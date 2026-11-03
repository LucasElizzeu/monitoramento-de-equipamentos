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

    def test_topology_has_distinct_physical_ports_and_correct_special_links(self):
        config = app.get_backbone()
        nodes = {node['id']: node for node in config['nodes']}
        self.assertNotIn('itapeua', nodes)
        ports = []
        for link in config['links']:
            for side, port_key in [('a', 'port_a'), ('b', 'port_b')]:
                self.assertIn(link[side], nodes)
                if link[port_key]:
                    ports.append((link[side], link[port_key]))
        self.assertEqual(len(ports), len(set(ports)))
        special = {link['label']: link for link in config['links'] if link['label']}
        self.assertEqual((special['GNEX']['a'], special['GNEX']['port_a'], special['GNEX']['b']), ('manaus2', 'ten-gigabit-ethernet:1/1/9', 'coari'))
        self.assertEqual((special['INFOVIA']['a'], special['INFOVIA']['b']), ('manaus', 'escritorio'))
        self.assertEqual((special['SMART']['a'], special['SMART']['b']), ('coari', 'claro'))
        self.assertEqual(sum(link['maintenance'] for link in config['links']), 1)
