import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

TEMP = tempfile.TemporaryDirectory()
os.environ['MONITOR_DATA_DIR'] = TEMP.name
import app
import remote_ping

SUCCESS = '''DC-POPAM# ping 10.91.0.2
PING 10.91.0.2 (10.91.0.2) 56(84) bytes of data.
64 bytes from 10.91.0.2: icmp_seq=1 ttl=64 time=6.51 ms
64 bytes from 10.91.0.2: icmp_seq=2 ttl=64 time=2.36 ms
64 bytes from 10.91.0.2: icmp_seq=3 ttl=64 time=2.17 ms
64 bytes from 10.91.0.2: icmp_seq=4 ttl=64 time=2.41 ms
64 bytes from 10.91.0.2: icmp_seq=5 ttl=64 time=2.58 ms

--- 10.91.0.2 ping statistics ---
5 packets transmitted, 5 received, 0% packet loss, time 4006ms
rtt min/avg/max/mdev = 2.169/3.204/6.505/1.655 ms
'''
LOSS = '''PING 10.91.0.2 (10.91.0.2) 56(84) bytes of data.
From 10.91.0.1 icmp_seq=1 Destination Host Unreachable
--- 10.91.0.2 ping statistics ---
5 packets transmitted, 0 received, +5 errors, 100% packet loss, time 4000ms
'''


