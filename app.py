"""Equipment monitoring MVP. Run: .venv/bin/uvicorn app:app."""
import base64
import hashlib
import ipaddress
import json
import math
import os
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import paramiko
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from icmplib import ping
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('MONITOR_DATA_DIR', ROOT / '.data'))
DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
KEY_FILE = DATA / 'credentials.key'
if not KEY_FILE.exists():
    try:
        with KEY_FILE.open('xb') as key_file:
            os.chmod(KEY_FILE, 0o600)
            key_file.write(Fernet.generate_key())
    except FileExistsError:
        pass
CIPHER = Fernet(KEY_FILE.read_bytes())
DB = DATA / 'monitor.db'
LOCK = threading.RLock()
STOP = threading.Event()
INFLIGHT = set()


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    connection = sqlite3.connect(DB, timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with connect() as db:
        db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS devices (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, host TEXT NOT NULL,
          kind TEXT NOT NULL, interval INTEGER NOT NULL, ssh_port INTEGER,
          username TEXT, password TEXT, fingerprint TEXT, ports TEXT,
          status_command TEXT, optics_command TEXT,
          state TEXT NOT NULL DEFAULT 'pending', failures INTEGER NOT NULL DEFAULT 0,
          latency REAL, last_check TEXT, last_ping REAL NOT NULL DEFAULT 0,
          last_ssh REAL NOT NULL DEFAULT 0, ssh_error TEXT, port_data TEXT DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS samples (
          id INTEGER PRIMARY KEY, device_id INTEGER NOT NULL, at TEXT NOT NULL,
          latency REAL, success INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS sample_device ON samples(device_id, id);
        CREATE TABLE IF NOT EXISTS alerts (
          id INTEGER PRIMARY KEY, device_id INTEGER NOT NULL, device_name TEXT NOT NULL,
          at TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL);
        ''')
        columns = {row['name'] for row in db.execute('PRAGMA table_info(devices)')}
        if 'config_version' not in columns:
            db.execute('ALTER TABLE devices ADD COLUMN config_version INTEGER NOT NULL DEFAULT 0')
    os.chmod(DB, 0o600)


class DeviceInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    host: str
    kind: str = 'ping'
    interval: int = Field(default=1, ge=1, le=300)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(default='', max_length=100)
    password: str = Field(default='', max_length=500)
    fingerprint: str = ''
    ports: list[str] = Field(default_factory=list, max_length=128)
    status_command: str = 'show interface link'
    optics_command: str = 'show interface tranceivers'

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError('Informe um nome.')
        return value.strip()

    @field_validator('host')
    @classmethod
    def valid_host(cls, value):
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError:
            raise ValueError('Informe um endereço IPv4 ou IPv6 válido.')

    @field_validator('kind')
    @classmethod
    def valid_kind(cls, value):
        if value not in ('ping', 'datacom'):
            raise ValueError('Tipo inválido.')
        return value

    @field_validator('ports')
    @classmethod
    def valid_ports(cls, value):
        if any(not re.fullmatch(r'[a-zA-Z0-9/_.:-]{1,40}', port) for port in value):
            raise ValueError('Nome de porta inválido.')
        if len(set(value)) != len(value):
            raise ValueError('Portas duplicadas.')
        return value

    @field_validator('status_command', 'optics_command')
    @classmethod
    def valid_command(cls, value):
        if (not re.fullmatch(r'(?:show|display) [a-zA-Z0-9 /_.:{}-]{1,150}', value)
                or value.count('{port}') > 1 or '{' in value.replace('{port}', '')
                or '}' in value.replace('{port}', '')):
            raise ValueError('Use um comando show/display somente de leitura. {port} é opcional.')
        return value


def public_device(row):
    value = dict(row)
    value['has_password'] = bool(value.pop('password'))
    value['ports'] = json.loads(value['ports'] or '[]')
    value['port_data'] = json.loads(value['port_data'] or '[]')
    return value


def alert(db, device, level, message):
    db.execute('INSERT INTO alerts(device_id,device_name,at,level,message) VALUES(?,?,?,?,?)',
               (device['id'], device['name'], now(), level, message))


def record_ping(device_id, success, latency=None, error=None, expected_version=None, started_at=None):
    """Only completed ICMP probes count as packet loss; local errors do not."""
    with LOCK, connect() as db:
        device = db.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone()
        if not device or (expected_version is not None and device['config_version'] != expected_version):
            return
        ping_at = started_at if started_at is not None else time.time()
        if error:
            if device['state'] != 'error':
                alert(db, device, 'warning', error)
            db.execute("UPDATE devices SET state='error',last_check=?,last_ping=?,latency=NULL WHERE id=?",
                       (now(), ping_at, device_id))
            return
        failures = 0 if success else device['failures'] + 1
        state = 'online' if success else ('offline' if failures > 20 else 'unstable')
        if state == 'offline' and device['failures'] <= 20:
            alert(db, device, 'critical', f'Sem ping: {failures} perdas consecutivas.')
        if success and device['failures'] > 20:
            alert(db, device, 'success', 'Ping restabelecido. Equipamento online.')
        at = now()
        db.execute('UPDATE devices SET state=?,failures=?,latency=?,last_check=?,last_ping=? WHERE id=?',
                   (state, failures, latency if success else None, at, ping_at, device_id))
        db.execute('INSERT INTO samples(device_id,at,latency,success) VALUES(?,?,?,?)',
                   (device_id, at, latency if success else None, int(success)))
        db.execute('DELETE FROM samples WHERE device_id=? AND id NOT IN '
                   '(SELECT id FROM samples WHERE device_id=? ORDER BY id DESC LIMIT 720)',
                   (device_id, device_id))
        db.execute('DELETE FROM alerts WHERE id NOT IN (SELECT id FROM alerts ORDER BY id DESC LIMIT 1000)')


def check_ping(device):
    started_at = time.time()
    version = device.get('config_version')
    try:
        result = ping(device['host'], count=1, timeout=min(1.5, device['interval'] * 0.8), privileged=False)
        record_ping(device['id'], result.is_alive, result.avg_rtt if result.is_alive else None,
                    expected_version=version, started_at=started_at)
    except Exception:
        record_ping(device['id'], False, error='Não foi possível executar ICMP. Verifique as permissões e a rede do servidor.',
                    expected_version=version, started_at=started_at)


def fingerprint(key):
    return 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')


class VerifyFingerprint(paramiko.MissingHostKeyPolicy):
    def __init__(self, expected):
        self.expected = expected

    def missing_host_key(self, client, hostname, key):
        if fingerprint(key) != self.expected:
            raise paramiko.SSHException('Chave SSH não corresponde à impressão digital cadastrada.')


def clean_cli(output):
    output = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', output)
    return output.replace('\r', '').replace('\u2212', '-').replace('\xa0', ' ')


def port_lines(port, output):
    """Select the exact interface and its wrapped diagnostic lines."""
    if re.fullmatch(r'\d+/\d+/\d+', port):
        pattern = re.compile(r'(?<![\d/])' + re.escape(port) + r'(?![\d/])', re.I)
    else:
        pattern = re.compile(r'(?<![\w/.-])' + re.escape(port) + r'(?![\w/.-])', re.I)
    lines = []
    active = False
    for line in clean_cli(output).splitlines():
        if re.search(r'(?<![\d/])\d+/\d+/\d+(?![\d/])', line):
            active = bool(pattern.search(line))
        if active:
            lines.append(line)
    return '\n'.join(lines)


def optical_power(cell):
    cell = cell.strip()
    # Never interpret N/A, LOS or a dash as zero power.
    match = re.fullmatch(r'([+-]?\d+(?:[.,]\d+)?)\s*(?:dBm)?', cell, re.I)
    return float(match.group(1).replace(',', '.')) if match else None


def optical_powers(output, context=None):
    output = clean_cli(output)
    values = {'rx': None, 'tx': None}
    direction = r'(?<![a-z])(?:rx|tx|receive[dr]?|receiving|transmit(?:ted)?|transmitting)(?![a-z])'
    for line in output.splitlines():
        labels = list(re.finditer(direction, line, re.I))
        for i, label in enumerate(labels):
            key = 'rx' if re.match(r'rx|receiv', label.group(), re.I) else 'tx'
            segment = line[label.end():labels[i + 1].start() if i + 1 < len(labels) else len(line)]
            match = re.search(r'([+-]?\d+(?:[.,]\d+)?)\s*dBm', segment, re.I)
            if not match:
                match = re.search(r'dBm\s*\)?\s*[:=]?\s*([+-]?\d+(?:[.,]\d+)?)', segment, re.I)
            if match:
                values[key] = float(match.group(1).replace(',', '.'))
    # Honor explicit header order, including reversed RX/TX and values without units.
    header = None
    for line in clean_cli(context or output).splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        rx = next((i for i,c in enumerate(cells) if re.search(r'\b(?:rx|receive[dr]?)\b', c, re.I)), None)
        tx = next((i for i,c in enumerate(cells) if re.search(r'\b(?:tx|transmit(?:ted)?)\b', c, re.I)), None)
        if rx is not None and tx is not None and rx != tx:
            header = (len(cells), rx, tx)
            break
    for line in output.splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if header and len(cells) == header[0]:
            for key, index in [('rx', header[1]), ('tx', header[2])]:
                if values[key] is None:
                    values[key] = optical_power(cells[index])
        elif len(cells) >= 3:
            # DmOS row ends in TX | RX. Temperature/voltage/bias may be missing.
            power_cell = r'(?:[+-]?\d+(?:[.,]\d+)?\s*dBm|N/?A|--?|-?inf(?:inity)?(?:\s*dBm)?|LOS)'
            if all(re.fullmatch(power_cell, cell, re.I) for cell in cells[-2:]):
                for key, cell in [('tx', cells[-2]), ('rx', cells[-1])]:
                    if values[key] is None:
                        values[key] = optical_power(cell)
        elif not re.search(direction, line, re.I):
            # Whitespace tables with two explicit dBm measurements, TX then RX.
            powers = re.findall(r'([+-]?\d+(?:[.,]\d+)?)\s*dBm', line, re.I)
            if len(powers) == 2:
                for key, value in zip(('tx', 'rx'), powers):
                    if values[key] is None:
                        values[key] = float(value.replace(',', '.'))
    return values['rx'], values['tx']


def parse_port(port, status_output, optics_output, optics_context=None):
    # Conservative extraction: ambiguous or unfamiliar output stays unknown.
    match = re.search(r'(?:line protocol|operational(?: status)?|oper(?:ation)? state|link(?: status)?|physical(?: state)?|\bis)\s*(?:is|:|=)?\s*(up|down)\b', status_output, re.I)
    states = set(s.lower() for s in re.findall(r'\b(?:up|down)\b', status_output, re.I))
    state = match.group(1).lower() if match else (next(iter(states)).lower() if len(states) == 1 else 'unknown')
    description = re.search(r'\bdescription\s*[:=]\s*(.*)', status_output, re.I)
    # DmOS `show interface link`: interface, link, autoneg, speed, duplex,
    # three extra columns, then description. Never include another interface.
    link_row = re.search(r'^\s*' + re.escape(port) + r'\s+(up|down)\s+(?:true|false)\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s*(.*?)\s*$', status_output, re.I | re.M)
    rx, tx = optical_powers(optics_output, optics_context)
    if link_row:
        state = link_row.group(1).lower()
    return dict(name=port, state=state, rx=rx, tx=tx,
                description=link_row.group(2).strip() if link_row else description.group(1).strip() if description else '',
                checked_at=now(), status_output=status_output, optics_output=optics_output)


def ssh_read(client, command):
    _, stdout, stderr = client.exec_command(command, timeout=7)
    output = stdout.read(65536).decode('utf-8', 'replace')
    error = stderr.read(4096).decode('utf-8', 'replace')
    if stdout.channel.recv_exit_status() not in (0, -1) or error.strip():
        raise paramiko.SSHException('Comando rejeitado. Confira o perfil de comandos do equipamento.')
    return output


def check_ssh(device):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(VerifyFingerprint(device['fingerprint']))
    ports = []
    error = None
    try:
        client.connect(device['host'], port=device['ssh_port'], username=device['username'],
                       password=CIPHER.decrypt(device['password'].encode()).decode(),
                       timeout=6, auth_timeout=6, banner_timeout=6, look_for_keys=False, allow_agent=False)
        status_bulk = None if '{port}' in device['status_command'] else ssh_read(client, device['status_command'])
        optics_bulk = None if '{port}' in device['optics_command'] else ssh_read(client, device['optics_command'])
        selected_ports = json.loads(device['ports'])
        if not selected_ports and status_bulk is not None:
            selected_ports = list(dict.fromkeys(re.findall(r'^\s*([\w.-]*\d+/\d+/\d+)\s+(?:up|down)\b', status_bulk, re.I | re.M)))[:128]
            if not selected_ports:
                raise paramiko.SSHException('Nenhuma porta reconhecida na listagem.')
        for port in selected_ports:
            status = ssh_read(client, device['status_command'].replace('{port}', port)) if status_bulk is None else port_lines(port, status_bulk)
            optics = ssh_read(client, device['optics_command'].replace('{port}', port)) if optics_bulk is None else port_lines(port, optics_bulk)
            result = parse_port(port, status, optics, optics_context=optics_bulk)
            result['status_output'] = status_bulk if status_bulk is not None else status
            result['optics_output'] = optics_bulk if optics_bulk is not None else optics
            ports.append(result)
    except paramiko.AuthenticationException:
        error = 'Autenticação SSH recusada. Verifique usuário e senha.'
    except Exception:
        error = 'Consulta SSH falhou. Verifique acesso, chave SSH e comandos do modelo.'
    finally:
        client.close()
    with LOCK, connect() as db:
        current = db.execute('SELECT * FROM devices WHERE id=?', (device['id'],)).fetchone()
        if not current or current['config_version'] != device.get('config_version', 0):
            return
        if error:
            if current['ssh_error'] != error:
                alert(db, current, 'warning', error)
            db.execute('UPDATE devices SET ssh_error=?,last_ssh=? WHERE id=?', (error, time.time(), device['id']))
        else:
            previous = {p['name']: p for p in json.loads(current['port_data'])}
            for port in ports:
                old = previous.get(port['name'], {}).get('state')
                if port['state'] == 'down' and old != 'down':
                    alert(db, current, 'critical', f"Porta {port['name']} caiu (link down).")
                elif port['state'] == 'up' and old == 'down':
                    alert(db, current, 'success', f"Porta {port['name']} restabelecida.")
            db.execute('UPDATE devices SET ssh_error=NULL,last_ssh=?,port_data=? WHERE id=?',
                       (time.time(), json.dumps(ports), device['id']))


def run_check(device, kind):
    try:
        (check_ping if kind == 'ping' else check_ssh)(device)
    finally:
        with LOCK:
            INFLIGHT.discard((device['id'], kind))


def monitor():
    with ThreadPoolExecutor(max_workers=12) as pool:
        while not STOP.is_set():
            with LOCK, connect() as db:
                devices = db.execute('SELECT * FROM devices').fetchall()
                for row in devices:
                    device = dict(row)
                    for kind, due in [('ping', time.time() - device['last_ping'] >= device['interval']),
                                      ('ssh', device['kind'] == 'datacom' and time.time() - device['last_ssh'] >= 30)]:
                        key = (device['id'], kind)
                        if due and key not in INFLIGHT:
                            INFLIGHT.add(key)
                            pool.submit(run_check, device, kind)
            STOP.wait(0.1)


@asynccontextmanager
async def lifespan(app):
    init_db()
    STOP.clear()
    thread = threading.Thread(target=monitor, daemon=True)
    app.state.monitor_thread = thread
    thread.start()
    yield
    STOP.set()
    thread.join(timeout=15)


app = FastAPI(title='Nexo • Monitoramento de rede', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


@app.middleware('http')
async def local_api_guard(request, call_next):
    # Prevent cross-site writes when running the local development interface.
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
        from urllib.parse import urlsplit
        if urlsplit(origin).netloc != request.headers.get('host'):
            return JSONResponse({'detail': 'Origem não permitida.'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/')
def index():
    return FileResponse(ROOT / 'static' / 'index.html')


@app.get('/api/health')
def health():
    running = getattr(app.state, 'monitor_thread', None)
    return {'status': 'ok' if running and running.is_alive() else 'degraded',
            'monitor_running': bool(running and running.is_alive() and not STOP.is_set())}


@app.get('/api/dashboard')
def dashboard(demo: bool = False):
    if demo:
        return demo_dashboard()
    with LOCK, connect() as db:
        devices = [public_device(row) for row in db.execute('SELECT * FROM devices ORDER BY id')]
        events = [dict(row) for row in db.execute('SELECT * FROM alerts ORDER BY id DESC LIMIT 60')]
        samples = [dict(row) for row in db.execute('SELECT * FROM samples ORDER BY id DESC LIMIT 720')][::-1]
    return dict(devices=devices, alerts=events, samples=samples, demo=False, updated_at=now())


def device_values(device, previous=None):
    values = device.model_dump()
    password = device.password
    saved_password = previous['password'] if previous and previous['kind'] == 'datacom' else ''
    if device.kind == 'datacom' and (not device.username or not (password or saved_password)
            or not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}', device.fingerprint)):
        raise HTTPException(422, 'Datacom requer usuário, senha e impressão digital SSH SHA256 verificada.')
    if device.kind == 'datacom' and not device.ports and ('{port}' in device.status_command or '{port}' in device.optics_command):
        raise HTTPException(422, 'Informe as portas ao usar comandos com {port}.')
    values['ports'] = json.dumps(values['ports'])
    values['password'] = (CIPHER.encrypt(password.encode()).decode() if password else saved_password) if device.kind == 'datacom' else ''
    return values


@app.post('/api/devices', status_code=201)
def create_device(device: DeviceInput):
    values = device_values(device)
    with LOCK, connect() as db:
        if db.execute('SELECT id FROM devices WHERE host=? AND kind=?', (device.host, device.kind)).fetchone():
            raise HTTPException(409, 'Este IP já está cadastrado para este tipo de monitoramento.')
        if db.execute('SELECT count(*) FROM devices').fetchone()[0] >= 100:
            raise HTTPException(422, 'Limite desta versão: 100 equipamentos.')
        columns = ','.join(values)
        cursor = db.execute(f"INSERT INTO devices({columns}) VALUES({','.join('?' for _ in values)})", tuple(values.values()))
        result = public_device(db.execute('SELECT * FROM devices WHERE id=?', (cursor.lastrowid,)).fetchone())
    return result


@app.put('/api/devices/{device_id}')
def update_device(device_id: int, device: DeviceInput):
    with LOCK, connect() as db:
        previous = db.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone()
        if not previous:
            raise HTTPException(404, 'Equipamento não encontrado.')
        values = device_values(device, previous)
        if db.execute('SELECT id FROM devices WHERE host=? AND kind=? AND id<>?',
                      (device.host, device.kind, device_id)).fetchone():
            raise HTTPException(409, 'Este IP já está cadastrado para este tipo de monitoramento.')
        changed_target = device.host != previous['host'] or device.kind != previous['kind']
        changed_ssh = any(values[key] != previous[key] for key in
                          ('ssh_port', 'username', 'password', 'fingerprint', 'ports', 'status_command', 'optics_command'))
        if changed_target:
            db.execute('DELETE FROM samples WHERE device_id=?', (device_id,))
            values.update(state='pending', failures=0, latency=None, last_check=None)
        if changed_target or changed_ssh:
            values.update(port_data='[]', ssh_error=None)
        values.update(config_version=previous['config_version'] + 1, last_ping=0, last_ssh=0)
        assignments = ','.join(f'{column}=?' for column in values)
        db.execute(f'UPDATE devices SET {assignments} WHERE id=?', (*values.values(), device_id))
        return public_device(db.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone())


@app.delete('/api/devices/{device_id}', status_code=204)
def delete_device(device_id: int):
    with LOCK, connect() as db:
        if not db.execute('DELETE FROM devices WHERE id=?', (device_id,)).rowcount:
            raise HTTPException(404, 'Equipamento não encontrado.')
        db.execute('DELETE FROM samples WHERE device_id=?', (device_id,))


@app.get('/api/devices/{device_id}/history')
def history(device_id: int):
    with LOCK, connect() as db:
        return [dict(row) for row in db.execute('SELECT at,latency,success FROM samples WHERE device_id=? ORDER BY id DESC LIMIT 120', (device_id,))][::-1]


def demo_dashboard():
    devices = []
    labels = [('Datacom • Core principal', '10.0.0.1', 'datacom', 'online', 2.4),
              ('Datacom • Distribuição norte', '10.0.1.1', 'datacom', 'online', 3.8),
              ('Servidor • ERP', '10.0.0.10', 'ping', 'online', 1.2),
              ('Roteador • Filial centro', '10.0.2.1', 'ping', 'unstable', None),
              ('Switch • Almoxarifado', '10.0.3.2', 'ping', 'offline', None),
              ('Datacom • Distribuição sul', '10.0.4.1', 'datacom', 'online', 4.1)]
    for i, (name, host, kind, state, latency) in enumerate(labels, 1):
        ports = [] if kind == 'ping' else [dict(name=f'ge1/1/{p}', state='down' if i == 2 and p == 3 else 'up', rx=None if i == 2 and p == 3 else round(-8.3-p*1.2, 2), tx=-2.1, checked_at=now(), status_output='Exemplo de saída simulada', optics_output='Dados de demonstração') for p in range(1, 5)]
        devices.append(dict(id=i, name=name, host=host, kind=kind, state=state, failures=24 if state == 'offline' else 7 if state == 'unstable' else 0, latency=latency, last_check=now(), interval=5, ports=[p['name'] for p in ports], port_data=ports, ssh_error=None))
    samples = [dict(device_id=1, at=datetime.fromtimestamp(time.time()-(59-i)*5, timezone.utc).isoformat(), latency=round(3 + math.sin(i*.55)*.7 + math.cos(i*.17)*.45, 2), success=1) for i in range(60)]
    events = [dict(id=3, device_id=5, device_name=labels[4][0], at=now(), level='critical', message='Sem ping: 24 perdas consecutivas.'),
              dict(id=2, device_id=2, device_name=labels[1][0], at=now(), level='critical', message='Porta ge1/1/3 caiu (link down).'),
              dict(id=1, device_id=1, device_name=labels[0][0], at=now(), level='success', message='Ping restabelecido. Equipamento online.')]
    return dict(devices=devices, alerts=events, samples=samples, demo=True, updated_at=now())
