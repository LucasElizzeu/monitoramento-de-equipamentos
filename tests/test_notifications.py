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
import notifications
import whatsapp_meta
import backups
from fastapi import HTTPException
from pydantic import ValidationError

TOKEN = 'test_meta_token_not_a_real_credential_12345'


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        for field, value in [('DB', self.data/'monitor.db'), ('DATA', self.data)]:
            change = patch.object(app, field, value)
            change.start(); self.addCleanup(change.stop)
        app.init_db()
        # Backups must contain the same key used for app-level encryption.
        (self.data/'credentials.key').write_bytes(app.KEY_FILE.read_bytes())
        self.device = app.create_device(app.DeviceInput(name='BBU Centro',host='192.0.2.10'))
        self.at = time.time()

    def configure(self, **kwargs):
        data = dict(token=TOKEN, phone_number_id='123456789', recipient='+55 (11) 99999-9999',
                    template_name='velosonet_alerta', enabled=True, batch_seconds=30)
        data.update(kwargs)
        return app.save_notification_settings(app.NotificationInput(**data))

    def enqueue(self, at=None, topic='ping', level='critical', message='Sem ping após 21 perdas.'):
        with patch.object(app.time, 'time', return_value=self.at if at is None else at):
            with app.connect() as db:
                app.alert(db, self.device, level, message, topic)

    def process(self, at):
        with patch.object(app.time,'time',return_value=at):
            app.send_pending_notifications()

    def rows(self):
        with app.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM notification_outbox ORDER BY id')]

    def test_disabled_by_default_and_no_replay_of_existing_history(self):
        self.enqueue()
        self.assertFalse(app.notification_settings()['enabled'])
        self.assertEqual(self.rows(), [])
        self.configure()
        self.assertEqual(self.rows(), [])

    def test_token_encrypted_never_returned_and_blank_keeps_it(self):
        result = self.configure()
        self.assertTrue(result['has_token'])
        self.assertNotIn(TOKEN, json.dumps(result))
        with app.connect() as db:
            original = notifications.settings(db)['token']
        self.assertNotIn(TOKEN, original)
        self.assertEqual(app.CIPHER.decrypt(original.encode()).decode(), TOKEN)
        self.configure(token='', recipient='5511888888888')
        with app.connect() as db:
            self.assertEqual(notifications.settings(db)['token'], original)
        self.assertEqual(app.notification_settings()['config']['recipient'], '5511888888888')

    def test_requires_complete_configuration_and_valid_inputs_before_enabling(self):
        for values in [dict(token=''), dict(phone_number_id='../secret'), dict(recipient='https://other.invalid'),
                       dict(language='pt/BR'), dict(api_version='https://other.invalid'),
                       dict(template_name='Wrong Name'), dict(token='bad\nAuthorization'),
                       dict(notify_ping=False,notify_ports=False,notify_circuits=False,notify_collection=False)]:
            with self.subTest(values=list(values)):
                with self.assertRaises((HTTPException, ValidationError)): self.configure(**values)
        self.assertFalse(app.notification_settings()['enabled'])

    def test_groups_three_events_and_rate_limits_remaining_events(self):
        self.configure()
        for i in range(4): self.enqueue(at=self.at+i)
        with patch.object(whatsapp_meta,'send',return_value='simulated-id') as sender:
            self.process(self.at+29); sender.assert_not_called()
            self.process(self.at+30)
            self.assertEqual(sender.call_count, 1)
            self.assertEqual([row['status'] for row in self.rows()], ['sent','sent','sent','pending'])
            self.process(self.at+45); self.assertEqual(sender.call_count, 1)
            self.process(self.at+60); self.assertEqual(sender.call_count, 2)
            self.process(self.at+90); self.assertEqual(sender.call_count, 2)
        self.assertEqual(app.notification_settings()['counts']['sent'], 4)

    def test_confirmation_threshold_repeated_loss_and_recovery_do_not_duplicate(self):
        self.configure()
        for i in range(30): app.record_ping(self.device['id'],False)
        app.record_ping(self.device['id'],True,2)
        app.record_ping(self.device['id'],True,2)
        self.assertEqual([row['level'] for row in self.rows()], ['critical','success'])
        self.assertEqual([row['topic'] for row in self.rows()], ['ping','ping'])

    def test_topics_and_local_errors_are_separate(self):
        self.configure(notify_ports=False)
        self.enqueue(topic='port')
        self.enqueue(topic='collection',level='warning')
        self.enqueue(topic='circuit')
        self.assertEqual([row['topic'] for row in self.rows()], ['circuit'])
        self.configure(notify_collection=True)
        app.record_ping(self.device['id'],False,error='Falha local')
        self.assertEqual(self.rows()[-1]['topic'], 'collection')

    def test_transient_errors_retry_three_times_then_stop(self):
        self.configure(); self.enqueue()
        with patch.object(whatsapp_meta,'send',side_effect=whatsapp_meta.SendError('Temporário', True)) as sender:
            for delta in [30,90,150,210]: self.process(self.at+delta)
            self.assertEqual(sender.call_count, 3)
        result=self.rows()[0]
        self.assertEqual((result['attempts'],result['status']), (3,'failed'))
        self.assertFalse(app.notification_settings()['blocked'])

    def test_permanent_error_pauses_queue_without_stopping_monitoring(self):
        self.configure(); self.enqueue()
        with patch.object(whatsapp_meta,'send',side_effect=whatsapp_meta.SendError('Token recusado')) as sender:
            self.process(self.at+30); self.enqueue(at=self.at+31)
            self.process(self.at+90); self.assertEqual(sender.call_count, 1)
        self.assertTrue(app.notification_settings()['blocked'])
        app.record_ping(self.device['id'],True,2)
        self.assertEqual(app.dashboard()['devices'][0]['state'], 'online')
        self.configure()
        self.assertFalse(app.notification_settings()['blocked'])
        self.assertEqual(self.rows()[-1]['status'], 'cancelled')

    def test_changes_and_removal_cancel_pending_events(self):
        self.configure(); self.enqueue()
        self.configure(recipient='5511888888888')
        self.assertEqual(self.rows()[0]['status'], 'cancelled')
        self.enqueue(at=self.at+1)
        app.remove_notification_settings()
        self.assertFalse(app.notification_settings()['has_token'])
        self.assertFalse(app.notification_settings()['enabled'])
        self.assertTrue(all(row['status']=='cancelled' for row in self.rows()))

    def test_conflicting_settings_revision_does_not_overwrite_current(self):
        original=self.configure()
        self.configure(recipient='5511888888888')
        with self.assertRaises(HTTPException) as result:
            self.configure(revision=original['revision'])
        self.assertEqual(result.exception.status_code,409)
        self.assertEqual(app.notification_settings()['config']['recipient'],'5511888888888')

    def test_expired_events_are_not_sent_after_a_long_interruption(self):
        self.configure(); self.enqueue()
        with patch.object(whatsapp_meta,'send') as sender:
            self.process(self.at+3601); sender.assert_not_called()
        self.assertEqual(self.rows()[0]['status'], 'expired')

    def test_queue_size_is_bounded(self):
        self.configure()
        with patch.object(notifications,'MAX_PENDING',2):
            for i in range(3): self.enqueue(at=self.at+i)
        self.assertEqual(len(self.rows()),2)
        self.assertIn('Fila cheia',app.notification_settings()['last_error'])
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM alerts').fetchone()[0],3)

    def test_recovery_retries_interrupted_job_without_resetting_attempt_count(self):
        self.configure(); self.enqueue()
        with app.connect() as db:
            notifications.prepare(db,self.at+30)
        with app.connect() as db:
            notifications.recover(db)
        row=self.rows()[0]
        self.assertEqual((row['status'],row['attempts']),('pending',1))
        self.assertGreater(row['available_at'],self.at)

    def test_test_send_is_explicit_works_while_disabled_and_does_not_enqueue(self):
        self.configure(enabled=False)
        with patch.object(whatsapp_meta,'send',return_value='simulated-test') as sender:
            self.assertEqual(app.test_notification()['status'],'accepted')
            sender.assert_called_once()
        self.assertEqual(self.rows(),[])
        self.assertFalse(app.notification_settings()['enabled'])

    def test_backup_preserves_encrypted_token_but_restore_pauses_notifications(self):
        self.configure(); self.enqueue()
        archive=backups.create(self.data)
        destination=backups.restore(self.data/'backups'/archive['name'],self.data/'restored')
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(destination/'monitor.db')) as db:
            enabled,token=db.execute('SELECT enabled,token FROM notification_settings').fetchone()
            self.assertEqual(enabled,0)
            self.assertEqual(app.CIPHER.decrypt(token.encode()).decode(),TOKEN)
            self.assertEqual(db.execute('SELECT status FROM notification_outbox').fetchone()[0],'cancelled')

    def test_rollback_does_not_send_uncommitted_events(self):
        self.configure()
        db=app.connect()
        try:
            app.alert(db,self.device,'critical','Queda','ping')
            db.rollback()
        finally: db.close()
        self.assertEqual(self.rows(),[])
