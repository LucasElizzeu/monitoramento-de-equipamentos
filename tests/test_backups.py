import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet
import backups


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'data'
        self.data.mkdir()
        self.key = Fernet.generate_key()
        (self.data / 'credentials.key').write_bytes(self.key)
        self.secret = 'fake-test-password'
        with closing(sqlite3.connect(self.data / 'monitor.db')) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('CREATE TABLE devices(id INTEGER PRIMARY KEY,name TEXT,host TEXT,kind TEXT,password TEXT);'
                             'CREATE TABLE samples(id INTEGER PRIMARY KEY,success INTEGER);'
                             'CREATE TABLE alerts(id INTEGER PRIMARY KEY,message TEXT);')
            db.execute('INSERT INTO devices VALUES(1,?,?,?,?)',
                       ('Core', '192.0.2.1', 'datacom', Fernet(self.key).encrypt(self.secret.encode()).decode()))
            db.commit()

    def create(self, **kwargs):
        result = backups.create(self.data, **kwargs)
        return self.data / 'backups' / result['name']

    def tamper(self, original, replacements=None, extra=None):
        target = self.root / 'modified.zip'
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(target, 'w') as out:
            for name in source.namelist():
                out.writestr(name, (replacements or {}).get(name, source.read(name)))
            if extra:
                out.writestr(*extra)
        return target

    def test_snapshot_includes_committed_wal_data_and_valid_matching_key(self):
        with closing(sqlite3.connect(self.data / 'monitor.db')) as live:
            live.execute('INSERT INTO samples VALUES(1,1)')
            live.commit()
            archive = self.create()
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(set(z.namelist()), {'monitor.db', 'credentials.key', 'manifest.json'})
                self.assertNotIn(self.secret.encode(), z.read('monitor.db'))
                self.assertEqual(z.read('credentials.key'), self.key)
            destination = backups.restore(archive, self.root / 'restored')
            with closing(sqlite3.connect(destination / 'monitor.db')) as db:
                self.assertEqual(db.execute('SELECT success FROM samples').fetchone()[0], 1)
                stored = db.execute('SELECT password FROM devices').fetchone()[0]
                self.assertEqual(Fernet((destination / 'credentials.key').read_bytes()).decrypt(stored.encode()).decode(), self.secret)
            if os.name != 'nt':
                self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
                self.assertEqual((destination / 'credentials.key').stat().st_mode & 0o777, 0o600)

    def test_does_not_overwrite_existing_directory(self):
        archive = self.create()
        before = (self.data / 'monitor.db').read_bytes()
        with self.assertRaises(backups.BackupError):
            backups.restore(archive, self.data)
        self.assertEqual(before, (self.data / 'monitor.db').read_bytes())

    def test_corrupt_or_modified_backup_leaves_no_destination(self):
        modified = self.tamper(self.create(), {'credentials.key': Fernet.generate_key()})
        destination = self.root / 'restored'
        with self.assertRaises(backups.BackupError):
            backups.restore(modified, destination)
        self.assertFalse(destination.exists())
        modified.write_bytes(b'not a zip')
        with self.assertRaises(backups.BackupError):
            backups.restore(modified, destination)
        self.assertFalse(destination.exists())

    def test_checks_credential_key_even_when_manifest_hash_is_updated(self):
        archive = self.create()
        import hashlib
        with zipfile.ZipFile(archive) as z:
            manifest = json.loads(z.read('manifest.json'))
        wrong_key = Fernet.generate_key()
        manifest['sha256']['credentials.key'] = hashlib.sha256(wrong_key).hexdigest()
        modified = self.tamper(archive, {'credentials.key': wrong_key, 'manifest.json': json.dumps(manifest)})
        with self.assertRaises(backups.BackupError):
            backups.restore(modified, self.root / 'restored')

    def test_rejects_path_traversal_duplicate_members_and_unknown_versions(self):
        archive = self.create()
        for extra in (('../outside', 'bad'), ('devices.db', 'bad')):
            modified = self.tamper(archive, extra=extra)
            with self.assertRaises(backups.BackupError):
                backups.restore(modified, self.root / 'restored')
            self.assertFalse((self.root / 'outside').exists())
        modified = self.tamper(archive, {'manifest.json': json.dumps({'format': 'velosonet-backup', 'version': 99})})
        with self.assertRaises(backups.BackupError):
            backups.restore(modified, self.root / 'restored')

    def test_rejects_wrong_key_before_creating_any_backup(self):
        (self.data / 'credentials.key').write_bytes(Fernet.generate_key())
        with self.assertRaises(backups.BackupError):
            self.create()
        self.assertEqual(backups.catalog(self.data / 'backups'), [])

    def test_daily_schedule_and_separate_retention_for_automatic_and_manual(self):
        at = datetime(2026, 10, 1, tzinfo=timezone.utc)
        for i in range(9):
            backups.create(self.data, automatic=True, at=at + timedelta(days=i))
        self.assertIsNone(backups.create(self.data, automatic=True, at=at + timedelta(days=8, hours=1)))
        for i in range(7):
            backups.create(self.data, at=at + timedelta(days=9, minutes=i))
        entries = backups.catalog(self.data / 'backups')
        self.assertEqual(sum(e['automatic'] for e in entries), 7)
        self.assertEqual(sum(not e['automatic'] for e in entries), 5)
        self.assertEqual(entries[-1]['at'][:10], '2026-10-03')

    def test_download_lookup_cannot_escape_backup_directory(self):
        archive = self.create()
        self.assertEqual(backups.backup_path(archive.parent, archive.name), archive)
        for name in ('../credentials.key', 'monitor.db', '../' + archive.name, 'missing.zip'):
            with self.assertRaises(backups.BackupError):
                backups.backup_path(archive.parent, name)

    def test_oversized_archive_is_rejected_without_restoring(self):
        from unittest.mock import patch
        archive = self.create()
        with patch.object(backups, 'LIMIT', 10):
            with self.assertRaises(backups.BackupError):
                backups.restore(archive, self.root / 'restored')
        self.assertFalse((self.root / 'restored').exists())

    def test_malformed_manifest_does_not_create_destination(self):
        modified = self.tamper(self.create(), {'manifest.json': '[]'})
        with self.assertRaises(backups.BackupError):
            backups.restore(modified, self.root / 'restored')
        self.assertFalse((self.root / 'restored').exists())

    def test_invalid_database_is_rejected_even_with_valid_hash(self):
        import hashlib
        archive = self.create()
        with zipfile.ZipFile(archive) as z:
            manifest = json.loads(z.read('manifest.json'))
        payload = b'This is not SQLite'
        manifest['sha256']['monitor.db'] = hashlib.sha256(payload).hexdigest()
        modified = self.tamper(archive, {'monitor.db': payload, 'manifest.json': json.dumps(manifest)})
        with self.assertRaises(backups.BackupError):
            backups.restore(modified, self.root / 'restored')
        self.assertFalse((self.root / 'restored').exists())
