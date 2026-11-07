import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ.setdefault('MONITOR_DATA_DIR', TEMP.name)
import app


class RadioRoutesTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        db_patch = patch.object(app, 'DB', Path(directory.name) / 'monitor.db')
        db_patch.start()
        self.addCleanup(db_patch.stop)
        app.init_db()

    def radio(self, **values):
        return app.DeviceInput(name='Rádio', host='192.0.2.15', kind='siae', **values)

    def test_legacy_migration_keeps_radio_identity_credentials_and_telemetry(self):
        radio = app.create_device(self.radio(siae_enabled=True, siae_session='unit-test-session'))
        with app.connect() as db:
            key = db.execute('SELECT siae_session FROM devices WHERE id=?', (radio['id'],)).fetchone()[0]
            db.execute("UPDATE devices SET siae_data=? WHERE id=?", ('{"status":"ready","total_bps":123}', radio['id']))
            db.execute('ALTER TABLE devices DROP COLUMN radio_network')
            db.execute('ALTER TABLE devices DROP COLUMN radio_route')
        app.init_db()
        app.init_db()
        with app.connect() as db:
            saved = db.execute('SELECT * FROM devices WHERE id=?', (radio['id'],)).fetchone()
            self.assertEqual(saved['siae_session'], key)
            self.assertEqual(saved['siae_data'], '{"status":"ready","total_bps":123}')
            self.assertEqual(saved['radio_route'], 'tefe-tabatinga')
            self.assertIsNone(saved['radio_network'])
            self.assertEqual(saved['host'], radio['host'])

    def test_coari_requires_network_and_rejects_invalid_route(self):
        with self.assertRaises(app.HTTPException) as rejected:
            app.create_device(self.radio(radio_route='coari-tefe'))
        self.assertEqual(rejected.exception.status_code, 422)
        for values in ({'radio_route': 'invalid'}, {'radio_network': 3}, {'radio_network': 0}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.radio(**values)

    def test_network_round_trip_old_clients_and_change_of_route(self):
        radio = app.create_device(self.radio(radio_route='coari-tefe', radio_network=1))
        saved = app.update_device(radio['id'], self.radio())
        self.assertEqual((saved['radio_route'], saved['radio_network']), ('coari-tefe', 1))
        saved = app.update_device(radio['id'], self.radio(radio_route='coari-tefe', radio_network=2))
        self.assertEqual(saved['radio_network'], 2)
        saved = app.update_device(radio['id'], self.radio(radio_route='tefe-tabatinga'))
        self.assertIsNone(saved['radio_network'])
        self.assertEqual(saved['id'], radio['id'])
        app.init_db()
        self.assertEqual(app.dashboard()['devices'][0]['radio_route'], 'tefe-tabatinga')

    def test_radio_status_boundaries_and_no_reading(self):
        for state, latency, expected in [('online', 0, 'up'), ('online', 200, 'up'),
                ('online', 200.01, 'high'), ('online', 300, 'high'),
                ('offline', 0, 'down'), ('offline', None, 'down'),
                ('error', 10, 'unknown'), ('pending', None, 'unknown'),
                ('unstable', None, 'unknown')]:
            with self.subTest(state=state, latency=latency):
                self.assertEqual(app.radio_status({'state': state, 'latency': latency}), expected)
        radio = app.create_device(self.radio())
        with app.connect() as db:
            db.execute("UPDATE devices SET state='online',latency=201 WHERE id=?", (radio['id'],))
        self.assertEqual(app.dashboard()['devices'][0]['radio_status'], 'high')
