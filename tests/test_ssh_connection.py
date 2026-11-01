import os,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
TEMP=tempfile.TemporaryDirectory()
os.environ.setdefault('MONITOR_DATA_DIR',TEMP.name)
import app

class SSHConnectionTests(unittest.TestCase):
    def test_connection_failures_are_distinct_and_never_echo_password_or_exception_body(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(app,'DB',Path(temp)/'monitor.db'):
            app.init_db()
            device=app.create_device(app.DeviceInput(name='Datacom',host='192.0.2.99',kind='datacom',username='op',password='secret-test-only',fingerprint='SHA256:'+'a'*43))
            with app.connect() as db:
                stored=dict(db.execute('SELECT * FROM devices WHERE id=?',(device['id'],)).fetchone())
            cases=[(app.paramiko.AuthenticationException('secret-test-only'),'AuthenticationException'),(app.InvalidToken(),'InvalidToken'),(app.paramiko.ssh_exception.IncompatiblePeer('secret-test-only'),'IncompatiblePeer'),(TimeoutError('secret-test-only'),'TimeoutError'),(app.paramiko.SSHException('secret-test-only'),'SSHException')]
            for failure,kind in cases:
                with self.subTest(kind=kind),patch.object(app.paramiko,'SSHClient') as client,patch.object(app,'ssh_read') as read:
                    client.return_value.connect.side_effect=failure
                    app.check_ssh(stored)
                    result=app.dashboard()['devices'][0]
                    self.assertEqual(result['ssh_diagnostic']['error_type'],kind)
                    self.assertEqual(result['ssh_diagnostic']['stage'],'conexão SSH')
                    self.assertNotIn('secret-test-only',json.dumps(result))
                    read.assert_not_called()
                    client.return_value.close.assert_called_once()

    def test_mismatch_reports_observed_fingerprint_and_still_rejects_key(self):
        key=app.paramiko.RSAKey.generate(1024)
        with self.assertRaises(app.HostKeyMismatch) as result:
            app.VerifyFingerprint('SHA256:'+'a'*43).missing_host_key(None,'host',key)
        self.assertIn(app.fingerprint(key),str(result.exception))
        self.assertIn('ssh-rsa',str(result.exception))
