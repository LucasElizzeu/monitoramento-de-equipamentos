import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ.setdefault('MONITOR_DATA_DIR', TEMP.name)
import app
import siae

TABLE = {'Err': 0, 'Indx': 0, 'More': 0, 'val': [
    ['3', 3, 881684355, 3465228286, 1083758542, 1140223, 350189, 40230405, 7604212, 15870598, 64046],
    ['5', 5, 4289395679, 3042466562, 13870204, 5214358, 16, 2989707440, 3688238115, 137679406, 10]]}


class SiaeProtocolTests(unittest.TestCase):
    def test_observed_response_maps_received_octets_and_not_packets(self):
        self.assertEqual(siae.parse_table(TABLE, [3]), {3: {'rx_octets': 881684355, 'tx_octets': 40230405}})
        self.assertEqual(len(siae.parse_table(TABLE, [3, 5])), 2)

    def test_invalid_partial_duplicate_or_missing_rows_are_rejected(self):
        for payload in ({'Err': 1}, dict(TABLE, More=1), dict(TABLE, val=TABLE['val'] * 2),
                        dict(TABLE, val=[['3', 4] + TABLE['val'][0][2:]]), dict(TABLE, val=[])):
            with self.subTest(payload=payload), self.assertRaises(siae.SiaeError):
                siae.parse_table(payload, [3])

    def test_unsigned_32bit_counter_validation(self):
        for value in (-1, 2**32, 1.5, True, None):
            payload = json.loads(json.dumps(TABLE))
            payload['val'][0][2] = value
            with self.subTest(value=value), self.assertRaises(siae.SiaeError):
                siae.parse_table(payload, [3])

    def test_rate_is_bytes_difference_times_eight_over_elapsed_seconds(self):
        old = {3: {'rx_octets': 100000000, 'tx_octets': 100}}
        new = {3: {'rx_octets': 130000000, 'tx_octets': 200}}
        rates, note = siae.calculate_rates(old, new, 2)
        self.assertEqual(rates[3]['rx_bps'], 120e6)
        self.assertIsNone(note)
        self.assertEqual(siae.calculate_rates(old, old, 2)[0][3]['rx_bps'], 0)

    def test_counter_reset_wrap_or_long_gap_rebaseline_without_false_spike(self):
        high = {3: {'rx_octets': 2**32 - 1, 'tx_octets': 100}}
        low = {3: {'rx_octets': 1000, 'tx_octets': 200}}
        self.assertIsNone(siae.calculate_rates(high, low, 2)[0])
        for seconds in (0, -1, 11, float('nan')):
            with self.subTest(seconds=seconds):
                self.assertIsNone(siae.calculate_rates(low, low, seconds)[0])

    def test_tx_wrap_does_not_hide_valid_rx_consumption(self):
        old = {3: {'rx_octets': 100, 'tx_octets': 2**32 - 1}}
        new = {3: {'rx_octets': 110, 'tx_octets': 5}}
        rates, _ = siae.calculate_rates(old, new, 2)
        self.assertEqual(rates[3], {'rx_bps': 40, 'tx_bps': None})

    def test_transport_sends_observed_read_only_payload_and_does_not_leak_session(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(TABLE).encode()
        with patch.object(siae, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            values = siae.read_counters('192.0.2.70', 'http', 80, 'unit-test-session', [3])
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, 'http://192.0.2.70/Snmp.GetTable')
        self.assertEqual(request.method, 'POST')
        self.assertEqual(json.loads(request.data), {'Id': 'unit-test-session', 'rad': '1.3.6.1.2.1.2.2.1',
            'lea': ['1', '10', '11', '12', '13', '14', '16', '17', '18', '19']})
        self.assertNotIn('session', str(values))

    def test_http_auth_error_and_redirect_do_not_echo_secrets(self):
        from urllib.error import HTTPError
        with patch.object(siae, 'build_opener') as opener:
            opener.return_value.open.side_effect = HTTPError('http://example.invalid', 401, 'private-value', {}, None)
            with self.assertRaises(siae.SiaeError) as error:
                siae.read_counters('192.0.2.70', 'http', 80, 'unit-test-session', [3])
        self.assertIn('expirada', str(error.exception))
        self.assertNotIn('private-value', str(error.exception))
        with self.assertRaises(siae.SiaeError):
            siae.NoRedirect().redirect_request(None, None, 302, '', {}, 'http://example.invalid')

    def test_oversized_and_html_login_responses_are_rejected(self):
        from unittest.mock import MagicMock
        for body in (b'x' * (siae.MAX_RESPONSE + 1), b'<html>Login</html>'):
            response = MagicMock()
            response.__enter__.return_value.read.return_value = body
            with patch.object(siae, 'build_opener') as opener:
                opener.return_value.open.return_value = response
                with self.assertRaises(siae.SiaeError):
                    siae.read_counters('192.0.2.70', 'http', 80, 'unit-test-session', [3])

    def test_ipv6_and_https_use_configured_origin(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(TABLE).encode()
        with patch.object(siae, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            siae.read_counters('2001:db8::1', 'https', 8443, 'unit-test-session', [3])
        self.assertEqual(opener.return_value.open.call_args.args[0].full_url,
                         'https://[2001:db8::1]:8443/Snmp.GetTable')

    def test_session_can_be_copied_as_a_json_string(self):
        entry = app.DeviceInput(name='Rádio', host='192.0.2.70', kind='siae', siae_session=' "unit-test-session" ')
        self.assertEqual(entry.siae_session, 'unit-test-session')


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
        app.SIAE_BASELINES.clear()
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

    def enable(self, indices=None):
        app.update_device(self.radio['id'], app.DeviceInput(name=self.radio['name'], host=self.radio['host'],
            kind='siae', siae_enabled=True, siae_session='unit-test-session', siae_interfaces=indices or [3]))
        return self.raw()

    def raw(self):
        with app.connect() as db:
            return dict(db.execute('SELECT * FROM devices WHERE id=?', (self.radio['id'],)).fetchone())

    def test_session_is_encrypted_and_omitted_in_dashboard_and_preserved_on_old_client_edit(self):
        raw = self.enable()
        self.assertNotEqual(raw['siae_session'], 'unit-test-session')
        self.assertEqual(app.CIPHER.decrypt(raw['siae_session'].encode()).decode(), 'unit-test-session')
        self.assertTrue(self.current()['has_siae_session'])
        self.assertNotIn('siae_session', self.current())
        self.assertNotIn('unit-test-session', json.dumps(app.dashboard()))
        app.update_device(self.radio['id'], app.DeviceInput(name='Renomeado', host=self.radio['host'], kind='siae'))
        self.assertEqual(self.raw()['siae_session'], raw['siae_session'])
        self.assertEqual(self.current()['siae_enabled'], 1)

    def test_enabled_collection_needs_session_and_same_session_cannot_move_to_another_host(self):
        with self.assertRaises(app.HTTPException):
            app.update_device(self.radio['id'], app.DeviceInput(name='Rádio', host=self.radio['host'], kind='siae', siae_enabled=True))
        raw = self.enable()
        for changes in ({'host': '192.0.2.71'}, {'siae_scheme': 'https'}, {'siae_port': 8080}):
            with self.subTest(changes=changes), self.assertRaises(app.HTTPException):
                app.update_device(self.radio['id'], app.DeviceInput(**dict(
                    dict(name='Rádio', host=self.radio['host'], kind='siae'), **changes)))
        self.assertEqual(self.raw()['siae_session'], raw['siae_session'])

    def test_aggregate_interface_requires_two_samples_and_does_not_invent_a_b_values(self):
        raw = self.enable()
        counters = [{3: {'rx_octets': 100000000, 'tx_octets': 100}},
                    {3: {'rx_octets': 130000000, 'tx_octets': 200}}]
        with patch.object(app, 'read_counters', side_effect=counters), patch.object(app.time, 'monotonic', side_effect=[10, 12]):
            app.check_siae(raw)
            self.assertEqual(self.current()['siae_consumption']['status'], 'warming_up')
            app.check_siae(raw)
        values = self.current()['siae_consumption']
        self.assertEqual(values['total_bps'], 120e6)
        self.assertIsNone(values['trx_a_bps'])
        self.assertIsNone(values['trx_b_bps'])
        self.assertEqual(self.current()['failures'], 0)

    def test_separate_interfaces_sum_rx_and_do_not_add_tx(self):
        raw = self.enable([3, 5])
        before = {3: {'rx_octets': 0, 'tx_octets': 0}, 5: {'rx_octets': 0, 'tx_octets': 0}}
        after = {3: {'rx_octets': 30000000, 'tx_octets': 100000}, 5: {'rx_octets': 20000000, 'tx_octets': 100000}}
        with patch.object(app, 'read_counters', side_effect=[before, after]), patch.object(app.time, 'monotonic', side_effect=[10, 12]):
            app.check_siae(raw)
            app.check_siae(raw)
        self.assertEqual(self.current()['siae_consumption']['total_bps'], 200e6)
        self.assertEqual(self.current()['siae_consumption']['trx_a_bps'], 120e6)
        self.assertEqual(self.current()['siae_consumption']['trx_b_bps'], 80e6)
        with self.assertRaises(ValueError):
            app.DeviceInput(name='Rádio', host=self.radio['host'], kind='siae', siae_interfaces=[3, 3])

    def test_error_clears_stale_bandwidth_without_ping_loss_and_recovers_after_new_baseline(self):
        raw = self.enable()
        before = {3: {'rx_octets': 0, 'tx_octets': 0}}
        after = {3: {'rx_octets': 30000000, 'tx_octets': 100000}}
        with patch.object(app, 'read_counters', side_effect=[before, after]), patch.object(app.time, 'monotonic', side_effect=[10, 12]):
            app.check_siae(raw)
            app.check_siae(raw)
        with patch.object(app, 'read_counters', side_effect=siae.SiaeError('Sessão expirada.')):
            app.check_siae(raw)
            app.check_siae(raw)
        values = self.current()['siae_consumption']
        self.assertEqual(values['status'], 'error')
        self.assertIsNone(values['total_bps'])
        self.assertEqual(self.current()['failures'], 0)
        self.assertEqual(len(app.dashboard()['alerts']), 1)
        with patch.object(app, 'read_counters', side_effect=[before, after]), patch.object(app.time, 'monotonic', side_effect=[20, 22]):
            app.check_siae(raw)
            app.check_siae(raw)
        self.assertEqual([e['level'] for e in app.dashboard()['alerts']], ['success', 'warning'])

    def test_edited_or_deleted_radio_discards_inflight_result_and_stale_job_does_not_connect(self):
        raw = self.enable()
        def edit_during_read(*args):
            app.update_device(self.radio['id'], app.DeviceInput(name='Alterado', host=self.radio['host'], kind='siae'))
            return {3: {'rx_octets': 1, 'tx_octets': 1}}
        with patch.object(app, 'read_counters', side_effect=edit_during_read):
            app.check_siae(raw)
        self.assertEqual(self.raw()['siae_data'], '{}')
        with patch.object(app, 'read_counters') as read:
            app.check_siae(raw)
        read.assert_not_called()
        raw = self.raw()
        def delete_during_read(*args):
            app.delete_device(self.radio['id'])
            return {3: {'rx_octets': 1, 'tx_octets': 1}}
        with patch.object(app, 'read_counters', side_effect=delete_during_read):
            app.check_siae(raw)
        self.assertEqual(app.dashboard()['devices'], [])


if __name__ == '__main__':
    unittest.main()
