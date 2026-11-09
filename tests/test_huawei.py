import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app

STATUS11 = '''XGigabitEthernet0/0/11 current state : UP
Line protocol current state : UP
Description:BB-LIM-DM4050-TEN1
Last 300 seconds input rate 1037701192 bits/sec, 374211 packets/sec
Last 300 seconds output rate 9893036040 bits/sec, 1001545 packets/sec
Input peak rate 9996864928 bits/sec, Record time: 2026-09-08 10:36:56
Output peak rate 9999998808 bits/sec, Record time: 2026-10-27 00:06:43
Input: 255608205670 packets, 104956033381310 bytes
Output: 809864006102 packets, 998992349470885 bytes
Input bandwidth utilization threshold : 80.00%
Output bandwidth utilization threshold: 80.00%
Input bandwidth utilization : 10.38%
Output bandwidth utilization : 98.93%
'''
STATUS12 = '''XGigabitEthernet0/0/12 current state : DOWN
Line protocol current state : DOWN
Description:BB-LIM-DM4050-TEN2
Last 300 seconds input rate 0 bits/sec, 0 packets/sec
Last 300 seconds output rate 0 bits/sec, 0 packets/sec
Input peak rate 9977444376 bits/sec, Record time: 2026-09-02 23:49:25
Input bandwidth utilization : 0%
Output bandwidth utilization : 0%
'''
OPTICS11 = '''XGigabitEthernet0/0/11 transceiver information:
RX Power(dBM) : -23.10
RX Power High Warning(dBM) : -7.00
RX Power Low Warning(dBM) : -23.01
RX Power Low Threshold(dBM) : -23.98
TX Power(dBM) : 1.71
TX Power High Warning(dBM) : 5.00
TX Power Low Threshold(dBM) : -1.00
'''
OPTICS12 = '''XGigabitEthernet0/0/12 transceiver information:
RX Power(dBM) : -40.00
RX Power Low Threshold(dBM) : -26.02
TX Power(dBM) : 3.30
TX Power Low Threshold(dBM) : -2.00
Transceiver phony alarm : Yes
'''


