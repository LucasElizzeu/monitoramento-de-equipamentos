import json
import os
import tempfile
import threading
import time
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

    def test_one_second_interval_and_cadence(self):
        device = app.update_device(self.id, app.DeviceInput(name='Local', host='127.0.0.1', interval=1))
        starts = []
        def probe(*args, **kwargs):
            starts.append(time.monotonic())
            self.assertLess(kwargs['timeout'], 1)
            time.sleep(0.2)
            return Mock(is_alive=True, avg_rtt=1.2)
        app.STOP.clear()
        with patch.object(app, 'ping', side_effect=probe):
            worker = threading.Thread(target=app.monitor)
            worker.start()
            try:
                deadline = time.monotonic() + 4
                while len(starts) < 3 and time.monotonic() < deadline:
                    time.sleep(0.05)
            finally:
                app.STOP.set()
                worker.join(timeout=3)
                app.STOP.clear()
        self.assertGreaterEqual(len(starts), 3)
        self.assertTrue(all(0.95 <= b-a < 1.2 for a,b in zip(starts, starts[1:])), starts)
        with self.assertRaises(ValueError):
            app.DeviceInput(name='Local', host='127.0.0.1', interval=0)

    def test_edit_preserves_password_samples_and_id(self):
        d = app.create_device(app.DeviceInput(name='Datacom', host='192.0.2.1', kind='datacom',
            username='op', password='test-only', fingerprint='SHA256:'+'a'*43))
        app.record_ping(d['id'], True, 2)
        edited = app.update_device(d['id'], app.DeviceInput(name='Novo nome', host='192.0.2.1',
            interval=1, kind='datacom', username='op', fingerprint='SHA256:'+'a'*43))
        self.assertEqual((edited['id'], edited['name'], edited['interval']), (d['id'], 'Novo nome', 1))
        self.assertTrue(edited['has_password'])
        self.assertNotIn('password', edited)
        self.assertEqual(len(app.history(d['id'])), 1)
        with app.connect() as db:
            stored = db.execute('SELECT password FROM devices WHERE id=?', (d['id'],)).fetchone()[0]
        self.assertEqual(app.CIPHER.decrypt(stored.encode()).decode(), 'test-only')

    def test_edit_can_replace_password_and_ports(self):
        d = app.create_device(app.DeviceInput(name='Datacom', host='192.0.2.1', kind='datacom',
            username='op', password='old-test', fingerprint='SHA256:'+'a'*43))
        edited = app.update_device(d['id'], app.DeviceInput(name='Datacom', host='192.0.2.1', kind='datacom',
            username='op', password='new-test', fingerprint='SHA256:'+'a'*43, ports=['1/1/1']))
        self.assertEqual(edited['ports'], ['1/1/1'])
        with app.connect() as db:
            stored = db.execute('SELECT password FROM devices WHERE id=?', (d['id'],)).fetchone()[0]
        self.assertEqual(app.CIPHER.decrypt(stored.encode()).decode(), 'new-test')

    def test_edit_host_discards_old_samples_and_stale_workers(self):
        app.record_ping(self.id, True, 3)
        original = self.device
        app.update_device(self.id, app.DeviceInput(name='New target', host='192.0.2.2'))
        self.assertEqual(app.history(self.id), [])
        app.record_ping(self.id, True, 9, expected_version=original['config_version'])
        self.assertEqual(self.device_state()['state'], 'pending')
        self.assertEqual(app.history(self.id), [])

    def test_edit_rejects_conflicts_and_missing_device(self):
        other = app.create_device(app.DeviceInput(name='Other', host='192.0.2.2'))
        with self.assertRaises(app.HTTPException) as error:
            app.update_device(other['id'], app.DeviceInput(name='Duplicate', host='127.0.0.1'))
        self.assertEqual(error.exception.status_code, 409)
        with self.assertRaises(app.HTTPException) as error:
            app.update_device(99999, app.DeviceInput(name='Missing', host='127.0.0.2'))
        self.assertEqual(error.exception.status_code, 404)

    def test_optics_does_not_require_temperature_voltage_or_bias(self):
        for text in [
            'gigabit-ethernet 1/1/1 | 45.73 °C | N/A | - | -6.51 dBm | -12.96 dBm',
            'gigabit-ethernet-1/1/1 | - | - | - | -6,51 dBm | -12,96 dBm',
            'gigabit-ethernet 1/1/1 45 °C 3.3 V 19 mA -6.51 dBm -12.96 dBm']:
            with self.subTest(text=text):
                row = app.port_lines('1/1/1', text)
                self.assertEqual(app.parse_port('1/1/1', '1/1/1 Up', row)['rx'], -12.96)
                self.assertEqual(app.parse_port('1/1/1', '1/1/1 Up', row)['tx'], -6.51)

    def test_optics_single_missing_measurement_does_not_hide_other(self):
        rx, tx = app.optical_powers('1/1/1 | N/A | - | - | -6.51 dBm | N/A')
        self.assertEqual((rx, tx), (None, -6.51))
        rx, tx = app.optical_powers('RX power: N/A TX power: -2.0 dBm')
        self.assertEqual((rx, tx), (None, -2.0))
        self.assertEqual(app.optical_powers('1/1/1 | - | - | - | N/A | -12.96 dBm'), (-12.96, None))

    def test_optics_uses_header_order_and_wrapped_rows(self):
        output = 'Interface | Temperature | RX Power (dBm) | TX Power (dBm)\n1/1/1 | 40 C | -12.96 | -6.51\n1/1/10 | 40 C | -25 | -3'
        row = app.port_lines('1/1/1', output)
        self.assertEqual(app.optical_powers(row, output), (-12.96, -6.51))
        block = 'Interface: gigabit-ethernet 1/1/1\n RX power: -12.96 dBm\n TX power: -6.51 dBm\nInterface: gigabit-ethernet 1/1/10\n RX power: -25 dBm'
        self.assertEqual(app.optical_powers(app.port_lines('1/1/1', block)), (-12.96, -6.51))

    def test_old_ssh_result_cannot_overwrite_edited_device(self):
        d = app.create_device(app.DeviceInput(name='Datacom', host='192.0.2.1', kind='datacom',
            username='op', password='test-only', fingerprint='SHA256:'+'a'*43, ports=['1/1/1']))
        original = dict(d, password=app.CIPHER.encrypt(b'test-only').decode(), ports='["1/1/1"]')
        app.update_device(d['id'], app.DeviceInput(name='Edited', host='192.0.2.1', kind='datacom',
            username='op', fingerprint='SHA256:'+'a'*43, ports=['1/1/2']))
        with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'ssh_read', side_effect=[
            '1/1/1 Down', 'gigabit-ethernet 1/1/1 | - | - | - | -2 dBm | -20 dBm']):
            app.check_ssh(original)
        current = next(d for d in app.dashboard()['devices'] if d['id'] == original['id'])
        self.assertEqual(current['ports'], ['1/1/2'])
        self.assertEqual(current['port_data'], [])
        self.assertEqual(app.dashboard()['alerts'], [])

    def test_schema_migration_keeps_existing_equipment(self):
        # Simulate the installed schema before editing support existed.
        with app.connect() as db:
            db.execute('ALTER TABLE devices DROP COLUMN config_version')
        app.init_db()
        self.assertEqual(self.device_state()['name'], 'Local')
        self.assertEqual(self.device_state()['config_version'], 0)


    def test_transceiver_command_default_and_legacy_input(self):
        self.assertEqual(app.DeviceInput(name='Local', host='127.0.0.1').optics_command, 'show interface transceivers')
        self.assertEqual(app.DeviceInput(name='Local', host='127.0.0.1', optics_command='show interface tranceivers').optics_command, 'show interface transceivers')
        self.assertEqual(app.DeviceInput(name='Local', host='127.0.0.1', optics_command='display transceiver {port}').optics_command, 'display transceiver {port}')

    def test_legacy_optics_migration_preserves_data_and_is_idempotent(self):
        d = app.create_device(app.DeviceInput(name='Datacom', host='192.0.2.1', kind='datacom',
            username='op', password='test-only', fingerprint='SHA256:'+'a'*43))
        app.record_ping(d['id'], True, 3)
        with app.connect() as db:
            db.execute("UPDATE devices SET optics_command='show interface tranceivers' WHERE id=?", (d['id'],))
            password = db.execute('SELECT password FROM devices WHERE id=?', (d['id'],)).fetchone()[0]
        app.init_db()
        app.init_db()
        migrated = next(x for x in app.dashboard()['devices'] if x['id'] == d['id'])
        self.assertEqual(migrated['optics_command'], 'show interface transceivers')
        self.assertEqual(migrated['config_version'], d['config_version'] + 1)
        self.assertEqual(migrated['last_ssh'], 0)
        self.assertEqual(len(app.history(d['id'])), 1)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT password FROM devices WHERE id=?', (d['id'],)).fetchone()[0], password)
            db.execute("UPDATE devices SET optics_command='display transceiver {port}' WHERE id=?", (d['id'],))
        app.init_db()
        custom = next(x for x in app.dashboard()['devices'] if x['id'] == d['id'])
        self.assertEqual(custom['optics_command'], 'display transceiver {port}')

    def test_cli_syntax_error_with_zero_exit_is_not_a_valid_measurement(self):
        client = Mock()
        stdout, stderr = Mock(), Mock()
        stdout.read.return_value = b'show interface \n syntax error: unknown argument\n'
        stdout.channel.recv_exit_status.return_value = 0
        stderr.read.return_value = b''
        client.exec_command.return_value = (Mock(), stdout, stderr)
        with self.assertRaises(app.CommandRejected) as error:
            app.ssh_read(client, 'show interface transceivers')
        self.assertIn('show interface transceivers', str(error.exception))
        stdout.read.return_value = b'gigabit-ethernet 1/1/1 | 40 C | 3 V | 19 mA | -6 dBm | -12 dBm'
        self.assertIn('-12 dBm', app.ssh_read(client, 'show interface transceivers'))

    def test_ssh_reports_rejected_command_in_dashboard(self):
        d = app.create_device(app.DeviceInput(name='Datacom', host='192.0.2.1', kind='datacom',
            username='op', password='test-only', fingerprint='SHA256:'+'a'*43))
        original = dict(d, password=app.CIPHER.encrypt(b'test-only').decode(), ports='[]')
        with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'ssh_read', side_effect=[
            '1/1/1 Up false 10G full - - lag-1 LINK',
            app.CommandRejected('O equipamento rejeitou o comando "show interface transceivers".')]):
            app.check_ssh(original)
        result = next(x for x in app.dashboard()['devices'] if x['id'] == d['id'])
        self.assertIn('show interface transceivers', result['ssh_error'])
        self.assertEqual(result['port_data'], [])



if __name__ == '__main__':
    unittest.main()
