import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ.setdefault('MONITOR_DATA_DIR', TEMP.name)
import app
import notifications
import telegram_bot

TOKEN = '987654321:AA_fake_token_only_for_incident_tests'
START = '2026-11-01T14:14:00+00:00'
END = '2026-11-01T14:20:00+00:00'


class NotificationIncidentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        change = patch.object(app, 'DB', Path(temp.name) / 'monitor.db')
        change.start(); self.addCleanup(change.stop)
        app.init_db()
        self.device = app.create_device(app.DeviceInput(name='LTE UARINI', host='192.0.2.10'))
        self.configure()

    def configure(self, enabled=True):
        app.save_notification_settings(app.NotificationInput(token=TOKEN, chat_id='123456789', enabled=enabled,
                                                            notify_collection=True))

    def emit(self, message, level='critical', topic='ping', key=None, stamp=START):
        with patch.object(app, 'now', return_value=stamp), app.connect() as db:
            app.alert(db, self.device, level, message, topic, key)

    def rows(self):
        with app.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM notification_outbox ORDER BY id')]

    def active(self):
        with app.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM notification_incidents ORDER BY incident_key')]

    def test_ping_message_is_exactly_name_cause_and_detection_time_without_header_or_ip(self):
        with patch.object(app, 'now', return_value=START):
            for _ in range(21): app.record_ping(self.device['id'], False)
        message = telegram_bot.summary(self.rows())
        self.assertEqual(message, 'LTE UARINI\nCausa: Sem resposta ao ping (21 perdas consecutivas).\nIniciado: 01/11/2026 às 10:14:00')
        with patch.object(app, 'now', return_value=END):
            app.record_ping(self.device['id'], True, 2)
        resolved = telegram_bot.summary([self.rows()[-1]])
        self.assertEqual(resolved, message + '\nResolvido: 01/11/2026 às 10:20:00')
        self.assertEqual(self.active(), [])

    def test_initial_time_survives_restart_pruning_and_repeated_failures(self):
        self.emit('Sem ping: 21 perdas consecutivas.')
        self.emit('Sem ping: 22 perdas consecutivas.', stamp=END)
        with app.connect() as db:
            db.execute("UPDATE notification_outbox SET status='sent'")
            notifications.prune(db, datetime.now().timestamp() + 8*86400)
        self.assertEqual(self.rows(), [])
        app.init_db()
        self.emit('Ping restabelecido. Equipamento online.', 'success', stamp=END)
        event = self.rows()[0]
        self.assertEqual(event['incident_started_at'], START)
        self.assertEqual(event['incident_cause'], 'Sem resposta ao ping (21 perdas consecutivas).')

    def test_ports_with_same_number_are_independent_and_alias_changes_keep_original_cause(self):
        self.emit('Porta Ten Gigabit Ethernet 1/1/1 (Saída Anori) caiu (link down).', topic='port', key='port:ten:1/1/1')
        self.emit('Porta Gigabit Ethernet 1/1/1 (Entrada) caiu (link down).', topic='port', key='port:giga:1/1/1')
        self.emit('Porta Ten Gigabit Ethernet 1/1/1 (Nome novo) restabelecida.', 'success', 'port', 'port:ten:1/1/1', END)
        resolved = self.rows()[-1]
        self.assertEqual(resolved['incident_cause'], 'Porta Ten Gigabit Ethernet 1/1/1 (Saída Anori) sem conexão.')
        self.assertEqual(resolved['incident_started_at'], START)
        self.assertEqual([r['incident_key'] for r in self.active()], ['port:giga:1/1/1'])

    def test_circuits_on_same_device_resolve_separately(self):
        self.emit('Circuito A (192.0.2.11): sem ping pelo Datacom, após 21 perdas consecutivas.', topic='circuit', key='circuit:1')
        self.emit('Circuito B (192.0.2.12): sem ping pelo Datacom, após 21 perdas consecutivas.', topic='circuit', key='circuit:2')
        self.emit('Circuito A (192.0.2.11) voltou a responder pelo Datacom.', 'success', 'circuit', 'circuit:1', END)
        self.assertIn('Circuito A', self.rows()[-1]['incident_cause'])
        self.assertEqual([r['incident_key'] for r in self.active()], ['circuit:2'])

    def test_band_recovery_preserves_original_failure_and_start(self):
        self.emit('Falha ao ler banda SIAE: O rádio não respondeu.', 'warning', 'collection', 'siae-band')
        self.emit('Leitura de banda SIAE restabelecida.', 'success', 'collection', 'siae-band', END)
        result = telegram_bot.summary([self.rows()[-1]])
        self.assertIn('Causa: Falha ao ler banda SIAE: O rádio não respondeu.', result)
        self.assertIn('Iniciado: 01/11/2026 às 10:14:00', result)
        self.assertIn('Resolvido: 01/11/2026 às 10:20:00', result)

    def test_recording_while_delivery_disabled_does_not_replay_history(self):
        self.configure(False)
        self.emit('Sem ping: 21 perdas consecutivas.')
        self.assertEqual(self.rows(), [])
        self.configure(True)
        self.emit('Ping restabelecido. Equipamento online.', 'success', stamp=END)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]['incident_started_at'], START)

    def test_changed_target_and_deleted_device_do_not_reuse_another_targets_incident(self):
        self.emit('Sem ping: 21 perdas consecutivas.')
        app.update_device(self.device['id'], app.DeviceInput(name='Outro alvo', host='192.0.2.20'))
        self.assertEqual(self.active(), [])
        self.emit('Sem ping: 21 perdas consecutivas.', stamp=END)
        app.delete_device(self.device['id'])
        self.assertEqual(self.active(), [])

    def test_database_upgrade_preserves_existing_queue_and_does_not_invent_old_start(self):
        self.emit('Sem ping: 21 perdas consecutivas.')
        with app.connect() as db:
            db.execute('ALTER TABLE notification_outbox DROP COLUMN incident_started_at')
            db.execute('ALTER TABLE notification_outbox DROP COLUMN incident_cause')
            db.execute('DELETE FROM notification_incidents')
        app.init_db()
        self.assertTrue(app.notification_settings()['enabled'])
        self.assertEqual(self.rows()[0]['message'], 'Sem ping: 21 perdas consecutivas.')
        self.assertIn('Iniciado: 01/11/2026 às 10:14:00', telegram_bot.summary(self.rows()))
        self.emit('Ping restabelecido. Equipamento online.', 'success', stamp=END)
        result = telegram_bot.summary([self.rows()[-1]])
        self.assertIn('Iniciado: não registrado', result)
        self.assertIn('Resolvido: 01/11/2026 às 10:20:00', result)

    def test_rollbacks_leave_no_incident_and_no_pending_notification(self):
        with app.connect() as db:
            with patch.object(app, 'now', return_value=START):
                app.alert(db, self.device, 'critical', 'Sem ping: 21 perdas consecutivas.', 'ping')
            db.rollback()
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.active(), [])

    def test_upgrade_recovers_active_ping_start_from_existing_panel_history(self):
        with patch.object(app, 'now', return_value=START):
            for _ in range(21): app.record_ping(self.device['id'], False)
        with app.connect() as db:
            db.execute('DELETE FROM notification_incidents')
        app.init_db()
        with patch.object(app, 'now', return_value=END):
            app.record_ping(self.device['id'], True, 2)
        self.assertEqual(self.rows()[-1]['incident_started_at'], START)
        self.assertIn('Iniciado: 01/11/2026 às 10:14:00', telegram_bot.summary([self.rows()[-1]]))

    def test_actual_sender_receives_simplified_text_and_keeps_original_panel_history(self):
        self.emit('Sem ping: 21 perdas consecutivas.')
        self.emit('Ping restabelecido. Equipamento online.', 'success', stamp=END)
        with patch.object(app.time, 'time', return_value=datetime.now().timestamp()+60), \
                patch.object(telegram_bot, 'send', return_value='simulated-id') as sender:
            app.send_pending_notifications()
        sender.assert_called_once()
        text = sender.call_args.args[2]
        self.assertNotIn('VELOSONET', text)
        self.assertNotIn('QUEDA', text)
        self.assertNotIn('192.0.2.10', text)
        self.assertIn('Resolvido: 01/11/2026 às 10:20:00', text)
        with app.connect() as db:
            self.assertEqual([r['message'] for r in db.execute('SELECT message FROM alerts ORDER BY id')],
                             ['Sem ping: 21 perdas consecutivas.', 'Ping restabelecido. Equipamento online.'])

    def test_three_long_events_keep_all_names_and_both_timestamps(self):
        events = [dict(device_name='😎'*80, level='success', message='x', incident_cause='😎'*1000,
                       incident_started_at=START, event_at=END) for _ in range(3)]
        result = telegram_bot.summary(events)
        self.assertEqual(result.count('Iniciado:'), 3)
        self.assertEqual(result.count('Resolvido:'), 3)
        self.assertLessEqual(len(result.encode('utf-16-le'))//2, 4000)
