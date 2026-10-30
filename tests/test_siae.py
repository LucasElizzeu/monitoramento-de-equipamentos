import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ.setdefault('MONITOR_DATA_DIR', TEMP.name)
import app


class SiaeConsumptionTests(unittest.TestCase):
    def test_total_uses_both_rates_and_preserves_real_zero(self):
        values = app.siae_consumption(120e6, 80e6)
        self.assertEqual(values, dict(trx_a_bps=120e6, trx_b_bps=80e6, total_bps=200e6))
        self.assertEqual(app.siae_consumption(0, 0)['total_bps'], 0)

    def test_missing_trx_keeps_total_unknown(self):
        for a, b in ((None, None), (None, 80e6), (120e6, None), (0, None)):
            with self.subTest(a=a, b=b):
                self.assertIsNone(app.siae_consumption(a, b)['total_bps'])

    def test_invalid_rates_and_overflow_are_rejected(self):
        for value in (-1, float('nan'), float('inf'), '120 Mbps', True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                app.siae_consumption(value, 0)
        with self.assertRaises(ValueError):
            app.siae_consumption(1e308, 1e308)

    def test_demo_is_explicit_and_has_no_datacom_ports(self):
        with patch.object(app, 'check_ping') as ping, patch.object(app, 'check_ssh') as ssh:
            dashboard = app.demo_dashboard()
        radios = [d for d in dashboard['devices'] if d['kind'] == 'siae']
        self.assertTrue(dashboard['demo'])
        self.assertEqual(len(radios), 2)
        for radio in radios:
            self.assertEqual(radio['siae_consumption']['status'], 'demo')
            self.assertEqual(radio['siae_consumption']['total_bps'], 200e6)
            self.assertEqual(radio['port_data'], [])
            self.assertEqual(radio['circuits'], [])
        ping.assert_not_called()
        ssh.assert_not_called()


class SiaeDeviceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        db_patch = patch.object(app, 'DB', Path(directory.name) / 'monitor.db')
        db_patch.start()
        self.addCleanup(db_patch.stop)
        app.init_db()
        self.radio = app.create_device(app.DeviceInput(name='SIAE Coari', host='192.0.2.70', kind='siae'))

    def current(self):
        with app.connect() as db:
            return app.public_device(db.execute('SELECT * FROM devices WHERE id=?', (self.radio['id'],)).fetchone(), db)

    def test_radio_persists_without_ssh_and_consumption_is_unconfigured(self):
        radio = self.current()
        self.assertEqual(radio['kind'], 'siae')
        self.assertEqual(radio['interval'], 1)
        self.assertFalse(radio['has_password'])
        self.assertNotIn('password', radio)
        self.assertEqual(radio['port_data'], [])
        self.assertEqual(radio['siae_consumption'], dict(
            trx_a_bps=None, trx_b_bps=None, total_bps=None, status='unconfigured'))

    def test_same_ip_can_be_bbu_but_cannot_duplicate_radio(self):
        app.create_device(app.DeviceInput(name='BBU', host=self.radio['host']))
        with self.assertRaises(app.HTTPException) as error:
            app.create_device(app.DeviceInput(name='SIAE duplicado', host=self.radio['host'], kind='siae'))
        self.assertEqual(error.exception.status_code, 409)

    def test_ping_is_local_and_does_not_need_ssh(self):
        with patch.object(app, 'IS_WINDOWS', False), patch.object(app, 'ping', return_value=SimpleNamespace(
                is_alive=True, avg_rtt=2.8)) as ping, patch.object(app, 'check_ssh') as ssh:
            app.run_check(self.radio, 'ping')
        ping.assert_called_once_with('192.0.2.70', count=1, timeout=4, privileged=False, payload_size=32)
        ssh.assert_not_called()
        self.assertEqual(self.current()['state'], 'online')
        self.assertEqual(self.current()['latency'], 2.8)
        self.assertIsNone(self.current()['siae_consumption']['total_bps'])

    def test_loss_threshold_recovery_and_collection_error_stay_separate(self):
        for _ in range(20):
            app.record_ping(self.radio['id'], False)
        self.assertEqual(self.current()['state'], 'unstable')
        app.record_ping(self.radio['id'], False)
        self.assertEqual(self.current()['state'], 'offline')
        app.record_ping(self.radio['id'], False, error='Falha do coletor local')
        self.assertEqual(self.current()['failures'], 21)
        app.record_ping(self.radio['id'], True, 3.2)
        self.assertEqual(self.current()['failures'], 0)
        events = app.dashboard()['alerts']
        self.assertEqual([e['level'] for e in events], ['success', 'warning', 'critical'])

    def test_edit_and_delete_radio_preserve_other_equipment(self):
        bbu = app.create_device(app.DeviceInput(name='BBU', host='192.0.2.72'))
        updated = app.update_device(self.radio['id'], app.DeviceInput(
            name='SIAE editado', host='192.0.2.71', kind='siae', interval=2))
        self.assertEqual(updated['name'], 'SIAE editado')
        self.assertEqual(updated['interval'], 2)
        app.delete_device(self.radio['id'])
        self.assertEqual([d['id'] for d in app.dashboard()['devices']], [bbu['id']])


if __name__ == '__main__':
    unittest.main()
