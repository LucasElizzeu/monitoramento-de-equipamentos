import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
import app


class DeviceCityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(app, 'DB', Path(self.temp.name)/'monitor.db')
        self.patch.start()
        app.init_db()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_city_round_trip_and_legacy_update_preserves_city(self):
        d = app.create_device(app.DeviceInput(name='BBU teste', host='192.0.2.55', city='  São   Paulo  '))
        self.assertEqual(d['city'], 'São Paulo')
        updated = app.update_device(d['id'], app.DeviceInput(name=d['name'], host=d['host']))
        self.assertEqual(updated['city'], 'São Paulo')
        cleared = app.update_device(d['id'], app.DeviceInput(name=d['name'], host=d['host'], city=''))
        self.assertEqual(cleared['city'], '')

    def test_old_database_gets_city_without_changing_devices(self):
        with app.connect() as db:
            db.execute("INSERT INTO devices(name,host,kind,interval) VALUES('Antigo','192.0.2.56','ping',5)")
            db.execute('ALTER TABLE devices DROP COLUMN city')
        app.init_db()
        with app.connect() as db:
            row = dict(db.execute("SELECT * FROM devices WHERE host='192.0.2.56'").fetchone())
        self.assertEqual(row['city'], '')
        self.assertEqual(row['name'], 'Antigo')
        self.assertEqual(row['interval'], 5)

    def test_long_or_control_character_city_rejected(self):
        for city in ('a'*81, 'Coari\nTefé', 'Coari\x00'):
            with self.subTest(city=city), self.assertRaises(ValidationError):
                app.DeviceInput(name='BBU', host='192.0.2.1', city=city)