class CircuitTests(unittest.TestCase):
    def setUp(self):
        app.init_db()
        app.STOP.clear()
        with app.connect() as db:
            for table in ('circuits', 'devices', 'alerts', 'samples'):
                db.execute(f'DELETE FROM {table}')
        self.parent = app.create_device(app.DeviceInput(name='DC-POPAM', host='192.0.2.10', kind='datacom',
            username='test-only', password='fake-test-only', fingerprint='SHA256:'+'a'*43))
        self.circuit = app.create_circuit(self.parent['id'], app.CircuitInput(name='Circuito Anori', host='10.91.0.2'))

    def stored(self):
        with app.connect() as db:
            return (dict(db.execute('SELECT * FROM circuits WHERE id=?', (self.circuit['id'],)).fetchone()),
                    dict(db.execute('SELECT * FROM devices WHERE id=?', (self.parent['id'],)).fetchone()))

    def record(self, text):
        circuit, parent = self.stored()
        app.record_circuit(circuit, parent, result=app.parse_remote_ping(circuit['host'], text), output=text)
        return self.stored()[0]

    def test_exact_user_output_has_five_successes_and_precise_average(self):
        result = self.record(SUCCESS)
        self.assertEqual((result['state'], result['failures'], result['transmitted'], result['received']), ('online', 0, 5, 5))
        self.assertEqual(result['latency'], 3.204)
        self.assertEqual(result['output'], SUCCESS)
        self.assertEqual(app.dashboard()['devices'][0]['circuits'][0]['host'], '10.91.0.2')
        self.assertNotIn('password', json.dumps(app.dashboard()['devices'][0]['circuits']))

    def test_packet_loss_threshold_counts_each_packet_not_each_command(self):
        for _ in range(4):
            result = self.record(LOSS)
        self.assertEqual((result['state'], result['failures']), ('unstable', 20))
        self.assertEqual(app.dashboard()['alerts'], [])
        result = self.record(LOSS)
        self.assertEqual((result['state'], result['failures']), ('offline', 25))
        self.assertEqual(len(app.dashboard()['alerts']), 1)
        self.record(LOSS)
        self.assertEqual(len(app.dashboard()['alerts']), 1)
        self.assertIn('Circuito Anori', app.dashboard()['alerts'][0]['message'])
        self.record(SUCCESS)
        self.assertEqual(self.stored()[0]['failures'], 0)
        self.assertEqual(app.dashboard()['alerts'][0]['level'], 'success')

    def test_interleaved_replies_reset_only_the_actual_consecutive_losses(self):
        for _ in range(4):
            self.record(LOSS)
        partial = '\n'.join([line for line in SUCCESS.splitlines() if not line.startswith('64 bytes') or 'icmp_seq=2 ' in line or 'icmp_seq=4 ' in line])
        partial = partial.replace('5 received, 0%', '2 received, 60%')
        result = self.record(partial)
        self.assertEqual((result['state'], result['failures']), ('unstable', 1))
        self.assertEqual([e['level'] for e in app.dashboard()['alerts']], ['success', 'critical'])

    def test_collector_uses_parent_credentials_and_never_pings_from_local_host(self):
        circuit, parent = self.stored()
        with patch.object(app.paramiko, 'SSHClient') as factory, patch.object(app, 'read_remote_ping', return_value=SUCCESS) as read, patch.object(app, 'ping') as local:
            app.check_circuit(circuit, parent)
        local.assert_not_called()
        self.assertEqual(factory.return_value.connect.call_args.args[0], '192.0.2.10')
        self.assertEqual(factory.return_value.connect.call_args.kwargs['password'], 'fake-test-only')
        self.assertFalse(factory.return_value.connect.call_args.kwargs['look_for_keys'])
        policy = factory.return_value.set_missing_host_key_policy.call_args.args[0]
        self.assertIsInstance(policy, app.VerifyFingerprint)
        self.assertEqual(policy.expected, parent['fingerprint'])
        self.assertEqual(read.call_args.args[1], '10.91.0.2')
        factory.return_value.close.assert_called_once()
        self.assertEqual(self.stored()[0]['state'], 'online')

    def test_ssh_authentication_failure_is_not_a_missing_echo(self):
        self.record(LOSS)
        for _ in range(2):
            circuit, parent = self.stored()
            with patch.object(app.paramiko, 'SSHClient') as factory:
                factory.return_value.connect.side_effect = app.paramiko.AuthenticationException
                app.check_circuit(circuit, parent)
        circuit, _ = self.stored()
        self.assertEqual((circuit['state'], circuit['failures']), ('error', 5))
        self.assertIsNone(circuit['transmitted'])
        self.assertEqual(len(app.dashboard()['alerts']), 1)
        self.assertIn('Autenticação', circuit['error'])

    def test_unrecognized_output_is_an_error_and_keeps_diagnostic(self):
        circuit, parent = self.stored()
        with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'read_remote_ping', return_value='syntax error: unknown command'):
            app.check_circuit(circuit, parent)
        stored, _ = self.stored()
        self.assertEqual((stored['state'], stored['failures']), ('error', 0))
        self.assertIn('syntax error', stored['output'])

    def test_editing_destination_discards_inflight_results_and_clears_old_readings(self):
        circuit, parent = self.stored()
        app.update_circuit(circuit['id'], app.CircuitInput(name='Outro circuito', host='10.91.0.3'))
        app.record_circuit(circuit, parent, result=app.parse_remote_ping('10.91.0.2', SUCCESS), output=SUCCESS)
        latest, _ = self.stored()
        self.assertEqual((latest['host'], latest['state'], latest['output']), ('10.91.0.3', 'pending', ''))

    def test_changing_source_clears_circuit_results_and_rejects_old_probe(self):
        self.record(SUCCESS)
        circuit, parent = self.stored()
        values = {**self.parent, 'host': '192.0.2.11'}
        updated = app.update_device(self.parent['id'], app.DeviceInput(**values))
        self.assertEqual(updated['circuits'][0]['state'], 'pending')
        self.assertEqual(updated['circuits'][0]['output'], '')
        self.assertEqual(updated['circuits'][0]['failures'], 0)
        app.record_circuit(circuit, parent, result=app.parse_remote_ping('10.91.0.2', SUCCESS), output=SUCCESS)
        self.assertEqual(self.stored()[0]['state'], 'pending')

    def test_metadata_edit_preserves_telemetry_and_old_clients_preserve_circuits(self):
        self.record(SUCCESS)
        edited = app.update_circuit(self.circuit['id'], app.CircuitInput(name='Circuito renomeado', host='10.91.0.2', interval=60))
        self.assertEqual((edited['state'], edited['latency']), ('online', 3.204))
        parent = app.update_device(self.parent['id'], app.DeviceInput(**{**self.parent, 'circuit_position': 2.1}))
        self.assertEqual(parent['circuits'][0]['name'], 'Circuito renomeado')
        self.assertEqual(parent['circuits'][0]['state'], 'online')
        self.assertTrue(parent['has_password'])

    def test_duplicates_are_scoped_to_source_and_cannot_reassign_source(self):
        with self.assertRaises(app.HTTPException) as error:
            app.create_circuit(self.parent['id'], app.CircuitInput(name='Dup', host='10.91.0.2'))
        self.assertEqual(error.exception.status_code, 409)
        parent2 = app.create_device(app.DeviceInput(name='Outro Datacom', host='192.0.2.12', kind='datacom', username='test', password='fake', fingerprint='SHA256:'+'a'*43))
        added = app.create_circuit(parent2['id'], app.CircuitInput(name='Outra rota', host='10.91.0.2'))
        self.assertEqual(added['source_device_id'], parent2['id'])
        bbu = app.create_device(app.DeviceInput(name='BBU', host='192.0.2.13'))
        with self.assertRaises(app.HTTPException) as error:
            app.create_circuit(bbu['id'], app.CircuitInput(name='Circuito', host='10.91.0.4'))
        self.assertEqual(error.exception.status_code, 422)

    def test_parent_conversion_is_guarded_and_delete_cascades_but_keeps_events(self):
        with self.assertRaises(app.HTTPException) as error:
            app.update_device(self.parent['id'], app.DeviceInput(name='BBU', host=self.parent['host']))
        self.assertEqual(error.exception.status_code, 422)
        for _ in range(5):
            self.record(LOSS)
        app.delete_device(self.parent['id'])
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM circuits').fetchone()[0], 0)
        self.assertEqual(len(app.dashboard()['alerts']), 1)

    def test_manual_test_schedules_without_blocking_or_opening_ssh(self):
        self.record(SUCCESS)
        with patch.object(app.paramiko, 'SSHClient') as ssh:
            app.request_circuit_check(self.circuit['id'])
        ssh.assert_not_called()
        self.assertEqual((self.stored()[0]['last_poll'], self.stored()[0]['state']), (0, 'online'))

    def test_restart_preserves_circuits_and_encrypted_credentials(self):
        circuit, parent = self.stored()
        app.init_db()
        after, source = self.stored()
        self.assertEqual(after, circuit)
        self.assertEqual(source['password'], parent['password'])
        app.delete_circuit(circuit['id'])
        self.assertEqual(app.dashboard()['devices'][0]['circuits'], [])
        with self.assertRaises(app.HTTPException):
            app.request_circuit_check(circuit['id'])

    def test_queued_probe_does_not_connect_after_configuration_changes(self):
        circuit, parent = self.stored()
        app.update_circuit(circuit['id'], app.CircuitInput(name='Novo destino', host='10.91.0.3'))
        with patch.object(app.paramiko, 'SSHClient') as ssh:
            app.check_circuit(circuit, parent)
        ssh.assert_not_called()

    def test_stopping_monitor_skips_queued_remote_checks(self):
        circuit, parent = self.stored()
        key = (circuit['id'], 'circuit')
        app.INFLIGHT.add(key)
        app.STOP.set()
        try:
            with patch.object(app, 'check_circuit') as check:
                app.run_circuit_check(circuit, parent)
            check.assert_not_called()
            self.assertNotIn(key, app.INFLIGHT)
        finally:
            app.STOP.clear()

    def test_host_and_interval_validation_blocks_command_injection(self):
        for host in ['10.91.0.2; reboot','10.91.0.2\nreboot','example.com','10.91.0.2 -c 10000','']:
            with self.subTest(host=host), self.assertRaises(ValueError):
                app.CircuitInput(name='Circuito', host=host)
        for interval in (0, 1, 9, 301):
            with self.assertRaises(ValueError):
                app.CircuitInput(name='Circuito', host='10.91.0.2', interval=interval)


