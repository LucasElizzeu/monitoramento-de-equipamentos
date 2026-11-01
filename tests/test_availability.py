import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ.setdefault('MONITOR_DATA_DIR', TEMP.name)
import app
import availability
from fastapi import HTTPException


class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        change = patch.object(app, 'DB', Path(temp.name) / 'monitor.db')
        change.start()
        self.addCleanup(change.stop)
        app.init_db()
        self.device = app.create_device(app.DeviceInput(name='BBU Centro', host='192.0.2.10', interval=5))
        self.at = 20000 * availability.DAY + 12 * 3600

    def ping(self, at, success=True, error=None, **kwargs):
        with patch.object(app.time, 'time', return_value=at):
            app.record_ping(self.device['id'], success, 2 if success else None, error, **kwargs)

    def report(self, at, days=7):
        with patch.object(app.time, 'time', return_value=at):
            return app.availability_report(days)['devices'][0]

    def test_no_history_is_not_fabricated_uptime(self):
        result = self.report(self.at)
        self.assertIsNone(result['availability_pct'])
        self.assertEqual(result['coverage_pct'], 0)
        self.assertEqual(result['successes'], 0)
        self.assertEqual(len(result['daily']), 7)

    def test_elapsed_time_not_number_of_samples_determines_percentage(self):
        self.ping(self.at)
        self.ping(self.at + 5, False)
        self.ping(self.at + 15)
        result = self.report(self.at + 15)
        self.assertAlmostEqual(result['up'], 5)
        self.assertAlmostEqual(result['down'], 10)
        self.assertAlmostEqual(result['availability_pct'], 100 / 3)
        self.assertEqual((result['successes'], result['losses']), (2, 1))

    def test_collection_errors_are_excluded_from_percentage_and_outages(self):
        self.ping(self.at)
        self.ping(self.at + 5, False, 'Falha local')
        self.ping(self.at + 10)
        result = self.report(self.at + 15)
        self.assertEqual((result['up'], result['error'], result['down']), (10, 5, 0))
        self.assertEqual(result['availability_pct'], 100)
        self.assertEqual((result['errors'], result['outages'], result['losses']), (1, 0, 0))

    def test_stopped_collection_is_not_extended_across_a_long_gap(self):
        self.ping(self.at)
        self.ping(self.at + 3600)
        result = self.report(self.at + 3600)
        self.assertEqual(result['up'], 14)  # interval + timeout + grace
        self.assertEqual(result['down'], 0)
        self.assertGreater(result['unmonitored'], 3500)
        self.assertEqual(result['availability_pct'], 100)

    def test_reading_report_does_not_double_count_pending_duration(self):
        self.ping(self.at)
        self.assertEqual(self.report(self.at + 5)['up'], 5)
        self.assertEqual(self.report(self.at + 5)['up'], 5)
        self.ping(self.at + 10)
        self.assertEqual(self.report(self.at + 15)['up'], 15)

    def test_day_boundary_and_window_exclude_old_totals(self):
        midnight = 20000 * availability.DAY
        self.ping(midnight - 5)
        self.ping(midnight + 5, False)
        result = self.report(midnight + 10)
        self.assertEqual((result['daily'][-2]['up'], result['daily'][-1]['up']), (5, 5))
        self.assertEqual(result['daily'][-1]['down'], 5)
        later = self.report(midnight + 7 * availability.DAY)
        self.assertEqual(later['up'], 0)
        self.assertIsNone(later['availability_pct'])

    def test_confirmed_outages_count_once_at_21_losses(self):
        for i in range(25):
            self.ping(self.at + i, False)
        self.ping(self.at + 25)
        for i in range(21):
            self.ping(self.at + 26 + i, False)
        result = self.report(self.at + 48)
        self.assertEqual(result['outages'], 2)
        self.assertEqual(result['losses'], 46)

    def test_persists_after_init_and_device_rename_but_resets_changed_target(self):
        self.ping(self.at)
        self.ping(self.at + 5)
        app.init_db()
        app.update_device(self.device['id'], app.DeviceInput(name='Novo nome', host='192.0.2.10'))
        self.assertEqual(self.report(self.at + 5)['successes'], 2)
        app.update_device(self.device['id'], app.DeviceInput(name='Outro IP', host='192.0.2.11'))
        self.assertIsNone(self.report(self.at + 5)['availability_pct'])
        self.assertEqual(self.report(self.at + 5)['successes'], 0)

    def test_stale_version_and_deleted_devices_cannot_leave_history(self):
        self.ping(self.at, expected_version=99)
        self.assertEqual(self.report(self.at)['successes'], 0)
        self.ping(self.at)
        app.delete_device(self.device['id'])
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM availability_days').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM availability_cursor').fetchone()[0], 0)

    def test_pruning_preserves_30_day_window_and_demo_is_read_only(self):
        self.ping(self.at)
        with app.connect() as db:
            availability.prune(db, self.at + 31 * availability.DAY)
            self.assertEqual(db.execute('SELECT count(*) FROM availability_days').fetchone()[0], 0)
        demo = app.availability_report(30, True)
        self.assertTrue(demo['demo'])
        self.assertEqual(len(demo['devices'][0]['daily']), 30)
        self.assertEqual(self.report(self.at)['successes'], 0)
        with self.assertRaises(HTTPException):
            app.availability_report(365)

    def test_report_does_not_expose_credential_fields(self):
        with patch.object(app.time, 'time', return_value=self.at):
            result = app.availability_report()
        self.assertNotIn('password', str(result))
        self.assertNotIn('fingerprint', str(result))
        self.assertNotIn('siae_session', str(result))

    def test_startup_discards_live_cursor_without_deleting_daily_history(self):
        import asyncio
        self.ping(self.at)
        self.ping(self.at + 5)
        self.addCleanup(app.STOP.clear)

        async def startup():
            async with app.lifespan(app.app):
                with app.connect() as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM availability_cursor').fetchone()[0], 0)
                self.assertEqual(self.report(self.at + 3600)['up'], 5)

        with patch.object(app, 'monitor'), patch.object(app, 'automatic_backups'):
            asyncio.run(startup())