class HuaweiTests(unittest.TestCase):
    def test_real_rates_and_optical_measurements_ignore_peaks_and_thresholds(self):
        p = app.parse_port('0/0/11', STATUS11, OPTICS11)
        self.assertEqual((p['state'], p['description']), ('up', 'BB-LIM-DM4050-TEN1'))
        self.assertEqual((p['rx'], p['tx']), (-23.1, 1.71))
        self.assertEqual((p['rx_bps'], p['tx_bps']), (1037701192, 9893036040))
        self.assertEqual((p['rx_percent'], p['tx_percent']), (10.38, 98.93))
        self.assertEqual(p['rate_window_seconds'], 300)
        p = app.parse_port('0/0/12', STATUS12, OPTICS12)
        self.assertEqual((p['state'], p['rx_bps'], p['tx_bps'], p['rx'], p['tx']), ('down', 0, 0, -40, 3.3))

    def test_missing_rates_and_wrong_interface_never_reuse_other_values(self):
        p = app.parse_port('0/0/12', STATUS11, OPTICS11)
        self.assertEqual(p['state'], 'unknown')
        self.assertIsNone(p['rx_bps'])
        self.assertIsNone(p['rx'])
        no_rate = '\n'.join(line for line in STATUS11.splitlines() if not line.startswith('Last '))
        p = app.parse_port('0/0/11', no_rate, OPTICS12)
        self.assertIsNone(p['rx_bps'])
        self.assertIsNone(p['tx_bps'])
        self.assertIsNone(p['rx'])

    def test_vrp_command_rejection_is_a_collection_error(self):
        from unittest.mock import MagicMock
        client = MagicMock()
        client.exec_command.return_value = (MagicMock(), MagicMock(), MagicMock())
        stdout, stderr = client.exec_command.return_value[1:]
        stdout.read.return_value = b"Error: Unrecognized command found at '^' position."
        stderr.read.return_value = b''
        stdout.channel.recv_exit_status.return_value = 0
        with self.assertRaises(app.CommandRejected):
            app.ssh_read(client, 'display interface XGigabitEthernet 0/0/11')

    def test_readonly_collection_and_conversion_keep_id_and_feed_port_history(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(app, 'DB', Path(temp) / 'monitor.db'):
            app.init_db()
            old = app.create_device(app.DeviceInput(name='Huawei', host='10.200.1.1'))
            configured = app.update_device(old['id'], app.DeviceInput(
                name='Huawei', host='10.200.1.1', kind='datacom', username='reader',
                password='test-only', fingerprint='SHA256:' + 'a' * 43,
                ports=['0/0/11', '0/0/12'], interface_type='ten-gigabit-ethernet',
                status_command='display interface XGigabitEthernet {port}',
                optics_command='display transceiver interface XGigabitEthernet {port} verbose',
                utilization_command=''))
            self.assertEqual(configured['id'], old['id'])
            with app.connect() as db:
                device = dict(db.execute('SELECT * FROM devices WHERE id=?', (old['id'],)).fetchone())
            outputs = {
                'display interface XGigabitEthernet 0/0/11': STATUS11,
                'display interface XGigabitEthernet 0/0/12': STATUS12,
                'display transceiver interface XGigabitEthernet 0/0/11 verbose': OPTICS11,
                'display transceiver interface XGigabitEthernet 0/0/12 verbose': OPTICS12,
            }
            with patch.object(app.paramiko, 'SSHClient') as client:
                commands = [
                    'display interface XGigabitEthernet 0/0/11',
                    'display transceiver interface XGigabitEthernet 0/0/11 verbose',
                    'display interface XGigabitEthernet 0/0/12',
                    'display transceiver interface XGigabitEthernet 0/0/12 verbose',
                ]
                channel = client.return_value.invoke_shell.return_value
                prompt = '<MANAUS-HUAWEI-S6730>'
                channel.recv.side_effect = [prompt.encode()] + [
                    (command + '\r\n' + outputs[command] + '\r\n' + prompt).encode()
                    for command in commands]
                app.check_ssh(device)
                client.return_value.invoke_shell.assert_called_once()
                client.return_value.exec_command.assert_not_called()
                self.assertEqual([call.args[0] for call in channel.sendall.call_args_list],
                                 [command + '\n' for command in commands])
            with app.connect() as db:
                row = db.execute('SELECT * FROM devices WHERE id=?', (old['id'],)).fetchone()
                self.assertIsNone(row['ssh_error'])
                ports = json.loads(row['port_data'])
                self.assertEqual([p['identity'] for p in ports], ['ten-gigabit-ethernet:0/0/11', 'ten-gigabit-ethernet:0/0/12'])
                self.assertEqual([p['rx_bps'] for p in ports], [1037701192, 0])
                self.assertTrue(all(p['utilization_enabled'] for p in ports))
                self.assertGreater(db.execute('SELECT COUNT(*) FROM port_traffic_series').fetchone()[0], 0)

            # A failed next collection retains only diagnostic text, not new metrics.
            with patch.object(app.paramiko, 'SSHClient'), patch.object(app.huawei_ssh, 'VRPReader') as terminal:
                terminal.return_value.read.side_effect = app.huawei_ssh.ReadTimeout('partial response')
                app.check_ssh(device)
            with app.connect() as db:
                failed = db.execute('SELECT * FROM devices WHERE id=?', (old['id'],)).fetchone()
                diagnostic = json.loads(failed['ssh_diagnostic'])
                self.assertIsNotNone(failed['ssh_error'])
                self.assertEqual(diagnostic['stage'], 'portas: 0/0/11')
                self.assertEqual(diagnostic['last_command'], commands[0])
                self.assertEqual(diagnostic['status_output'], 'partial response')
                self.assertEqual(diagnostic['transport'], 'terminal interativo VRP')
                self.assertEqual(json.loads(failed['port_data']), ports)