class RemoteTransportTests(unittest.TestCase):
    def test_invalid_or_contradictory_results_never_become_packet_loss(self):
        for output in [SUCCESS.replace('PING 10.91.0.2 (10.91.0.2)', 'PING 10.91.0.3 (10.91.0.3)'),
                       SUCCESS.replace('icmp_seq=5','icmp_seq=99'), 'syntax error', LOSS.replace('5 packets','0 packets')]:
            with self.subTest(output=output[:40]), self.assertRaises(app.RemotePingError):
                app.parse_remote_ping('10.91.0.2', output)

    def test_absolute_deadline_closes_remote_channel(self):
        client, stdout = Mock(), Mock()
        client.exec_command.return_value = (None, stdout, None)
        with patch.object(remote_ping.time, 'monotonic', side_effect=[100, 146]):
            with self.assertRaises(app.RemotePingError):
                app.read_remote_ping(client, '10.91.0.2')
        self.assertEqual(client.exec_command.call_args.args[0], 'ping 10.91.0.2')
        stdout.channel.close.assert_called_once()

    def test_ping_exit_one_with_valid_loss_summary_is_allowed(self):
        client, stdout = Mock(), Mock()
        client.exec_command.return_value = (None, stdout, None)
        channel = stdout.channel
        channel.recv_ready.side_effect = [True, False]
        channel.recv_stderr_ready.return_value = False
        channel.exit_status_ready.return_value = True
        channel.recv.return_value = LOSS.encode()
        channel.recv_exit_status.return_value = 1
        output = app.read_remote_ping(client, '10.91.0.2')
        self.assertEqual(app.parse_remote_ping('10.91.0.2', output)['probes'], [False]*5)
        channel.close.assert_called_once()

    def test_cancel_closes_remote_channel(self):
        client, stdout = Mock(), Mock()
        client.exec_command.return_value = (None, stdout, None)
        with self.assertRaises(app.RemotePingError):
            app.read_remote_ping(client, '10.91.0.2', cancelled=lambda: True)
        stdout.channel.close.assert_called_once()
