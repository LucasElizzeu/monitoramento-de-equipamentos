"""Durable, bounded alert outbox. Transport and monitoring run independently."""
import json
import time
import alert_labels

TOPICS = ('ping', 'port', 'circuit', 'collection')
MAX_PENDING = 500
MAX_AGE = 3600


def init_schema(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS notification_settings (
          id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0,
          revision INTEGER NOT NULL DEFAULT 0, token TEXT NOT NULL DEFAULT '',
          config TEXT NOT NULL DEFAULT '{}', last_error TEXT,
          last_sent_at REAL, next_send_at REAL NOT NULL DEFAULT 0,
          blocked INTEGER NOT NULL DEFAULT 0);
        INSERT OR IGNORE INTO notification_settings(id) VALUES(1);
        CREATE TABLE IF NOT EXISTS notification_outbox (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_id INTEGER NOT NULL, revision INTEGER NOT NULL,
          created_at REAL NOT NULL, event_at TEXT NOT NULL,
          device_name TEXT NOT NULL, host TEXT NOT NULL, topic TEXT NOT NULL,
          level TEXT NOT NULL, message TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
          provider TEXT NOT NULL DEFAULT 'telegram',
          available_at REAL NOT NULL, sent_at REAL, error TEXT, provider_id TEXT,
          UNIQUE(event_id, revision));
        CREATE INDEX IF NOT EXISTS notification_due ON notification_outbox(status,available_at,id);
        CREATE TABLE IF NOT EXISTS notification_incidents (
          device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
          incident_key TEXT NOT NULL, started_at TEXT NOT NULL, cause TEXT NOT NULL,
          PRIMARY KEY(device_id, incident_key));
    ''')
    columns = {row[1] for row in db.execute('PRAGMA table_info(notification_outbox)')}
    if 'provider' not in columns:
        db.execute("ALTER TABLE notification_outbox ADD COLUMN provider TEXT NOT NULL DEFAULT 'legacy'")
    for name in ('incident_started_at', 'incident_cause'):
        if name not in columns:
            db.execute(f'ALTER TABLE notification_outbox ADD COLUMN {name} TEXT')
    previous = settings(db)
    if (previous['config'] or previous['token'] or previous['enabled']) and previous['config'].get('provider') != 'telegram':
        # Replacing the old provider must not reuse its token or destination.
        db.execute("UPDATE notification_settings SET enabled=0,token='',config='{}',revision=revision+1,"
                   'last_error=NULL,blocked=0,next_send_at=0,last_sent_at=NULL WHERE id=1')
    db.execute("UPDATE notification_outbox SET status='cancelled' WHERE provider!='telegram' AND status IN ('pending','sending')")
    # A ping outage may already be active when this version is installed.
    # Recover its actual detection timestamp if the original alert still exists.
    for device in db.execute('SELECT id FROM devices WHERE failures>20'):
        event = db.execute("SELECT at,message FROM alerts WHERE device_id=? AND level='critical' "
                           "AND message LIKE 'Sem ping:%' ORDER BY id DESC LIMIT 1", (device['id'],)).fetchone()
        if event:
            db.execute('INSERT OR IGNORE INTO notification_incidents(device_id,incident_key,started_at,cause) '
                       "VALUES(?,'ping',?,?)", (device['id'], event['at'], alert_labels.cause(event['message'], 'critical', 'ping')))


def settings(db):
    row = dict(db.execute('SELECT * FROM notification_settings WHERE id=1').fetchone())
    row['config'] = json.loads(row['config'])
    return row


def incident_snapshot(db, device_id, level, message, topic, event_at, incident_key=None):
    fault = alert_labels.cause(message, level, topic)
    key = incident_key or ('ping' if topic == 'ping' else None)
    if key is None:
        return (None if level == 'success' else event_at), fault
    if level != 'success':
        db.execute('INSERT OR IGNORE INTO notification_incidents(device_id,incident_key,started_at,cause) '
                   'VALUES(?,?,?,?)', (device_id, key, event_at, fault))
    row = db.execute('SELECT started_at,cause FROM notification_incidents WHERE device_id=? AND incident_key=?',
                     (device_id, key)).fetchone()
    if level == 'success':
        db.execute('DELETE FROM notification_incidents WHERE device_id=? AND incident_key=?', (device_id, key))
    return (row['started_at'], row['cause']) if row else (None, fault)


def forget_incident(db, device_id, incident_key):
    db.execute('DELETE FROM notification_incidents WHERE device_id=? AND incident_key=?', (device_id, incident_key))


def enqueue(db, event_id, device, level, message, topic, event_at, at, incident_key=None):
    # Track the occurrence even when delivery is disabled or the queue is full.
    # This remains in the event transaction and survives queue pruning/restarts.
    started, fault = incident_snapshot(db, device['id'], level, message, topic, event_at, incident_key)
    selected = settings(db)
    config = selected['config']
    if not selected['enabled'] or not config.get('topics', {}).get(topic, False):
        return
    if level == 'warning' and not config.get('topics', {}).get('collection', False):
        return
    # Only future events enter the queue; old panel history is never replayed.
    db.execute("UPDATE notification_outbox SET status='expired',error='Evento com mais de uma hora.' "
               "WHERE status='pending' AND created_at<?", (at - MAX_AGE,))
    count = db.execute("SELECT count(*) FROM notification_outbox WHERE status IN ('pending','sending')").fetchone()[0]
    if count >= MAX_PENDING:
        db.execute("UPDATE notification_settings SET last_error='Fila cheia. Alguns alertas ficaram apenas no painel.' WHERE id=1")
        return
    db.execute('INSERT OR IGNORE INTO notification_outbox(event_id,revision,created_at,event_at,device_name,host,topic,level,message,available_at,provider,incident_started_at,incident_cause) '
               "VALUES(?,?,?,?,?,?,?,?,?,?,'telegram',?,?)",
               (event_id, selected['revision'], at, event_at, device['name'], device['host'], topic, level, message, at, started, fault))


def prepare(db, at):
    selected = settings(db)
    db.execute("UPDATE notification_outbox SET status='expired',error='Evento com mais de uma hora.' "
               "WHERE status='pending' AND created_at<?", (at - MAX_AGE,))
    db.execute("UPDATE notification_outbox SET status='cancelled' WHERE status='pending' AND revision!=?", (selected['revision'],))
    if not selected['enabled'] or selected['blocked'] or at < selected['next_send_at']:
        return None
    first = db.execute("SELECT created_at FROM notification_outbox WHERE status='pending' AND provider='telegram' AND revision=? "
                       "AND available_at<=? ORDER BY id LIMIT 1", (selected['revision'], at)).fetchone()
    if not first or at < first['created_at'] + selected['config'].get('batch_seconds', 30):
        return None
    rows = [dict(row) for row in db.execute("SELECT * FROM notification_outbox WHERE status='pending' "
        "AND provider='telegram' AND revision=? AND available_at<=? ORDER BY id LIMIT 3", (selected['revision'], at))]
    ids = [row['id'] for row in rows]
    db.executemany("UPDATE notification_outbox SET status='sending',attempts=attempts+1 WHERE id=?", [(i,) for i in ids])
    db.execute('UPDATE notification_settings SET next_send_at=? WHERE id=1',
               (at + selected['config'].get('batch_seconds', 30),))
    return dict(settings=selected, events=rows)


def finish(db, job, at, error=None, retryable=False, retry_after=60, provider_id=None):
    current = settings(db)
    same = current['revision'] == job['settings']['revision']
    for event in job['events']:
        status = 'sent' if error is None else 'pending' if retryable and event['attempts'] < 2 else 'failed'
        if error and not same:
            status = 'cancelled'
        db.execute('UPDATE notification_outbox SET status=?,sent_at=?,error=?,available_at=?,provider_id=? WHERE id=? AND status=\'sending\'',
                   (status, at if error is None else None, error, at + retry_after, provider_id, event['id']))
    if same:
        db.execute('UPDATE notification_settings SET last_error=?,blocked=?,'
                   'last_sent_at=CASE WHEN ? IS NULL THEN ? ELSE last_sent_at END,'
                   'next_send_at=CASE WHEN ? THEN max(next_send_at,?) ELSE next_send_at END WHERE id=1',
                   (error, int(error is not None and not retryable), error, at,
                    int(error is not None and retryable), at + retry_after))


def recover(db):
    # A crash may have happened after the remote service accepted a message.
    # Pending retries are bounded; the provider may deliver a duplicate in this case.
    db.execute("UPDATE notification_outbox SET status='pending',available_at=? WHERE status='sending' AND attempts<3", (time.time()+60,))
    db.execute("UPDATE notification_outbox SET status='failed',error='Envio interrompido após três tentativas.' WHERE status='sending'")


def prune(db, at):
    db.execute("DELETE FROM notification_outbox WHERE status NOT IN ('pending','sending') AND created_at<?", (at - 7*86400,))
    db.execute("DELETE FROM notification_outbox WHERE status NOT IN ('pending','sending') AND id NOT IN "
               "(SELECT id FROM notification_outbox ORDER BY id DESC LIMIT 1000)")
