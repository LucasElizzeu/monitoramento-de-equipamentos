"""Time-based ICMP availability, retained as daily UTC totals for 31 days."""
import math

DAY = 86400
RETENTION_DAYS = 31


def init_schema(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS availability_days (
          device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
          day INTEGER NOT NULL,
          up REAL NOT NULL DEFAULT 0, down REAL NOT NULL DEFAULT 0,
          error REAL NOT NULL DEFAULT 0,
          successes INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0,
          errors INTEGER NOT NULL DEFAULT 0, outages INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(device_id, day));
        CREATE TABLE IF NOT EXISTS availability_cursor (
          device_id INTEGER PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
          at REAL NOT NULL, state TEXT NOT NULL, expires REAL NOT NULL);
    ''')


def slices(start, end):
    while start < end:
        day = math.floor(start / DAY) * DAY
        edge = min(end, day + DAY)
        yield day, edge - start
        start = edge


def record(db, device, state, at, outage=False):
    """Account for the previous result only until its collection deadline.

    Error time is tracked separately. Long interruptions never become uptime
    or downtime. Called in the same transaction/version guard as record_ping.
    """
    previous = db.execute('SELECT * FROM availability_cursor WHERE device_id=?', (device['id'],)).fetchone()
    if previous and at <= previous['at']:
        return
    if previous:
        for day, duration in slices(previous['at'], min(at, previous['expires'])):
            column = previous['state']  # Internal enum, never user input.
            db.execute('INSERT OR IGNORE INTO availability_days(device_id,day) VALUES(?,?)', (device['id'], day))
            db.execute(f'UPDATE availability_days SET {column}={column}+? WHERE device_id=? AND day=?',
                       (duration, device['id'], day))
    day = math.floor(at / DAY) * DAY
    db.execute('INSERT OR IGNORE INTO availability_days(device_id,day) VALUES(?,?)', (device['id'], day))
    counter = {'up': 'successes', 'down': 'losses', 'error': 'errors'}[state]
    db.execute(f'UPDATE availability_days SET {counter}={counter}+1,outages=outages+? WHERE device_id=? AND day=?',
               (int(outage), device['id'], day))
    deadline = max(device['interval'] * 2, device['interval'] + device['ping_timeout'] + 5)
    db.execute('INSERT INTO availability_cursor(device_id,at,state,expires) VALUES(?,?,?,?) '
               'ON CONFLICT(device_id) DO UPDATE SET at=excluded.at,state=excluded.state,expires=excluded.expires',
               (device['id'], at, state, at + deadline))


def reset(db, device_id):
    db.execute('DELETE FROM availability_days WHERE device_id=?', (device_id,))
    db.execute('DELETE FROM availability_cursor WHERE device_id=?', (device_id,))


def prune(db, at):
    db.execute('DELETE FROM availability_days WHERE day<?',
               ((math.floor(at / DAY) - RETENTION_DAYS + 1) * DAY,))


def summarize(daily):
    totals = {key: sum(day[key] for day in daily) for key in
              ('up', 'down', 'error', 'unmonitored', 'successes', 'losses', 'errors', 'outages')}
    valid = totals['up'] + totals['down']
    period = valid + totals['error'] + totals['unmonitored']
    totals['availability_pct'] = 100 * totals['up'] / valid if valid else None
    totals['coverage_pct'] = 100 * valid / period if period else 0
    return totals


def report(db, devices, days, at):
    # Whole UTC dates, including today. This permits exact, bounded daily storage.
    start = (math.floor(at / DAY) - days + 1) * DAY
    stored = {(row['device_id'], row['day']): dict(row) for row in db.execute(
        'SELECT * FROM availability_days WHERE day>=? AND day<=?', (start, at))}
    cursors = {row['device_id']: row for row in db.execute('SELECT * FROM availability_cursor')}
    results = []
    for device in devices:
        daily = []
        for day in range(start, math.floor(at / DAY) * DAY + 1, DAY):
            entry = dict(day=day, up=0., down=0., error=0., successes=0, losses=0, errors=0, outages=0)
            entry.update({k: v for k, v in stored.get((device['id'], day), {}).items() if k in entry})
            cursor = cursors.get(device['id'])
            if cursor:
                left = max(day, cursor['at'])
                right = min(day + DAY, at, cursor['expires'])
                if right > left:
                    entry[cursor['state']] += right - left
            duration = min(day + DAY, at) - day
            entry['unmonitored'] = max(0., duration - entry['up'] - entry['down'] - entry['error'])
            daily.append(entry)
        results.append(dict(id=device['id'], name=device['name'], host=device['host'], kind=device['kind'],
                            daily=daily, **summarize(daily)))
    return dict(days=days, start=start, end=at, timezone='UTC', devices=results)


def demo_report(devices, days, at):
    start = (math.floor(at / DAY) - days + 1) * DAY
    results = []
    for device in devices:
        daily = []
        for index in range(days):
            day = start + index * DAY
            duration = min(DAY, at - day)
            down = min(duration * .15, (device['id'] * 127 + index * 41) % 900)
            error = min(duration * .03, 60 if index % 5 == 0 else 0)
            missing = min(duration * .02, 90 if index % 7 == 0 else 0)
            daily.append(dict(day=day, up=duration-down-error-missing, down=down, error=error,
                              unmonitored=missing, successes=1000, losses=10, errors=int(error > 0),
                              outages=int(down > 300)))
        results.append(dict(id=device['id'], name=device['name'], host=device['host'], kind=device['kind'],
                            daily=daily, **summarize(daily)))
    return dict(days=days, start=start, end=at, timezone='UTC', demo=True, devices=results)
