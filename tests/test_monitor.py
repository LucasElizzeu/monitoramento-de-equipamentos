import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

# Isolate every test from the development database and its credentials.
TEMP = tempfile.TemporaryDirectory()
os.environ['MONITOR_DATA_DIR'] = TEMP.name
import app


class MonitorTests(unittest.TestCase):
    def setUp(self):
        app.init_db()
        with app.connect() as db:
            for table in ('devices', 'alerts', 'samples'):
                db.execute(f'DELETE FROM {table}')
        self.device = app.create_device(app.DeviceInput(name='Local', host='127.0.0.1'))
        self.id = self.device['id']

    def device_state(self):
        with app.connect() as db:
            return dict(db.execute('SELECT * FROM devices WHERE id=?', (self.id,)).fetchone())

    def test_twenty_losses_are_not_offline_but_twenty_one_are(self):
        for _ in range(20):
            app.record_ping(self.id, False)
        self.assertEqual(self.device_state()['state'], 'unstable')
        self.assertEqual(len(app.dashboard()['alerts']), 0)
        app.record_ping(self.id, False)
        self.assertEqual(self.device_state()['state'], 'offline')
        self.assertEqual(len(app.dashboard()['alerts']), 1)
        app.record_ping(self.id, False)
        self.assertEqual(len(app.dashboard()['alerts']), 1, 'No duplicate outage alerts')

    def test_success_resets_counter_and_registers_recovery(self):
        for _ in range(21):
            app.record_ping(self.id, False)
        app.record_ping(self.id, True, 1.25)
        d = self.device_state()
        self.assertEqual((d['state'], d['failures'], d['latency']), ('online', 0, 1.25))
        self.assertEqual(app.dashboard()['alerts'][0]['level'], 'success')

    def test_nonconsecutive_loss_does_not_accumulate(self):
        for _ in range(25):
            app.record_ping(self.id, False)
            app.record_ping(self.id, True, 2)
        self.assertEqual(self.device_state()['failures'], 0)
        self.assertEqual(app.dashboard()['alerts'], [])

    def test_collector_error_is_not_packet_loss(self):
        with patch.object(app, 'ping', side_effect=PermissionError):
            app.check_ping(self.device)
        self.assertEqual(self.device_state()['state'], 'error')
        self.assertEqual(self.device_state()['failures'], 0)
        self.assertEqual(app.history(self.id), [])

    def test_signal_parser_only_uses_explicit_units_and_labels(self):
        parsed = app.parse_port('ge1/1/1', 'ge1/1/1 link: up', 'ge1/1/1 RX power: -18.27 dBm TX power: -2.1 dBm')
        self.assertEqual((parsed['state'], parsed['rx'], parsed['tx']), ('up', -18.27, -2.1))
        parsed = app.parse_port('ge1/1/1', 'unrecognized output', 'temperature 32, voltage 3.3')
        self.assertEqual((parsed['state'], parsed['rx']), ('unknown', None))

    def test_port_names_must_match_exactly(self):
        result = app.port_lines('ge1/1/1', 'ge1/1/10 down\nge1/1/1 up')
        self.assertEqual(result, 'ge1/1/1 up')

    def test_supplied_datacom_output(self):
        status = '1/1/21   Up    false     1G     full    -         -        -       TELEBRAS-ANORI\n1/1/22   Up    false     1G     full    -         -        -       TELEBRAS-LTE-ANORI'
        optics = 'gigabit-ethernet 1/1/21 | 45.73 C | 3.37 V | 19.77 mA | -6.51 dBm | -12.96 dBm\ngigabit-ethernet 1/1/22 | 54.14 C | 3.3 V | 19.77 mA | -6.39 dBm | -9.53 dBm'
        result = app.parse_port('1/1/21', app.port_lines('1/1/21', status), app.port_lines('1/1/21', optics))
        self.assertEqual((result['state'], result['description'], result['tx'], result['rx']), ('up', 'TELEBRAS-ANORI', -6.51, -12.96))
        second = app.parse_port('1/1/22', app.port_lines('1/1/22', status), app.port_lines('1/1/22', optics))
        self.assertEqual((second['tx'], second['rx']), (-6.39, -9.53))

    def test_ssh_auto_detects_all_ports_from_supplied_format(self):
        d = app.create_device(app.DeviceInput(name='Datacom', host='192.0.2.1', kind='datacom', username='op',
            password='test', fingerprint='SHA256:'+'a'*43))
        d['password'] = app.CIPHER.encrypt(b'test').decode()
        d['ports'] = '[]'
        with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'ssh_read', side_effect=[
            '1/1/21 Up false 1G full - - - ANORI\n1/1/22 Down false 1G full - - - FILIAL',
            'gigabit-ethernet 1/1/21 | 45.73 C | 3.37 V | 19.77 mA | -6.51 dBm | -12.96 dBm']):
            app.check_ssh(d)
        result = next(x for x in app.dashboard()['devices'] if x['id'] == d['id'])
        self.assertEqual(len(result['port_data']), 2)
        self.assertEqual(result['port_data'][0]['rx'], -12.96)
        self.assertEqual(result['port_data'][1]['state'], 'down')

    def test_device_validation(self):
        for value in ('127.0.0.1; rm -rf /', 'example.com', ''):
            with self.assertRaises(ValueError):
                app.DeviceInput(name='Test', host=value)
        for value in ('show interface link; reboot', 'reboot', 'show {unknown}'):
            with self.assertRaises(ValueError):
                app.DeviceInput(name='Test', host='127.0.0.1', status_command=value)

    def test_credentials_are_encrypted_and_not_returned(self):
        d = app.create_device(app.DeviceInput(name='Datacom', host='192.0.2.1', kind='datacom',
            username='operator', password='test-only-not-a-real-secret', fingerprint='SHA256:'+'a'*43, ports=['ge1/1/1']))
        self.assertNotIn('password', d)
        self.assertTrue(d['has_password'])
        with app.connect() as db:
            encrypted = db.execute('SELECT password FROM devices WHERE id=?', (d['id'],)).fetchone()[0]
        self.assertNotEqual(encrypted, 'test-only-not-a-real-secret')
        self.assertEqual(app.CIPHER.decrypt(encrypted.encode()).decode(), 'test-only-not-a-real-secret')
        self.assertNotIn('test-only-not-a-real-secret', json.dumps(app.dashboard()))

    def test_host_key_mismatch_is_rejected(self):
        with self.assertRaises(app.paramiko.SSHException):
            app.VerifyFingerprint('SHA256:expected').missing_host_key(None, 'host', app.paramiko.RSAKey.generate(1024))

    def test_delete_removes_samples_but_keeps_events(self):
        for _ in range(21):
            app.record_ping(self.id, False)
        app.delete_device(self.id)
        data = app.dashboard()
        self.assertEqual(data['devices'], [])
        self.assertEqual(data['samples'], [])
        self.assertEqual(len(data['alerts']), 1)

    def test_ssh_port_transitions_generate_one_alert_and_recovery(self):
        d = app.create_device(app.DeviceInput(name='Datacom', host='192.0.2.1', kind='datacom', username='op',
            password='test', fingerprint='SHA256:'+'a'*43, ports=['ge1/1/1']))
        d['password'] = app.CIPHER.encrypt(b'test').decode()
        d['ports'] = json.dumps(d['ports'])
        with patch.object(app.paramiko, 'SSHClient') as factory, patch.object(app, 'ssh_read') as read:
            read.side_effect=['ge1/1/1 down', 'ge1/1/1 RX -20 dBm TX -2 dBm'] * 2
            app.check_ssh(d)
            app.check_ssh(d)
            alerts = [a for a in app.dashboard()['alerts'] if 'caiu' in a['message']]
            self.assertEqual(len(alerts), 1)
            read.side_effect=['ge1/1/1 up', 'ge1/1/1 RX -20 dBm TX -2 dBm']
            app.check_ssh(d)
            self.assertEqual(app.dashboard()['alerts'][0]['level'], 'success')
            factory.return_value.close.assert_called()


if __name__ == '__main__':
    unittest.main()
