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
            self.assertEqual(kwargs['timeout'], 4)
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
            db.execute('ALTER TABLE devices DROP COLUMN ping_timeout')
            db.execute('ALTER TABLE devices DROP COLUMN ping_detail')
            db.execute('ALTER TABLE devices DROP COLUMN interface_type')
            db.execute('ALTER TABLE devices DROP COLUMN ssh_diagnostic')
            db.execute('ALTER TABLE devices DROP COLUMN circuit_position')
            db.execute('ALTER TABLE devices DROP COLUMN port_aliases')
        app.init_db()
        self.assertEqual(self.device_state()['name'], 'Local')
        self.assertEqual(self.device_state()['config_version'], 0)
        self.assertEqual(self.device_state()['ping_timeout'], 4)
        self.assertIsNone(self.device_state()['ping_detail'])
        self.assertEqual(self.device_state()['interface_type'], 'auto')
        self.assertEqual(self.device_state()['ssh_diagnostic'], '{}')
        self.assertIsNone(self.device_state()['circuit_position'])
        self.assertEqual(self.device_state()['port_aliases'], '{}')


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


    def test_native_windows_ping_uses_same_system_command(self):
        output = 'Resposta de 10.0.3.6: bytes=32 tempo=2ms TTL=64\n'
        with patch.object(app.subprocess, 'run', return_value=Mock(stdout=output, stderr='', returncode=0)) as run:
            self.assertEqual(app.windows_ping('10.0.3.6', 4), (True, 2.0, output.strip()))
        args = run.call_args.args[0]
        self.assertEqual(args[-1], '10.0.3.6')
        self.assertEqual(args[1:-1], ['-4', '-n', '1', '-w', '4000'])
        self.assertTrue(args[0].endswith('PING.EXE'))
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_native_windows_handles_latency_and_ipv6(self):
        for host, output, latency in [
            ('10.0.3.6', 'Reply from 10.0.3.6: bytes=32 time<1ms TTL=64', 0.0),
            ('10.0.3.6', 'Resposta de 10.0.3.6: bytes=32 tempo=1200ms TTL=64', 1200.0),
            ('::1', 'Reply from ::1: time<1ms', 0.0)]:
            with self.subTest(host=host, output=output), patch.object(app.subprocess, 'run', return_value=Mock(stdout=output, stderr='', returncode=0)):
                alive, rtt, _ = app.windows_ping(host, 4)
                self.assertEqual((alive, rtt), (True, latency))

    def test_native_windows_unreachable_with_exit_zero_is_not_online(self):
        output = 'Resposta de 10.0.3.1: Host de destino inacessível.\nRecebidos = 1'
        with patch.object(app.subprocess, 'run', return_value=Mock(stdout=output, stderr='', returncode=0)):
            self.assertFalse(app.windows_ping('10.0.3.6', 4)[0])
        output = 'Request timed out.\nLost = 1 (100% loss)'
        with patch.object(app.subprocess, 'run', return_value=Mock(stdout=output, stderr='', returncode=1)):
            self.assertFalse(app.windows_ping('10.0.3.6', 4)[0])

    def test_native_windows_does_not_accept_other_source_or_unknown_output(self):
        for output in ['Reply from 10.0.3.60: bytes=32 time=2ms TTL=64', 'Unexpected localized output']:
            with self.subTest(output=output), patch.object(app.subprocess, 'run', return_value=Mock(stdout=output, stderr='', returncode=0)):
                with self.assertRaises(app.PingCollectionError):
                    app.windows_ping('10.0.3.6', 4)

    def test_windows_local_failure_is_a_collector_error(self):
        with patch.object(app, 'IS_WINDOWS', True), patch.object(app.subprocess, 'run', return_value=Mock(stdout='PING: transmit failed. General failure.', stderr='', returncode=1)):
            app.check_ping(self.device)
        self.assertEqual(self.device_state()['state'], 'error')
        self.assertEqual(self.device_state()['failures'], 0)
        self.assertIn('General failure', self.device_state()['ping_detail'])
        self.assertEqual(app.history(self.id), [])

    def test_windows_missing_executable_is_not_packet_loss(self):
        with patch.object(app, 'IS_WINDOWS', True), patch.object(app.subprocess, 'run', side_effect=FileNotFoundError):
            app.check_ping(self.device)
        self.assertEqual(self.device_state()['state'], 'error')
        self.assertEqual(self.device_state()['failures'], 0)

    def test_windows_collector_selects_native_ping(self):
        with patch.object(app, 'IS_WINDOWS', True), patch.object(app, 'windows_ping', return_value=(True, 1200, 'Native echo reply')) as native, patch.object(app, 'ping') as library:
            app.check_ping(self.device)
            native.assert_called_once_with('127.0.0.1', 4)
            library.assert_not_called()
        self.assertEqual((self.device_state()['state'], self.device_state()['latency']), ('online', 1200))
        self.assertEqual(self.device_state()['ping_detail'], 'Native echo reply')

    def test_timeout_is_independent_of_interval_and_validated(self):
        device = app.create_device(app.DeviceInput(name='Slow link', host='192.0.2.2', interval=1, ping_timeout=6))
        with patch.object(app, 'IS_WINDOWS', False), patch.object(app, 'ping', return_value=Mock(is_alive=True, avg_rtt=1200)) as library:
            app.check_ping(device)
            self.assertEqual(library.call_args.kwargs['timeout'], 6)
        result = next(d for d in app.dashboard()['devices'] if d['id'] == device['id'])
        self.assertEqual(result['state'], 'online')
        self.assertEqual(result['ping_timeout'], 6)
        for timeout in (0, 31, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                app.DeviceInput(name='Invalid', host='127.0.0.2', ping_timeout=timeout)


    def interface_fixture(self):
        status = ('Gigabit Ethernet Interfaces:\n'
                  'ID Link Shutdown Speed Duplex Disabled Blocked LAG Description\n'
                  '1/1/1 Down false - - - - - GIGA-LINK\n'
                  'Ten Gigabit Ethernet Interfaces:\n'
                  'ID Link Shutdown Speed Duplex Disabled Blocked LAG Description\n'
                  '1/1/1 Up false 10G full - - lag-1 TEN-LINK\n'
                  '1/1/2 Up false 10G full - - lag-1 TEN-SECOND\n'
                  'Hundred Gigabit Ethernet Interfaces:\n'
                  '1/1/1 Down false - - - - - HUNDRED-LINK')
        optics = ('Interface | Temperature | Voltage | Bias | TX power (dBm) | RX power (dBm)\n'
                  'gigabit-ethernet 1/1/1 | 40 C | 3 V | 10 mA | -2 dBm | -26 dBm\n'
                  'ten-gigabit-ethernet 1/1/1 | 45 C | 3 V | 10 mA | -6 dBm | -12 dBm\n'
                  'ten-gigabit-ethernet 1/1/2 | 44 C | 3 V | 10 mA | -7 dBm | -13 dBm\n'
                  'hundred-gigabit-ethernet 1/1/1 | 42 C | 3 V | 10 mA | -3 dBm | -18 dBm')
        return status, optics

    def run_family_check(self, family, ports):
        d = app.create_device(app.DeviceInput(name='Typed Datacom', host='192.0.2.3', kind='datacom',
            username='op', password='test-only', fingerprint='SHA256:'+'a'*43, ports=ports, interface_type=family))
        stored = dict(d, password=app.CIPHER.encrypt(b'test-only').decode(), ports=json.dumps(ports))
        with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'ssh_read', side_effect=self.interface_fixture()):
            app.check_ssh(stored)
        return next(x for x in app.dashboard()['devices'] if x['id'] == d['id'])

    def test_ten_selection_does_not_read_gigabit_or_hundred_same_number(self):
        result = self.run_family_check('ten-gigabit-ethernet', ['1/1/1'])
        self.assertIsNone(result['ssh_error'])
        port = result['port_data'][0]
        self.assertEqual((port['name'], port['state'], port['description'], port['rx'], port['tx']),
                         ('1/1/1', 'up', 'TEN-LINK', -12, -6))
        self.assertEqual(port['interface_type'], 'ten-gigabit-ethernet')
        self.assertEqual(port['identity'], 'ten-gigabit-ethernet:1/1/1')
        self.assertEqual(app.dashboard()['alerts'], [])

    def test_ten_auto_discovery_only_includes_ten_ports(self):
        result = self.run_family_check('ten-gigabit-ethernet', [])
        self.assertEqual([p['name'] for p in result['port_data']], ['1/1/1', '1/1/2'])
        self.assertTrue(all(p['state'] == 'up' for p in result['port_data']))
        self.assertEqual(result['port_data'][1]['rx'], -13)

    def test_gigabit_selection_preserves_real_down_state(self):
        result = self.run_family_check('gigabit-ethernet', ['1/1/1'])
        port = result['port_data'][0]
        self.assertEqual((port['state'], port['description'], port['rx']), ('down', 'GIGA-LINK', -26))
        self.assertIn('Gigabit Ethernet', app.dashboard()['alerts'][0]['message'])

    def test_hundred_selection_does_not_use_ten_up_state(self):
        result = self.run_family_check('hundred-gigabit-ethernet', ['1/1/1'])
        port = result['port_data'][0]
        self.assertEqual((port['state'], port['description'], port['rx']), ('down', 'HUNDRED-LINK', -18))

    def test_auto_ambiguous_port_requests_selection_instead_of_guessing(self):
        result = self.run_family_check('auto', ['1/1/1'])
        self.assertEqual(result['port_data'], [])
        self.assertIn('selecione Gigabit, Ten Gigabit', result['ssh_error'])
        self.assertFalse(any(a['level'] == 'critical' for a in app.dashboard()['alerts']))

    def test_selected_type_does_not_fall_back_to_other_family(self):
        status, optics = self.interface_fixture()
        self.assertEqual(app.port_lines('1/1/2', optics, 'gigabit-ethernet'), '')
        self.assertIn('-13 dBm', app.port_lines('1/1/2', optics, 'ten-gigabit-ethernet'))
        self.assertNotIn('-26 dBm', app.port_lines('1/1/1', optics, 'ten-gigabit-ethernet'))
        self.assertIn('TEN-LINK', app.port_lines('1/1/1', status, 'ten-gigabit-ethernet'))
        self.assertNotIn('HUNDRED-LINK', app.port_lines('1/1/1', status, 'ten-gigabit-ethernet'))

    def test_edit_interface_type_keeps_password_and_invalidates_old_readings(self):
        result = self.run_family_check('gigabit-ethernet', ['1/1/1'])
        self.assertTrue(result['port_data'])
        updated = app.update_device(result['id'], app.DeviceInput(name='Typed Datacom', host='192.0.2.3', kind='datacom',
            username='op', fingerprint='SHA256:'+'a'*43, ports=['1/1/1'], interface_type='ten-gigabit-ethernet'))
        self.assertEqual(updated['interface_type'], 'ten-gigabit-ethernet')
        self.assertEqual(updated['port_data'], [])
        self.assertEqual(updated['id'], result['id'])
        self.assertTrue(updated['has_password'])
        with self.assertRaises(ValueError):
            app.DeviceInput(name='Invalid', host='127.0.0.1', interface_type='not-a-type')


    def test_per_port_templates_still_support_unlabelled_diagnostics(self):
        d = app.create_device(app.DeviceInput(name='Custom Datacom', host='192.0.2.4', kind='datacom',
            username='op', password='test-only', fingerprint='SHA256:'+'a'*43, ports=['1/1/1'],
            interface_type='ten-gigabit-ethernet', status_command='show interface ten-gigabit-ethernet {port}',
            optics_command='show interface transceivers ten-gigabit-ethernet {port}'))
        original = dict(d, password=app.CIPHER.encrypt(b'test-only').decode(), ports='["1/1/1"]')
        with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'ssh_read', side_effect=[
            'link status: up', 'RX power: -12 dBm TX power: -6 dBm']):
            app.check_ssh(original)
        result = next(x for x in app.dashboard()['devices'] if x['id'] == d['id'])
        self.assertEqual(result['port_data'][0]['state'], 'up')
        self.assertEqual(result['port_data'][0]['rx'], -12)


    def test_compact_and_hyphenated_headers_keep_selected_ten_family(self):
        for giga, ten in [('GigabitEthernet Interfaces:', 'TenGigabitEthernet Interfaces:'),
                          ('Gigabit-Ethernet Interfaces:', 'Ten-GigabitEthernet Interfaces:'),
                          ('Gigabit Ethernet Interfaces:', '10GE Interfaces:')]:
            with self.subTest(ten=ten):
                status = f'{giga}\n1/1/1 Down false - - - - - GIGA\n{ten}\n1/1/1 Up false 10G full - - - TEN'
                selected = app.port_lines('1/1/1', status, 'ten-gigabit-ethernet')
                self.assertIn('1/1/1 Up', selected)
                self.assertNotIn('1/1/1 Down', selected)

    def test_repeated_same_ten_diagnostics_are_one_interface_not_another_family(self):
        optics = ('TenGigabitEthernet Interfaces:\n'
                  'TenGigabitEthernet 1/1/1 RX power: -12 dBm\n'
                  'TenGigabitEthernet 1/1/1 TX power: -6 dBm')
        selected = app.port_lines('1/1/1', optics, 'ten-gigabit-ethernet')
        self.assertEqual(app.optical_powers(selected), (-12, -6))


    def test_compact_ten_end_to_end_uses_saved_selection(self):
        d = app.create_device(app.DeviceInput(name='Compact Ten', host='192.0.2.5', kind='datacom',
            username='op', password='test-only', fingerprint='SHA256:'+'a'*43, ports=['1/1/1']))
        edited = app.update_device(d['id'], app.DeviceInput(name='Compact Ten', host='192.0.2.5', kind='datacom',
            username='op', fingerprint='SHA256:'+'a'*43, ports=['1/1/1'], interface_type='ten-gigabit-ethernet'))
        with app.connect() as db:
            stored = dict(db.execute('SELECT * FROM devices WHERE id=?', (d['id'],)).fetchone())
        status = 'GigabitEthernet Interfaces:\n1/1/1 Down false - - - - - GIGA\nTenGigabitEthernet Interfaces:\n1/1/1 Up false 10G full - - - TEN'
        optics = 'GigabitEthernet 1/1/1 | 40 C | 3 V | 19 mA | -2 dBm | -26 dBm\nTenGigabitEthernet 1/1/1 | 40 C | 3 V | 19 mA | -6 dBm | -12 dBm'
        with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'ssh_read', side_effect=[status, optics]):
            app.check_ssh(stored)
        result = next(x for x in app.dashboard()['devices'] if x['id'] == d['id'])
        self.assertIsNone(result['ssh_error'])
        self.assertEqual(result['port_data'][0]['state'], 'up')
        self.assertEqual(result['port_data'][0]['rx'], -12)
        self.assertEqual(result['port_data'][0]['interface_type'], 'ten-gigabit-ethernet')
        self.assertEqual(result['ssh_diagnostic'], {})

    def test_explicit_type_unrecognized_output_keeps_diagnostic_and_no_password(self):
        d = app.create_device(app.DeviceInput(name='Unknown Ten', host='192.0.2.6', kind='datacom',
            username='op', password='test-only-secret', fingerprint='SHA256:'+'a'*43, ports=['1/1/1'],
            interface_type='ten-gigabit-ethernet'))
        with app.connect() as db:
            stored = dict(db.execute('SELECT * FROM devices WHERE id=?', (d['id'],)).fetchone())
        status = 'UnknownFamily Interfaces:\n1/1/1 Down false - - - - - FIRST\nOtherFamily Interfaces:\n1/1/1 Up false 10G full - - - SECOND'
        with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'ssh_read', side_effect=[status, 'No optical data']):
            app.check_ssh(stored)
        result = next(x for x in app.dashboard()['devices'] if x['id'] == d['id'])
        self.assertIn('Ten Gigabit Ethernet', result['ssh_error'])
        self.assertNotIn('Edite o Datacom', result['ssh_error'])
        self.assertEqual(result['ssh_diagnostic']['interface_type'], 'ten-gigabit-ethernet')
        self.assertEqual(result['ssh_diagnostic']['status_output'], status)
        self.assertEqual(result['ssh_diagnostic']['stage'], 'portas: 1/1/1')
        self.assertNotIn('test-only-secret', json.dumps(result))
        self.assertEqual(result['port_data'], [])

    def test_conflicting_same_family_states_are_not_silently_picked(self):
        output = 'TenGigabitEthernet Interfaces:\n1/1/1 Up false 10G full - - - FIRST\n1/1/1 Down false - - - - - SECOND'
        with self.assertRaises(app.InterfaceSelectionError) as error:
            app.port_lines('1/1/1', output, 'ten-gigabit-ethernet')
        self.assertIn('estados Up e Down conflitantes', str(error.exception))

    def test_cr_only_output_preserves_interface_sections(self):
        output = 'GigabitEthernet Interfaces:\r1/1/1 Down false - - - - - GIGA\rTenGigabitEthernet Interfaces:\r1/1/1 Up false 10G full - - - TEN'
        result = app.port_lines('1/1/1', output, 'ten-gigabit-ethernet')
        self.assertIn('1/1/1 Up', result)
        self.assertNotIn('1/1/1 Down', result)


    def named_port_fixture(self):
        d = app.create_device(app.DeviceInput(name='Alias Datacom', host='192.0.2.8', kind='datacom',
            username='op', password='test-only', fingerprint='SHA256:'+'a'*43, ports=['1/1/1'],
            interface_type='ten-gigabit-ethernet', circuit_position=2))
        readings = [dict(name='1/1/1', interface_type=family, state='up', rx=-12, tx=-6,
                         description='SWITCH_DM4380-CAA...', identity=family+':1/1/1')
                    for family in ('ten-gigabit-ethernet', 'gigabit-ethernet')]
        with app.connect() as db:
            db.execute('UPDATE devices SET port_data=? WHERE id=?', (json.dumps(readings), d['id']))
        return d

    def test_custom_port_name_persists_without_touching_device_description_or_ssh(self):
        d = self.named_port_fixture()
        with patch.object(app.paramiko, 'SSHClient') as ssh:
            renamed = app.update_port_alias(d['id'], app.PortAliasInput(port='1/1/1',
                interface_type='ten-gigabit-ethernet', display_name='  Saída para Anori  '))
            ssh.assert_not_called()
        self.assertEqual(renamed['port_data'][0]['display_name'], 'Saída para Anori')
        self.assertEqual(renamed['port_data'][0]['description'], 'SWITCH_DM4380-CAA...')
        self.assertEqual(renamed['port_data'][1]['display_name'], 'SWITCH_DM4380-CAA...')
        self.assertEqual(renamed['config_version'], d['config_version'])
        self.assertEqual(renamed['circuit_position'], 2)
        self.assertTrue(renamed['has_password'])
        app.init_db()
        persisted = next(x for x in app.dashboard()['devices'] if x['id'] == d['id'])
        self.assertEqual(persisted['port_data'][0]['custom_name'], 'Saída para Anori')

    def test_clearing_port_alias_restores_equipment_description(self):
        d = self.named_port_fixture()
        app.update_port_alias(d['id'], app.PortAliasInput(port='1/1/1', interface_type='ten-gigabit-ethernet', display_name='Entrada'))
        result = app.update_port_alias(d['id'], app.PortAliasInput(port='1/1/1', interface_type='ten-gigabit-ethernet', display_name=''))
        self.assertEqual(result['port_data'][0]['display_name'], 'SWITCH_DM4380-CAA...')
        self.assertEqual(result['port_aliases'], {})

    def test_new_ssh_readings_keep_custom_name_and_include_it_in_alerts(self):
        d = self.named_port_fixture()
        app.update_port_alias(d['id'], app.PortAliasInput(port='1/1/1', interface_type='ten-gigabit-ethernet', display_name='Circuito Anori'))
        with app.connect() as db:
            stored = dict(db.execute('SELECT * FROM devices WHERE id=?', (d['id'],)).fetchone())
        with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'ssh_read', side_effect=[
            'Ten Gigabit Ethernet Interfaces:\n1/1/1 Down false - - - - - NOVA-DESCRICAO',
            'ten-gigabit-ethernet 1/1/1 | 40 C | 3 V | 19 mA | -2 dBm | -12 dBm']):
            app.check_ssh(stored)
        result = next(x for x in app.dashboard()['devices'] if x['id'] == d['id'])
        self.assertEqual(result['port_data'][0]['display_name'], 'Circuito Anori')
        self.assertEqual(result['port_data'][0]['description'], 'NOVA-DESCRICAO')
        self.assertIn('Circuito Anori', app.dashboard()['alerts'][0]['message'])

    def test_port_alias_validation_and_missing_device(self):
        for kwargs in [dict(port='1/1/1; reboot'), dict(port='1/1/1', interface_type='invalid'),
                       dict(port='1/1/1', display_name='x'*121), dict(port='1/1/1', display_name='line1\nline2')]:
            with self.assertRaises(ValueError):
                app.PortAliasInput(**kwargs)
        with self.assertRaises(app.HTTPException) as error:
            app.update_port_alias(999999, app.PortAliasInput(port='1/1/1', display_name='Name'))
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(app.HTTPException) as error:
            app.update_port_alias(self.id, app.PortAliasInput(port='1/1/1', display_name='Name'))
        self.assertEqual(error.exception.status_code, 422)

    def test_position_is_optional_persisted_and_preserved_for_old_clients(self):
        updated = app.update_device(self.id, app.DeviceInput(name='Positioned', host='127.0.0.1', circuit_position=10))
        self.assertEqual(updated['circuit_position'], 10)
        kept = app.update_device(self.id, app.DeviceInput(name='Renamed', host='127.0.0.1'))
        self.assertEqual(kept['circuit_position'], 10)
        cleared = app.update_device(self.id, app.DeviceInput(name='Renamed', host='127.0.0.1', circuit_position=None))
        self.assertIsNone(cleared['circuit_position'])
        for position in (0, -1, 10001, 2.5):
            with self.assertRaises(ValueError):
                app.DeviceInput(name='Invalid', host='127.0.0.1', circuit_position=position)


    def utilization_fixture(self):
        return ('                             L1 RX      L1 TX      L2 RX      L2 TX\n'
                'INTERFACE NAME               BANDWIDTH  BANDWIDTH  BANDWIDTH  BANDWIDTH\n'
                '-------------------------------------------------------------------------\n'
                'ten-gigabit-ethernet-1/1/11  2.5Gbps    162.1Mbps  2.4Gbps    151.4Mbps\n'
                'gigabit-ethernet-1/1/11     10Mbps     5Mbps      9Mbps      4Mbps\n'
                'ten-gigabit-ethernet-1/1/12  0bps       N/A        0bps       0bps')

    def test_supplied_utilization_output_keeps_l1_l2_and_physical_families(self):
        output = self.utilization_fixture()
        ten = app.utilization_values(app.port_lines('1/1/11', output, 'ten-gigabit-ethernet'))
        self.assertEqual((ten['rx_bps'], ten['tx_bps'], ten['l2_rx_bps'], ten['l2_tx_bps']),
                         (2_500_000_000, 162_100_000, 2_400_000_000, 151_400_000))
        giga = app.utilization_values(app.port_lines('1/1/11', output, 'gigabit-ethernet'))
        self.assertEqual((giga['rx_bps'], giga['tx_bps']), (10_000_000, 5_000_000))
        missing = app.utilization_values(app.port_lines('1/1/12', output, 'ten-gigabit-ethernet'))
        self.assertEqual((missing['rx_bps'], missing['tx_bps'], missing['l2_tx_bps']), (0, None, 0))

    def test_utilization_header_order_units_and_decimal_comma(self):
        output = ('     L2 TX    L1 TX    L2 RX    L1 RX\n'
                  'INTERFACE NAME  BANDWIDTH  BANDWIDTH  BANDWIDTH  BANDWIDTH\n'
                  'ten-gigabit-ethernet-1/1/11  9Kbps  162,1Mbps  1Gbps  2,5Gbps')
        values = app.utilization_values(output)
        self.assertEqual((values['rx_bps'], values['tx_bps'], values['l2_tx_bps']), (2.5e9, 162.1e6, 9000))
        self.assertEqual(app.utilization_values('RX: 10MBps')['rx_bps'], None)
        self.assertEqual(app.utilization_values('RX packets: 12345 TX bytes: 3000')['tx_bps'], None)
        self.assertEqual(app.utilization_values('1/1/11  200  100')['rx_bps'], None)

    def test_utilization_reads_once_and_keeps_only_selected_interfaces(self):
        d = app.create_device(app.DeviceInput(name='Mixed', host='192.0.2.9', kind='datacom', username='op',
            password='test-only', fingerprint='SHA256:'+'a'*43, interface_type='mixed',
            ports=['ten:1/1/11', 'giga:1/1/19']))
        with app.connect() as db:
            stored = dict(db.execute('SELECT * FROM devices WHERE id=?', (d['id'],)).fetchone())
        with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'ssh_read',
                side_effect=[*self.mixed_fixture(), self.utilization_fixture()]) as read:
            app.check_ssh(stored)
        self.assertEqual([call.args[1] for call in read.call_args_list],
                         ['show interface link', 'show interface transceivers', 'show interface utilization'])
        result = next(x for x in app.dashboard()['devices'] if x['id'] == d['id'])
        self.assertIsNone(result['ssh_error'])
        self.assertEqual(len(result['port_data']), 2)
        ten, giga = result['port_data']
        self.assertEqual((ten['rx'], ten['rx_bps'], ten['l2_tx_bps']), (-11, 2.5e9, 151.4e6))
        self.assertIsNone(giga['rx_bps'], 'Missing Giga19 cannot borrow the readings of Giga11')

    def test_rejected_utilization_does_not_hide_links_and_never_reuses_old_rates(self):
        ports = [dict(name='1/1/11', interface_type='ten-gigabit-ethernet', state='up', rx=-12, rx_bps=999)]
        with patch.object(app, 'ssh_read', return_value=self.utilization_fixture()):
            app.collect_utilization(Mock(), {}, ports)
        self.assertEqual(ports[0]['rx_bps'], 2.5e9)
        with patch.object(app, 'ssh_read', side_effect=app.CommandRejected('Comando de utilização rejeitado.')):
            app.collect_utilization(Mock(), {}, ports)
        self.assertEqual((ports[0]['state'], ports[0]['rx']), ('up', -12))
        self.assertIsNone(ports[0]['rx_bps'])
        self.assertEqual(ports[0]['utilization_output'], '')
        self.assertIn('rejeitado', ports[0]['utilization_error'])
        with patch.object(app, 'ssh_read') as read:
            app.collect_utilization(Mock(), {'utilization_command': ''}, ports)
        read.assert_not_called()
        self.assertFalse(ports[0]['utilization_enabled'])
        self.assertIsNone(ports[0]['utilization_error'])

    def test_ssh_utilization_failure_still_publishes_current_link_and_signal(self):
        d = app.create_device(app.DeviceInput(name='Datacom', host='192.0.2.9', kind='datacom', username='op',
            password='test-only', fingerprint='SHA256:'+'a'*43, interface_type='ten-gigabit-ethernet', ports=['1/1/11']))
        with app.connect() as db:
            stored = dict(db.execute('SELECT * FROM devices WHERE id=?', (d['id'],)).fetchone())
        with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'ssh_read', side_effect=[
                *self.mixed_fixture(), app.CommandRejected('O equipamento rejeitou show interface utilization.')]):
            app.check_ssh(stored)
        result = next(x for x in app.dashboard()['devices'] if x['id'] == d['id'])
        self.assertIsNone(result['ssh_error'])
        port = result['port_data'][0]
        self.assertEqual((port['state'], port['rx']), ('up', -11))
        self.assertIsNone(port['rx_bps'])
        self.assertIn('show interface utilization', port['utilization_error'])

    def test_ambiguous_utilization_does_not_reuse_or_cross_port_data(self):
        ports = [dict(name='1/1/11', interface_type='auto')]
        with patch.object(app, 'ssh_read', return_value=self.utilization_fixture()):
            app.collect_utilization(Mock(), {}, ports)
        self.assertIsNone(ports[0]['rx_bps'])
        self.assertIn('mais de um tipo', ports[0]['utilization_error'])

    def test_utilization_migration_and_older_clients_preserve_settings(self):
        with app.connect() as db:
            db.execute('ALTER TABLE devices DROP COLUMN utilization_command')
        app.init_db()
        self.assertEqual(self.device_state()['utilization_command'], 'show interface utilization')
        disabled = app.update_device(self.id, app.DeviceInput(name='Local', host='127.0.0.1', utilization_command=''))
        self.assertEqual(disabled['utilization_command'], '')
        kept = app.update_device(self.id, app.DeviceInput(name='Renamed', host='127.0.0.1'))
        self.assertEqual(kept['utilization_command'], '')
        for command in ('reboot', 'show interface utilization; reboot', 'show interface utilization {port}'):
            with self.assertRaises(ValueError):
                app.DeviceInput(name='Local', host='127.0.0.1', utilization_command=command)

    def mixed_fixture(self):
        status = ('Gigabit Ethernet Interfaces:\n'
                  '1/1/10 Down false - - - - - GIGA-10\n'
                  '1/1/19 Up false 1G full - - - GIGA-19\n'
                  '1/1/20 Down false - - - - - GIGA-20\n'
                  'TenGigabitEthernet Interfaces:\n'
                  '1/1/10 Up false 10G full - - - TEN-10\n'
                  '1/1/11 Up false 10G full - - - TEN-11\n'
                  '1/1/12 Down false - - - - - TEN-12\n'
                  'Hundred Gigabit Ethernet Interfaces:\n'
                  '1/1/10 Down false - - - - - HUNDRED-10')
        optics = ('gigabit-ethernet 1/1/10 | 40 C | 3 V | 10 mA | -2 dBm | -99 dBm\n'
                  'gigabit-ethernet 1/1/19 | 40 C | 3 V | 10 mA | -2 dBm | -19 dBm\n'
                  'gigabit-ethernet 1/1/20 | 40 C | 3 V | 10 mA | -2 dBm | -20 dBm\n'
                  'ten-gigabit-ethernet 1/1/10 | 40 C | 3 V | 10 mA | -6 dBm | -10 dBm\n'
                  'ten-gigabit-ethernet 1/1/11 | 40 C | 3 V | 10 mA | -6 dBm | -11 dBm\n'
                  'ten-gigabit-ethernet 1/1/12 | 40 C | 3 V | 10 mA | -6 dBm | -12 dBm')
        return status, optics

    def collect_mixed(self, device_id):
        with app.connect() as db:
            stored = dict(db.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone())
        with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'ssh_read', side_effect=self.mixed_fixture()):
            app.check_ssh(stored)
        return next(d for d in app.dashboard()['devices'] if d['id'] == device_id)

    def test_mixed_exact_user_selection_excludes_giga_ten_and_other_groups(self):
        d = app.create_device(app.DeviceInput(name='Mixed', host='192.0.2.9', kind='datacom', username='op',
            password='test-only', fingerprint='SHA256:'+'a'*43, interface_type='mixed',
            ports=['ten:1/1/10', 'ten:1/1/11', 'ten:1/1/12', 'giga:1/1/19', 'giga:1/1/20']))
        result = self.collect_mixed(d['id'])
        self.assertIsNone(result['ssh_error'])
        self.assertEqual({(p['interface_type'],p['name']) for p in result['port_data']},
            {('ten-gigabit-ethernet', '1/1/10'), ('ten-gigabit-ethernet', '1/1/11'),
             ('ten-gigabit-ethernet', '1/1/12'), ('gigabit-ethernet', '1/1/19'), ('gigabit-ethernet', '1/1/20')})
        ten = next(p for p in result['port_data'] if p['name']=='1/1/10')
        self.assertEqual((ten['state'], ten['rx'], ten['description']), ('up', -10, 'TEN-10'))
        alerts = app.dashboard()['alerts']
        self.assertEqual(len(alerts), 2)
        self.assertFalse(any('Porta Gigabit Ethernet 1/1/10' in a['message'] for a in alerts))
        self.assertFalse(any('Hundred' in a['message'] for a in alerts))

    def test_mixed_same_number_has_separate_names_signals_and_alerts(self):
        d = app.create_device(app.DeviceInput(name='Mixed', host='192.0.2.9', kind='datacom', username='op',
            password='test-only', fingerprint='SHA256:'+'a'*43, interface_type='mixed',
            ports=['ten:1/1/10', 'giga:1/1/10']))
        app.update_port_alias(d['id'], app.PortAliasInput(port='1/1/10', interface_type='ten-gigabit-ethernet', display_name='Ten principal'))
        app.update_port_alias(d['id'], app.PortAliasInput(port='1/1/10', interface_type='gigabit-ethernet', display_name='Giga reserva'))
        result = self.collect_mixed(d['id'])
        self.assertEqual(len({p['identity'] for p in result['port_data']}), 2)
        ports = {p['interface_type']:p for p in result['port_data']}
        self.assertEqual((ports['ten-gigabit-ethernet']['display_name'],ports['ten-gigabit-ethernet']['rx']), ('Ten principal', -10))
        self.assertEqual((ports['gigabit-ethernet']['display_name'],ports['gigabit-ethernet']['rx']), ('Giga reserva', -99))
        self.assertIn('Giga reserva', app.dashboard()['alerts'][0]['message'])
        self.collect_mixed(d['id'])
        self.assertEqual(len(app.dashboard()['alerts']), 1)

    def test_mixed_requires_typed_full_paths_and_general_commands(self):
        for ports in ([], ['1/1/10'], ['ten:10'], ['ten:1/1/10x'], ['hundred-gigabit-ethernet:1/1/10']):
            with self.subTest(ports=ports), self.assertRaises(app.HTTPException) as error:
                app.create_device(app.DeviceInput(name='Mixed', host='192.0.2.9', kind='datacom', username='op',
                    password='test-only', fingerprint='SHA256:'+'a'*43, interface_type='mixed', ports=ports))
            self.assertEqual(error.exception.status_code, 422)
        with self.assertRaises(app.HTTPException) as error:
            app.create_device(app.DeviceInput(name='Mixed', host='192.0.2.9', kind='datacom', username='op',
                password='test-only', fingerprint='SHA256:'+'a'*43, interface_type='mixed', ports=['ten:1/1/10'],
                status_command='show interface {port}'))
        self.assertIn('consultas gerais', error.exception.detail)
        with self.assertRaises(ValueError):
            app.PortAliasInput(port='1/1/10', interface_type='mixed', display_name='Ambiguous')

    def test_mixed_edit_preserves_position_password_and_existing_physical_alias(self):
        d = app.create_device(app.DeviceInput(name='Mixed', host='192.0.2.9', kind='datacom', username='op',
            password='test-only', fingerprint='SHA256:'+'a'*43, interface_type='ten-gigabit-ethernet',
            ports=['1/1/10'], circuit_position=3))
        app.update_port_alias(d['id'], app.PortAliasInput(port='1/1/10', interface_type='ten-gigabit-ethernet', display_name='Nome anterior'))
        updated = app.update_device(d['id'], app.DeviceInput(name='Mixed', host='192.0.2.9', kind='datacom', username='op',
            fingerprint='SHA256:'+'a'*43, interface_type='mixed', ports=['ten:1/1/10', 'giga:1/1/19']))
        self.assertEqual(updated['circuit_position'], 3)
        self.assertTrue(updated['has_password'])
        result = self.collect_mixed(d['id'])
        self.assertEqual(result['port_data'][0]['display_name'], 'Nome anterior')
        self.assertEqual(result['port_data'][1]['description'], 'GIGA-19')



if __name__ == '__main__':
    unittest.main()
