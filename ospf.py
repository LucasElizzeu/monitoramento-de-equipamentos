"""Read-only OSPF neighbor snapshots; routing state is independent of link state."""
import ipaddress
import json
import re
import time

SOURCE_HOST = '10.200.24.1'
COMMAND = 'show ip ospf neighbor'
PEERS = (
    dict(router_id='10.200.1.1', address='10.10.1.81', name='INFOVIA · Manaus', link_id='manaus-escritorio-infovia-1'),
    dict(router_id='10.200.9.1', address='10.10.20.1', name='INFOVIA · Coari', link_id='coari-escritorio-infovia-1'),
    dict(router_id='10.200.30.1', address='10.10.20.10', name='INFOVIA · Tabatinga', link_id=None),
)
ROW = re.compile(r'^\s*(\d+(?:\.\d+){3})\s+\d+\s+(down|attempt|init|2-?way|exstart|exchange|loading|full)(?:/\S*)?\s+(.+)$', re.I)
IP = re.compile(r'(?<![\d.])\d+(?:\.\d+){3}(?![\d.])')


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS ospf_readings (
        device_id INTEGER PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
        checked_at REAL NOT NULL, data TEXT NOT NULL, baseline TEXT NOT NULL DEFAULT '{}',
        config_version INTEGER NOT NULL DEFAULT 0)''')


def parse_neighbors(output):
    rows = []
    for line in output.splitlines():
        match = ROW.match(line)
        if not match:
            continue
        router_id, state, tail = match.groups()
        addresses = list(IP.finditer(tail))
        if len(addresses) != 1:
            raise ValueError('Linha OSPF incompleta ou ambígua.')
        address = addresses[0]
        for value in (router_id, address.group()):
            ipaddress.IPv4Address(value)
        interface = tail[address.end():].strip()
        if not interface:
            raise ValueError('Interface ausente na resposta OSPF.')
        rows.append(dict(router_id=router_id, address=address.group(), state=state.lower().replace('-', ''), interface=interface))
    # A valid empty table is a missing adjacency; arbitrary output is a collection error.
    header = re.search(r'neighbor\s+id.*state.*address.*interface|no\s+(?:ospf\s+)?neighbors?\b', output, re.I)
    if not rows and not header:
        raise ValueError('Resposta não reconhecida como tabela de vizinhos OSPF.')
    # Do not interpret truncated/malformed neighbor rows as a confirmed disappearance.
    candidates = [line for line in output.splitlines() if re.match(r'^\s*\d+(?:\.\d+){3}\s+\d+\s+', line)]
    if len(candidates) != len(rows):
        raise ValueError('Tabela de vizinhos OSPF incompleta.')
    result = []
    for peer in PEERS:
        matches = [r for r in rows if r['router_id'] == peer['router_id'] and r['address'] == peer['address']]
        if len(matches) > 1:
            raise ValueError('Mais de uma adjacência corresponde ao vizinho OSPF esperado.')
        result.append(dict(peer, **{k: v for k, v in (matches[0] if matches else dict(state='missing', interface='')).items() if k not in peer}))
    return result


def record(db, device, peers, error, checked_at, emit):
    previous = db.execute('SELECT * FROM ospf_readings WHERE device_id=?', (device['id'],)).fetchone()
    baseline = json.loads(previous['baseline']) if previous and previous['config_version'] == device['config_version'] else {}
    for peer in peers:
        key, state = peer['router_id'], peer['state']
        old = baseline.get(key)
        if state != 'full' and old in (None, 'full'):
            emit(db, device, 'critical', f"OSPF {peer['name']}: vizinho {key} fora de Full ({state}).", 'circuit', f'ospf:{key}')
        elif state == 'full' and old is not None and old != 'full':
            emit(db, device, 'success', f"OSPF {peer['name']}: vizinho {key} restabelecido em Full.", 'circuit', f'ospf:{key}')
        baseline[key] = state
    data = dict(peers=peers, error=error, checked_at=checked_at, command=COMMAND)
    db.execute('''INSERT INTO ospf_readings(device_id,checked_at,data,baseline,config_version) VALUES(?,?,?,?,?)
        ON CONFLICT(device_id) DO UPDATE SET checked_at=excluded.checked_at,data=excluded.data,
        baseline=excluded.baseline,config_version=excluded.config_version''',
        (device['id'], checked_at, json.dumps(data), json.dumps(baseline), device['config_version']))


def public(db, device, current_time=None):
    if device['host'] != SOURCE_HOST or device['kind'] != 'datacom':
        return None
    row = db.execute('SELECT * FROM ospf_readings WHERE device_id=?', (device['id'],)).fetchone()
    if not row or row['config_version'] != device['config_version']:
        return dict(status='pending', peers=[], error=None)
    data = json.loads(row['data'])
    age = (time.time() if current_time is None else current_time) - row['checked_at']
    data['status'] = 'stale' if age < -5 or age > 90 else 'error' if data['error'] else 'ok'
    return data
