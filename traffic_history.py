"""24-hour Datacom RX history, separate for each physical interface family."""
import math

RETENTION_SECONDS = 24 * 3600


def init_schema(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS port_traffic_series (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
          identity TEXT NOT NULL, port TEXT NOT NULL, interface_type TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '', last_seen_at REAL NOT NULL,
          last_valid_at REAL, last_positive_at REAL, last_sample_at REAL,
          last_rx_bps REAL, UNIQUE(device_id, identity));
        CREATE TABLE IF NOT EXISTS port_traffic_samples (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          series_id INTEGER NOT NULL REFERENCES port_traffic_series(id) ON DELETE CASCADE,
          at REAL NOT NULL, rx_bps REAL,
          UNIQUE(series_id, at));
        CREATE INDEX IF NOT EXISTS traffic_sample_time ON port_traffic_samples(at);
        CREATE INDEX IF NOT EXISTS traffic_series_time ON port_traffic_samples(series_id, at);
        CREATE INDEX IF NOT EXISTS traffic_device_valid ON port_traffic_series(device_id, last_valid_at);
    ''')


def rate(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def append_sample(db, series, at, value):
    # One explicit null marks an outage. Its entire duration remains a gap;
    # repeated failures do not need to fill the database with null rows.
    if value is not None or series['last_sample_at'] is None or series['last_rx_bps'] is not None:
        db.execute('INSERT INTO port_traffic_samples(series_id,at,rx_bps) VALUES(?,?,?) '
                   'ON CONFLICT(series_id,at) DO UPDATE SET rx_bps=excluded.rx_bps',
                   (series['id'], at, value))
        db.execute('UPDATE port_traffic_series SET last_sample_at=?,last_rx_bps=? WHERE id=?',
                   (at, value, series['id']))
    db.execute('UPDATE port_traffic_series SET last_seen_at=? WHERE id=?', (at, series['id']))


def record(db, device, ports, identity_for, at):
    """Called inside the SSH result transaction, after the config version guard."""
    series = {row['identity']: dict(row) for row in db.execute(
        'SELECT * FROM port_traffic_series WHERE device_id=?', (device['id'],))}
    seen = set()
    for port in ports or []:
        family = port.get('interface_type', 'auto')
        identity = identity_for(port['name'], family)
        family = identity.split(':', 1)[0]
        if identity in seen:
            continue
        seen.add(identity)
        value = rate(port.get('rx_bps')) if port.get('utilization_enabled', True) and not port.get('utilization_error') else None
        entry = series.get(identity)
        if entry is None and value is not None:
            cursor = db.execute('INSERT INTO port_traffic_series(device_id,identity,port,interface_type,description,last_seen_at) '
                                'VALUES(?,?,?,?,?,?)', (device['id'], identity, port['name'], family, port.get('description', ''), at))
            entry = dict(db.execute('SELECT * FROM port_traffic_series WHERE id=?', (cursor.lastrowid,)).fetchone())
        if entry is None:
            continue
        db.execute('UPDATE port_traffic_series SET port=?,interface_type=?,description=? WHERE id=?',
                   (port['name'], family, port.get('description', ''), entry['id']))
        if value is not None:
            db.execute('UPDATE port_traffic_series SET last_valid_at=?,last_positive_at=CASE WHEN ?>0 THEN ? ELSE last_positive_at END WHERE id=?',
                       (at, value, at, entry['id']))
        append_sample(db, entry, at, value)
    for identity, entry in series.items():
        if identity not in seen:
            append_sample(db, entry, at, None)


def prune(db, at):
    db.execute('DELETE FROM port_traffic_samples WHERE at<?', (at - RETENTION_SECONDS,))
    db.execute('DELETE FROM port_traffic_series WHERE NOT EXISTS '
               '(SELECT 1 FROM port_traffic_samples WHERE series_id=port_traffic_series.id)')


def summarize(points):
    valid = [point[1] for point in points if point[1] is not None]
    return dict(count=len(valid), mean_bps=sum(valid) / len(valid) if valid else None,
                peak_bps=max(valid) if valid else None,
                last_bps=points[-1][1] if points else None,
                last_at=points[-1][0] if points else None)


def history(db, series_id, at):
    start = at - RETENTION_SECONDS
    rows = db.execute('SELECT at,rx_bps FROM port_traffic_samples WHERE series_id=? AND at>=? AND at<=? ORDER BY at',
                      (series_id, start, at)).fetchall()
    points = [[row['at'] * 1000, row['rx_bps']] for row in rows]
    return dict(start=start * 1000, end=at * 1000, expected_interval=30, points=points,
                stats=summarize(points))
