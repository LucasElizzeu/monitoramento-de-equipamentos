import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import app
import alert_labels
import ospf

OUTPUT = '''Neighbor ID Pri State Role Address Interface
10.200.1.1 1 full P2P 10.10.1.81 Infra-OSPF-MPLS-MNS_VIA_INFOVIA
10.200.9.1 1 full P2P 10.10.20.1 Infra-OSPF-MPLS-TEF_CRI-INFOVIA
10.200.30.1 1 full P2P 10.10.20.10 Infra-OSPF-MPLS-TEF_TBN-INFOVIA
'''


class OspfTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE devices(id INTEGER PRIMARY KEY)')
        self.db.execute('INSERT INTO devices VALUES(1)')
        ospf.init_schema(self.db)
        self.device = dict(id=1, host=ospf.SOURCE_HOST, kind='datacom', config_version=0)
        self.emit = Mock()

    def tearDown(self):
        self.db.close()

    def save(self, peers, error=None, at=100):
        ospf.record(self.db, self.device, peers, error, at, self.emit)

    def test_notification_title_identifies_ospf_instead_of_ping(self):
        self.assertEqual(alert_labels.title('OSPF INFOVIA: vizinho fora de Full.', 'critical', 'circuit'), 'Adjacência OSPF fora de Full')
        self.assertEqual(alert_labels.title('OSPF INFOVIA: vizinho restabelecido em Full.', 'success', 'circuit'), 'Adjacência OSPF restabelecida')

    def test_user_output_and_full_dr_variant(self):
        peers = ospf.parse_neighbors(OUTPUT)
        self.assertEqual([p['state'] for p in peers], ['full'] * 3)
        self.assertEqual(peers[0]['address'], '10.10.1.81')
        self.assertIn('MNS_VIA_INFOVIA', peers[0]['interface'])
        self.assertEqual(ospf.parse_neighbors(OUTPUT.replace('full P2P', 'FULL/DR 00:00:35'))[0]['state'], 'full')

    def test_empty_table_missing_and_same_router_wrong_address(self):
        peers = ospf.parse_neighbors('Neighbor ID Pri State Address Interface\n')
        self.assertEqual([p['state'] for p in peers], ['missing'] * 3)
        peers = ospf.parse_neighbors(OUTPUT.replace('10.10.1.81', '10.10.1.99'))
        self.assertEqual(peers[0]['state'], 'missing')

    def test_malformed_truncated_and_duplicate_queries_are_errors(self):
        for output in ('', 'Permission denied', 'Unknown command', OUTPUT.replace('full P2P', 'bogus P2P'),
                       OUTPUT.replace(' Infra-OSPF-MPLS-MNS_VIA_INFOVIA', ''), OUTPUT + OUTPUT.splitlines()[1]):
            with self.subTest(output=output), self.assertRaises(ValueError):
                ospf.parse_neighbors(output)

    def test_alerts_are_deduplicated_and_recover_after_collection_error(self):
        full = ospf.parse_neighbors(OUTPUT)
        self.save(full)
        self.emit.assert_not_called()
        down = ospf.parse_neighbors(OUTPUT.replace('10.200.1.1 1 full', '10.200.1.1 1 init'))
        self.save(down)
        self.save(down)
        self.assertEqual(self.emit.call_count, 1)
        self.assertEqual(self.emit.call_args.args[2], 'critical')
        self.save([], 'SSH unavailable')
        self.assertEqual(self.emit.call_count, 1)
        self.save(full)
        self.assertEqual(self.emit.call_count, 2)
        self.assertEqual(self.emit.call_args.args[2], 'success')

    def test_unknown_stale_changed_source_and_first_missing(self):
        self.assertEqual(ospf.public(self.db, self.device, 100)['status'], 'pending')
        self.save(ospf.parse_neighbors('No OSPF neighbors'))
        self.assertEqual(self.emit.call_count, 3)
        self.assertEqual(ospf.public(self.db, self.device, 150)['status'], 'ok')
        self.assertEqual(ospf.public(self.db, self.device, 191)['status'], 'stale')
        self.assertEqual(ospf.public(self.db, self.device, 90)['status'], 'stale')
        self.assertEqual(ospf.public(self.db, dict(self.device, config_version=1), 100)['status'], 'pending')
        self.assertIsNone(ospf.public(self.db, dict(self.device, host='10.0.0.1'), 100))

    def test_collector_uses_readonly_query_and_records_transport_errors(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(app, 'DB', Path(temp)/'monitor.db'):
            app.init_db()
            with app.connect() as db:
                db.execute("INSERT INTO devices(id,name,host,kind,interval) VALUES(1,'Escritório',?,'datacom',5)", (ospf.SOURCE_HOST,))
                device = dict(db.execute('SELECT * FROM devices WHERE id=1').fetchone())
            device.update(password=app.CIPHER.encrypt(b'example').decode(), fingerprint='', ssh_port=22)
            with patch.object(app.paramiko, 'SSHClient') as client, patch.object(app, 'ssh_read', return_value=OUTPUT) as read:
                app.run_ospf_check(device)
                read.assert_called_once_with(client.return_value, 'show ip ospf neighbor')
                client.return_value.close.assert_called_once()
            with app.connect() as db:
                self.assertEqual(ospf.public(db, device)['status'], 'ok')
                db.execute("UPDATE devices SET port_data='[]',ssh_error=NULL WHERE id=1")
            with patch.object(app.paramiko, 'SSHClient') as client:
                client.return_value.connect.side_effect = RuntimeError('secret must not escape')
                app.run_ospf_check(device)
            with app.connect() as db:
                result = ospf.public(db, device)
                self.assertEqual(result['status'], 'error')
                self.assertNotIn('secret', result['error'])
                row = db.execute('SELECT * FROM devices WHERE id=1').fetchone()
                self.assertIsNone(row['ssh_error'])
                self.assertEqual(row['port_data'], '[]')

    def test_obsolete_collection_is_not_committed(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(app, 'DB', Path(temp)/'monitor.db'):
            app.init_db()
            with app.connect() as db:
                db.execute("INSERT INTO devices(id,name,host,kind,interval,config_version) VALUES(1,'Tefé',?,'datacom',5,1)", (ospf.SOURCE_HOST,))
            device = dict(self.device, password=app.CIPHER.encrypt(b'example').decode(), fingerprint='', ssh_port=22, username='test')
            with patch.object(app.paramiko, 'SSHClient'), patch.object(app, 'ssh_read', return_value=OUTPUT):
                app.run_ospf_check(device)
            with app.connect() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM ospf_readings').fetchone()[0], 0)
