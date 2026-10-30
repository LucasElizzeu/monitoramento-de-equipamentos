import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TEMP = tempfile.TemporaryDirectory()
os.environ.setdefault('MONITOR_DATA_DIR', TEMP.name)
import app
import siae


class LoginProtocolTests(unittest.TestCase):
    def response(self, payload):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        return response

    def test_observed_login_endpoint_and_credential_field_names(self):
        # The success body is a simulated contract; the physical radio's body
        # has not yet been captured. Only a valid Id can proceed to a read.
        with patch.object(siae, 'build_opener') as opener:
            opener.return_value.open.return_value = self.response({'Err': 0, 'Id': 'simulated-session'})
            result = siae.login('192.0.2.70', 'http', 8080, 'test-user', 'test-password')
        self.assertEqual(result, 'simulated-session')
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, 'http://192.0.2.70:8080/Log.Login')
        self.assertEqual(request.method, 'POST')
        self.assertEqual(json.loads(request.data), {'Usr': 'test-user', 'Pwd': 'test-password'})
        self.assertNotIn('test-password', request.full_url)

    def test_unknown_rejected_or_missing_session_never_succeeds_or_echoes_values(self):
        for payload in ({'Err': 1, 'Id': 'sensitive-value'}, {'Err': '0', 'Id': 'sensitive-value'},
                        {'val': 'sensitive-value'}, {'Id': ''}, {'Id': 123}, {'Id': 'invalid value'},
                        {'Id': 'x' * 513}, ['sensitive-value']):
            with self.subTest(payload=payload), patch.object(siae, 'post_json', return_value=payload):
                with self.assertRaises(siae.SiaeError) as error:
                    siae.login('192.0.2.70', 'http', 80, 'test-user', 'test-password')
                self.assertNotIn('sensitive-value', str(error.exception))
                self.assertNotIn('test-password', str(error.exception))

    def test_auth_rejection_is_distinct_from_invalid_table(self):
        with self.assertRaises(siae.SiaeSessionError):
            siae.parse_table({'Err': 1}, [3])
        for payload in ({'Err': 0, 'More': 1}, {'Err': '0'}, {}):
            with self.assertRaises(siae.SiaeError) as error:
                siae.parse_table(payload, [3])
            self.assertNotIsInstance(error.exception, siae.SiaeSessionError)

    def test_login_http_errors_and_redirect_never_forward_credentials(self):
        from urllib.error import HTTPError
        for code in (401, 403, 500):
            with patch.object(siae, 'build_opener') as opener:
                opener.return_value.open.side_effect = HTTPError('http://192.0.2.70', code, 'private-value', {}, None)
                with self.assertRaises(siae.SiaeError) as error:
                    siae.login('192.0.2.70', 'http', 80, 'test-user', 'test-password')
                self.assertNotIn('private-value', str(error.exception))
        with self.assertRaises(siae.SiaeError):
            siae.NoRedirect().redirect_request(None, None, 307, '', {}, 'http://example.invalid')


class AutomaticLoginTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        db_patch = patch.object(app, 'DB', Path(directory.name) / 'monitor.db')
        db_patch.start()
        self.addCleanup(db_patch.stop)
        app.init_db()
        app.SIAE_BASELINES.clear()
        self.radio = app.create_device(app.DeviceInput(**self.values()))
        self.device_id = self.radio['id']

    def values(self, **changes):
        return dict(dict(name='SIAE teste', host='192.0.2.70', kind='siae', siae_enabled=True,
                         siae_auth_mode='login', siae_username='test-user', siae_password='test-password'), **changes)

    def raw(self):
        with app.connect() as db:
            return dict(db.execute('SELECT * FROM devices WHERE id=?', (self.device_id,)).fetchone())

    def edit(self, **changes):
        return app.update_device(self.device_id, app.DeviceInput(**self.values(siae_password='', **changes)))

    def counters(self, value=100):
        return {3: {'rx_octets': value, 'tx_octets': 20}}

    def check(self):
        app.check_siae(self.raw())

    def test_password_encrypted_and_never_returned_or_copied_to_other_destination(self):
        raw = self.raw()
        self.assertNotEqual(raw['siae_password'], 'test-password')
        self.assertEqual(app.CIPHER.decrypt(raw['siae_password'].encode()).decode(), 'test-password')
        self.assertTrue(self.radio['has_siae_password'])
        self.assertNotIn('siae_password', self.radio)
        self.assertNotIn('test-password', json.dumps(app.dashboard()))
        self.edit(name='Renomeado')
        self.assertEqual(self.raw()['siae_password'], raw['siae_password'])
        for change in ({'host': '192.0.2.71'}, {'siae_port': 8080}, {'siae_scheme': 'https'}, {'siae_username': 'other-user'}):
            with self.subTest(change=change), self.assertRaises(app.HTTPException):
                self.edit(**change)

    def test_missing_credential_is_rejected_and_old_client_edits_keep_saved_login(self):
        for change in ({'siae_username': ''}, {'siae_password': ''}):
            with self.subTest(change=change), self.assertRaises(app.HTTPException):
                app.create_device(app.DeviceInput(**self.values(host='192.0.2.71', **change)))
        raw = self.raw()
        app.update_device(self.device_id, app.DeviceInput(name='Cliente antigo', host=raw['host'], kind='siae'))
        self.assertEqual(self.raw()['siae_auth_mode'], 'login')
        self.assertEqual(self.raw()['siae_password'], raw['siae_password'])

    def test_first_login_session_reuse_and_two_samples_for_bandwidth(self):
        stale_snapshot = self.raw()
        with patch.object(app, 'siae_login', return_value='simulated-session') as login, \
             patch.object(app, 'read_counters', side_effect=[self.counters(100), self.counters(30000100)]) as read, \
             patch.object(app.time, 'monotonic', side_effect=[10, 12]):
            app.check_siae(stale_snapshot)
            self.assertEqual(app.dashboard()['devices'][0]['siae_consumption']['status'], 'warming_up')
            # Runtime renewal doesn't bump config_version; even an older job
            # snapshot must use the latest saved session instead of logging in.
            app.check_siae(stale_snapshot)
        login.assert_called_once_with('192.0.2.70', 'http', 80, 'test-user', 'test-password')
        self.assertEqual(read.call_args.args[3], 'simulated-session')
        public = app.dashboard()['devices'][0]
        self.assertEqual(public['siae_consumption']['total_bps'], 120e6)
        self.assertNotIn('simulated-session', json.dumps(public))
        self.assertEqual(app.CIPHER.decrypt(self.raw()['siae_session'].encode()).decode(), 'simulated-session')

    def test_expiration_renews_once_and_rebaselines_without_false_traffic(self):
        with patch.object(app, 'siae_login', return_value='first-session'), patch.object(app, 'read_counters', return_value=self.counters()):
            self.check()
        with patch.object(app, 'siae_login', return_value='renewed-session') as login, patch.object(app, 'read_counters',
                side_effect=[siae.SiaeSessionError('Expirada'), self.counters(9000000)]) as read:
            self.check()
        login.assert_called_once()
        self.assertEqual(read.call_count, 2)
        self.assertEqual(app.dashboard()['devices'][0]['siae_consumption']['status'], 'warming_up')
        self.assertEqual(app.CIPHER.decrypt(self.raw()['siae_session'].encode()).decode(), 'renewed-session')

    def test_rejected_login_or_session_does_not_loop_or_count_ping_loss(self):
        for login_result in (siae.SiaeError('Login recusado'), 'simulated-session'):
            with patch.object(app, 'siae_login', **({'side_effect': login_result} if isinstance(login_result, Exception)
                    else {'return_value': login_result})) as login, patch.object(app, 'read_counters',
                    side_effect=siae.SiaeSessionError('Sessão recusada')) as read:
                self.check()
            self.assertEqual(login.call_count, 1)
            self.assertLessEqual(read.call_count, 1)
            public = app.dashboard()['devices'][0]
            self.assertEqual(public['failures'], 0)
            self.assertIsNone(public['siae_consumption']['total_bps'])
            self.assertEqual(public['siae_consumption']['status'], 'error')
            self.assertFalse(public['has_siae_session'])

    def test_table_errors_do_not_trigger_unnecessary_reauthentication(self):
        with patch.object(app, 'siae_login', return_value='first-session'), patch.object(app, 'read_counters', return_value=self.counters()):
            self.check()
        with patch.object(app, 'siae_login') as login, patch.object(app, 'read_counters', side_effect=siae.SiaeError('Tabela incompleta')):
            self.check()
        login.assert_not_called()

    def test_credential_change_clears_session_and_manual_mode_removes_saved_password(self):
        with patch.object(app, 'siae_login', return_value='first-session'), patch.object(app, 'read_counters', return_value=self.counters()):
            self.check()
        app.update_device(self.device_id, app.DeviceInput(**self.values(siae_password='replacement-test-password')))
        self.assertEqual(self.raw()['siae_session'], '')
        self.assertEqual(app.CIPHER.decrypt(self.raw()['siae_password'].encode()).decode(), 'replacement-test-password')
        self.edit(siae_auth_mode='session', siae_session='manual-test-session')
        self.assertEqual(self.raw()['siae_password'], '')
        with patch.object(app, 'siae_login') as login, patch.object(app, 'read_counters', side_effect=siae.SiaeSessionError('Expirada')):
            self.check()
        login.assert_not_called()

    def test_inflight_login_cannot_overwrite_newer_configuration_or_deleted_device(self):
        def edit_during_login(*args):
            self.edit(siae_enabled=False)
            return 'stale-session'
        with patch.object(app, 'siae_login', side_effect=edit_during_login), patch.object(app, 'read_counters', return_value=self.counters()):
            self.check()
        self.assertEqual(self.raw()['siae_session'], '')
        self.assertEqual(self.raw()['siae_data'], '{}')
        self.edit(siae_enabled=True)
        def delete_during_login(*args):
            app.delete_device(self.device_id)
            return 'stale-session'
        with patch.object(app, 'siae_login', side_effect=delete_during_login), patch.object(app, 'read_counters', return_value=self.counters()):
            self.check()
        self.assertEqual(app.dashboard()['devices'], [])


if __name__ == '__main__':
    unittest.main()
