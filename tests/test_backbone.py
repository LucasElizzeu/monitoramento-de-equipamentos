import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from fastapi import HTTPException


class BackboneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(app, 'DB', Path(self.temp.name) / 'monitor.db')
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def test_template_loads_on_windows_default_encoding(self):
        original_open = Path.open

        def windows_open(path, mode='r', buffering=-1, encoding=None, errors=None, newline=None):
            if 'b' not in mode and encoding in (None, 'locale'):
                encoding = 'cp1252'
            return original_open(path, mode, buffering, encoding, errors, newline)

        with patch.object(Path, 'open', windows_open):
            config = app.get_backbone()
        self.assertIn('Nazaré', [node['name'] for node in config['nodes']])
        self.assertIn('TELEBRÁS 1', [link['label'] for link in config['links']])

    def test_ports_persist_without_changing_template(self):
        template = (app.ROOT / 'static/backbone.json').read_bytes()
        config = app.get_backbone()
        link = next(link for link in config['links'] if link['port_a'] is None)
        app.update_backbone_ports(link['id'], app.BackbonePortsInput(port_a=' XGE0/0/15 ', port_b=link['port_b'], maintenance=True))
        saved = next(item for item in app.get_backbone()['links'] if item['id'] == link['id'])
        self.assertEqual(saved['port_a'], 'XGE0/0/15')
        self.assertTrue(saved['maintenance'])
        app.update_backbone_ports(link['id'], app.BackbonePortsInput(port_a='XGE0/0/16'))
        partial = next(item for item in app.get_backbone()['links'] if item['id'] == link['id'])
        self.assertEqual(partial['port_b'], link['port_b'])
        self.assertTrue(partial['maintenance'])
        app.update_backbone_ports(link['id'], app.BackbonePortsInput(port_a='', port_b=link['port_b'], maintenance=False))
        restored = next(item for item in app.get_backbone()['links'] if item['id'] == link['id'])
        self.assertIsNone(restored['port_a'])
        self.assertFalse(restored['maintenance'])
        self.assertEqual((app.ROOT / 'static/backbone.json').read_bytes(), template)

    def test_unknown_link_cannot_create_override(self):
        with self.assertRaises(HTTPException) as error:
            app.update_backbone_ports('missing', app.BackbonePortsInput())
        self.assertEqual(error.exception.status_code, 404)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM backbone_ports').fetchone()[0], 0)

    def test_topology_preserves_ports_with_only_confirmed_mirrored_arrival(self):
        config = app.get_backbone()
        nodes = {node['id']: node for node in config['nodes']}
        self.assertNotIn('itapeua', nodes)
        ports = []
        for link in config['links']:
            for side, port_key in [('a', 'port_a'), ('b', 'port_b')]:
                self.assertIn(link[side], nodes)
                if link[port_key]:
                    ports.append((link[side], link[port_key]))
        from collections import Counter
        repeated = {port: count for port, count in Counter(ports).items() if count > 1}
        self.assertEqual(repeated, {('escritorio', 'ten-gigabit-ethernet:1/1/4'): 2})
        infovia = next(link for link in config['links'] if link['id'] == 'coari-escritorio-infovia-1')
        self.assertEqual((infovia['a'], infovia['port_a'], infovia['b'], infovia['port_b']),
                         ('coari', 'ten-gigabit-ethernet:1/1/7', 'escritorio', 'ten-gigabit-ethernet:1/1/4'))
        self.assertIn('espelhada', infovia['note'])
        special = {link['label']: link for link in config['links'] if link['label']}
        self.assertNotIn('GNEX', special)
        self.assertNotIn('manaus2-coari-1', {link['id'] for link in config['links']})
        self.assertEqual((special['INFOVIA']['id'], special['INFOVIA']['a'], special['INFOVIA']['port_a'], special['INFOVIA']['b'], special['INFOVIA']['port_b']),
                         ('manaus-escritorio-infovia-1', 'manaus', 'XGE0/0/23', 'escritorio', 'ten-gigabit-ethernet:1/1/4'))
        self.assertEqual((special['SMART']['a'], special['SMART']['b']), ('coari', 'claro'))
        self.assertEqual(sum(link['maintenance'] for link in config['links']), 0)

    def test_s2bti_connects_manaus2_coari_with_confirmed_ports(self):
        config = app.get_backbone()
        link = next(link for link in config['links'] if link['id'] == 'manaus-coari-s2bti-1')
        self.assertEqual((link['a'], link['b']), ('manaus2', 'coari'))
        self.assertEqual(link['port_a'], 'ten-gigabit-ethernet:1/1/9')
        self.assertEqual(link['port_b'], 'gigabit-ethernet:1/1/11')
        self.assertFalse(link['maintenance'])
        self.assertIn('S2BTI', link['label'])
        nodes = {n['id']: n for n in config['nodes']}
        self.assertEqual(nodes['manaus2']['x'], nodes['manaus']['x'])
        self.assertLess(nodes['manaus2']['y'], nodes['manaus']['y'])
        self.assertLess(link['routeLane'], min(n['y'] for n in config['nodes']))

    def test_radio_topology_has_both_independent_networks_and_exact_endpoint_pairs(self):
        config = app.get_backbone()
        self.assertEqual(len(config['links']), 29)
        radios = [l for l in config['radio_links'] if l['route'] == 'coari-tefe']
        self.assertEqual(len(radios), 8)
        self.assertEqual(len({l['id'] for l in radios}), 8)
        hosts = []
        sites = ['Coari', 'Betânia', 'Aracati', 'Prainha', 'Tefé']
        names = ['COARI', 'BETANIA', 'ARACATI', 'PRAINHA', 'TEFE']
        for network, ap, st in [(1, 20, 30), (2, 40, 50)]:
            links = sorted([l for l in radios if l['network'] == network], key=lambda l: l['order'])
            self.assertEqual([l['order'] for l in links], [1, 2, 3, 4])
            for i, link in enumerate(links):
                suffix = ' 2' if network == 2 else ''
                self.assertEqual(link['a'], dict(name=f'AP_{names[i]}/{names[i+1]}{suffix}', host=f'192.168.{ap}.{i*2+1}', site=sites[i]))
                self.assertEqual(link['b'], dict(name=f'ST_{names[i]}/{names[i+1]}{suffix}', host=f'192.168.{st}.{i*2+2}', site=sites[i+1]))
                hosts.extend([link['a']['host'], link['b']['host']])
        self.assertEqual(len(set(hosts)), 16)

    def test_radio_datacom_bindings_preserve_confirmed_source_and_pending_destination(self):
        config = app.get_backbone()
        nodes = {n['id']: n for n in config['nodes']}
        for network in config['radio_networks']:
            self.assertIn(network['network'], (1, 2))
            self.assertEqual(network['source'], dict(node='coari', port=f"ten-gigabit-ethernet:1/1/{7+network['network']}"))
            self.assertEqual(nodes[network['source']['node']]['host'], '10.200.9.1')
            self.assertEqual(nodes[network['target']['node']]['host'], '10.200.19.1')
            self.assertIsNone(network['target']['port'])
            self.assertEqual(network['target']['candidate_ports'], [f'gigabit-ethernet:1/1/{p}' for p in (5, 6, 7, 8)])
        self.assertEqual(len(config['radio_networks']), 2)

    def test_tefe_tabatinga_pairs_follow_the_thirty_supplied_ips(self):
        config = app.get_backbone()
        links = sorted([l for l in config['radio_links'] if l['route'] == 'tefe-tabatinga'], key=lambda l: l['order'])
        self.assertEqual(config['radio_route_origins']['tefe-tabatinga'], dict(node='claro', port=None))
        self.assertEqual(next(n['host'] for n in config['nodes'] if n['id']=='claro'), '10.200.19.1')
        self.assertEqual(len(links), 15)
        self.assertEqual([l['order'] for l in links], list(range(1, 16)))
        for i, link in enumerate(links):
            self.assertIsNone(link['network'])
            self.assertEqual(link['a']['host'], f'192.168.60.{2*i+1}')
            self.assertEqual(link['b']['host'], f'192.168.60.{2*i+2}')
            self.assertTrue(link['a']['name'].startswith('AP'))
            self.assertTrue(link['b']['name'].startswith('ST'))
            if i:
                self.assertEqual(links[i-1]['b']['site'], link['a']['site'])
        self.assertEqual(links[0]['a']['name'], 'AP_TEFE/UARINI')
        self.assertEqual(links[11]['b']['name'], 'ST_SAO_PAULO/CATURIÁ')
        self.assertEqual(links[7]['b']['name'], 'ST_TONANTINS/PROPERIDADE')
        self.assertEqual(links[5]['b']['site'], 'Guariba / N. Progresso')
        self.assertEqual(links[-1]['b']['name'], 'ST_TABATINGA/BELEM_DO_SOLIMOES')
        self.assertEqual(links[-1]['b']['site'], 'Tabatinga')
        all_ips = [l[side]['host'] for l in config['radio_links'] for side in ('a', 'b')]
        self.assertEqual(len(set(all_ips)), 46)
        self.assertEqual(len(config['links']), 29)
