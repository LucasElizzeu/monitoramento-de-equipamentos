import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ.setdefault('MONITOR_DATA_DIR', TEMP.name)
import app
import traffic_history


class TrafficHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        db_patch = patch.object(app, 'DB', Path(directory.name) / 'monitor.db')
        db_patch.start()
        self.addCleanup(db_patch.stop)
        app.init_db()
        self.at = time.time()
        self.device = app.create_device(app.DeviceInput(name='Datacom Coari', host='192.0.2.10', kind='datacom',
            username='test', password='test-only', fingerprint='SHA256:' + 'a' * 43,
            interface_type='gigabit-ethernet', ports=['1/1/1']))

    def port(self, value=120e6, family='gigabit-ethernet', name='1/1/1', **kwargs):
        return dict(name=name, interface_type=family, description='Enlace Coari', rx_bps=value,
                    utilization_enabled=True, **kwargs)

    def record(self, ports, at=None, device=None):
        with app.connect() as db:
            traffic_history.record(db, device or self.device, ports, app.port_alias_key, self.at if at is None else at)

    def catalog(self, include_zero=False):
        with patch.object(app.time, 'time', return_value=self.at):
            return app.traffic_ports(include_zero=include_zero)['series']

    def history(self, series_id):
        with patch.object(app.time, 'time', return_value=self.at):
            return app.traffic_port_history(series_id)

    def raw(self):
        with app.connect() as db:
            return dict(db.execute('SELECT * FROM devices WHERE id=?', (self.device['id'],)).fetchone())

    def test_starts_with_actual_measurements_and_persists_across_reinitialization(self):
        self.assertEqual(self.catalog(), [])
        self.record([self.port()])
        app.init_db()
        series = self.catalog()[0]
        history = self.history(series['id'])
        self.assertEqual(history['points'], [[self.at * 1000, 120e6]])
        self.assertEqual(history['end'] - history['start'], 86400000)
        self.assertEqual(history['stats']['count'], 1)
        self.assertEqual(history['stats']['mean_bps'], 120e6)
        self.assertNotIn('test-only', json.dumps(app.traffic_ports(include_zero=True)))

    def test_zero_is_real_but_unknown_and_disabled_measurements_are_not_zero(self):
        self.record([self.port(0)])
        self.assertEqual(self.catalog(), [])
        series = self.catalog(True)[0]
        self.record([self.port(120e6)], self.at - 60)
        self.record([self.port(None)], self.at - 30)
        values = self.history(series['id'])
        self.assertEqual([p[1] for p in values['points']], [120e6, None, 0])
        self.assertEqual(values['stats']['mean_bps'], 60e6)
        self.assertEqual(values['stats']['peak_bps'], 120e6)
        self.assertEqual(values['stats']['count'], 2)

    def test_invalid_or_percentage_only_ports_do_not_create_fabricated_history(self):
        for value in (None, float('nan'), float('inf'), -1, True):
            self.record([self.port(value)])
        port = self.port(120e6)
        port['utilization_enabled'] = False
        self.record([port])
        self.assertEqual(self.catalog(True), [])

    def test_failures_and_removed_ports_make_one_gap_without_stale_values(self):
        self.record([self.port()], self.at - 90)
        self.record(None, self.at - 60)
        self.record([], self.at - 30)
        series = self.catalog()[0]
        values = self.history(series['id'])
        self.assertEqual([p[1] for p in values['points']], [120e6, None])
        self.assertIsNone(values['stats']['last_bps'])
        self.record([self.port(0)], self.at)
        self.assertEqual(len(self.catalog()), 1, 'A port that carried traffic stays visible after going idle')
        self.assertEqual(self.history(series['id'])['stats']['last_bps'], 0)

    def test_same_number_different_families_and_sources_are_separate(self):
        other = app.create_device(app.DeviceInput(name='Outro', host='192.0.2.11', kind='datacom',
            username='test', password='test-only', fingerprint='SHA256:' + 'a' * 43))
        self.record([self.port(120e6), self.port(200e6, family='ten-gigabit-ethernet')])
        self.record([self.port(300e6)], device=other)
        catalog = self.catalog()
        self.assertEqual(len(catalog), 3)
        self.assertEqual({self.history(s['id'])['stats']['last_bps'] for s in catalog}, {120e6, 200e6, 300e6})
        self.assertEqual(len({(s['device_id'], s['identity']) for s in catalog}), 3)

    def test_port_prefix_variants_share_one_canonical_history(self):
        self.record([self.port(name='ge1/1/1')], self.at - 30)
        self.record([self.port(name='1/1/1')], self.at)
        catalog = self.catalog()
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]['identity'], 'gigabit-ethernet:1/1/1')
        self.assertEqual(self.history(catalog[0]['id'])['stats']['count'], 2)

    def test_renaming_port_updates_history_title_without_rewriting_samples(self):
        self.record([self.port()])
        series_id = self.catalog()[0]['id']
        app.update_port_alias(self.device['id'], app.PortAliasInput(
            port='1/1/1', interface_type='gigabit-ethernet', display_name='Saída para Coari'))
        self.assertEqual(self.catalog()[0]['display_name'], 'Saída para Coari')
        self.assertEqual(self.catalog()[0]['id'], series_id)
        self.assertEqual(self.history(series_id)['stats']['count'], 1)

    def test_retention_keeps_boundary_and_removes_older_data(self):
        self.record([self.port(10)], self.at - 86401)
        self.record([self.port(20)], self.at - 86400)
        self.record([self.port(30)], self.at)
        with app.connect() as db:
            traffic_history.prune(db, self.at)
            self.assertEqual(db.execute('SELECT count(*) FROM port_traffic_samples').fetchone()[0], 2)
        values = self.history(self.catalog()[0]['id'])
        self.assertEqual([p[1] for p in values['points']], [20, 30])

    def test_changing_host_or_deleting_device_cascades_samples(self):
        self.record([self.port()])
        app.update_device(self.device['id'], app.DeviceInput(name='Novo endereço', host='192.0.2.12', kind='datacom',
            username='test', fingerprint='SHA256:' + 'a' * 43, interface_type='gigabit-ethernet', ports=['1/1/1']))
        self.assertEqual(self.catalog(True), [])
        self.record([self.port()])
        app.delete_device(self.device['id'])
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM port_traffic_samples').fetchone()[0], 0)

    def test_unknown_history_returns_not_found(self):
        with self.assertRaises(app.HTTPException) as error:
            self.history(999)
        self.assertEqual(error.exception.status_code, 404)

    def test_successful_ssh_records_rx_and_failed_ssh_marks_gap(self):
        outputs = ['Gigabit Ethernet Interfaces:\n1/1/1 Up false 1G full - - - Enlace Coari',
            'gigabit-ethernet 1/1/1 | -6 dBm | -12 dBm',
            'L1 RX      L1 TX      L2 RX      L2 TX\nINTERFACE NAME               BANDWIDTH  BANDWIDTH  BANDWIDTH  BANDWIDTH\n'
            'gigabit-ethernet-1/1/1  120Mbps    10Mbps  110Mbps    9Mbps']
        with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'ssh_read', side_effect=outputs):
            app.check_ssh(self.raw())
        with patch.object(app.paramiko, 'SSHClient') as factory:
            factory.return_value.connect.side_effect = app.paramiko.SSHException('test connection failure')
            app.check_ssh(self.raw())
        with patch.object(app.time, 'time', return_value=time.time() + 1):
            series = app.traffic_ports()['series'][0]
            values = app.traffic_port_history(series['id'])
        self.assertEqual(values['stats']['count'], 1)
        self.assertEqual(values['stats']['peak_bps'], 120e6)
        self.assertIsNone(values['points'][-1][1])

    def test_stale_ssh_result_does_not_record_a_sample(self):
        old = self.raw()
        app.update_device(self.device['id'], app.DeviceInput(name='Renomeado', host=self.device['host'], kind='datacom',
            username='test', fingerprint='SHA256:' + 'a' * 43))
        with patch.object(app.paramiko, 'SSHClient') as factory:
            factory.return_value.connect.side_effect = app.paramiko.SSHException('stale failure')
            app.check_ssh(old)
        self.assertEqual(self.catalog(True), [])

    def test_demo_has_24_hour_samples_and_explicit_gaps_without_touching_database(self):
        before = app.dashboard()['devices']
        catalog = app.traffic_ports(demo=True)
        values = app.traffic_port_history(catalog['series'][0]['id'], demo=True)
        self.assertTrue(values['demo'])
        self.assertEqual(values['end'] - values['start'], 86400000)
        self.assertTrue(any(p[1] is None for p in values['points']))
        self.assertEqual(len(values['points']), 1441)
        self.assertEqual(app.dashboard()['devices'], before)


if __name__ == '__main__':
    unittest.main()
