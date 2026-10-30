"""Equipment monitoring MVP. Run: .venv/bin/uvicorn app:app."""
import base64
import hashlib
import ipaddress
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
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
from remote_ping import RemotePingError, parse_remote_ping, read_remote_ping

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
IS_WINDOWS = sys.platform == 'win32'
INTERFACE_LABELS = {
    'auto': 'Automático',
    'mixed': 'Gigabit + Ten (portas selecionadas)',
    'gigabit-ethernet': 'Gigabit Ethernet',
    'ten-gigabit-ethernet': 'Ten Gigabit Ethernet',
    'hundred-gigabit-ethernet': 'Hundred Gigabit Ethernet',
}


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    connection = sqlite3.connect(DB, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
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
        CREATE TABLE IF NOT EXISTS circuits (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
          name TEXT NOT NULL, host TEXT NOT NULL, interval INTEGER NOT NULL DEFAULT 30,
          state TEXT NOT NULL DEFAULT 'pending', failures INTEGER NOT NULL DEFAULT 0,
          latency REAL, last_check TEXT, last_poll REAL NOT NULL DEFAULT 0,
          output TEXT NOT NULL DEFAULT '', error TEXT,
          transmitted INTEGER, received INTEGER, config_version INTEGER NOT NULL DEFAULT 0,
          port_identity TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS circuit_target ON circuits(source_device_id, host);
        ''')
        columns = {row['name'] for row in db.execute('PRAGMA table_info(devices)')}
        circuit_columns = {row['name'] for row in db.execute('PRAGMA table_info(circuits)')}
        if 'port_identity' not in circuit_columns:
            db.execute('ALTER TABLE circuits ADD COLUMN port_identity TEXT')
        if 'config_version' not in columns:
            db.execute('ALTER TABLE devices ADD COLUMN config_version INTEGER NOT NULL DEFAULT 0')
        if 'ping_timeout' not in columns:
            db.execute('ALTER TABLE devices ADD COLUMN ping_timeout REAL NOT NULL DEFAULT 4')
        if 'ping_detail' not in columns:
            db.execute('ALTER TABLE devices ADD COLUMN ping_detail TEXT')
        if 'interface_type' not in columns:
            db.execute("ALTER TABLE devices ADD COLUMN interface_type TEXT NOT NULL DEFAULT 'auto'")
        if 'ssh_diagnostic' not in columns:
            db.execute("ALTER TABLE devices ADD COLUMN ssh_diagnostic TEXT NOT NULL DEFAULT '{}'")
        if 'circuit_position' not in columns:
            db.execute('ALTER TABLE devices ADD COLUMN circuit_position REAL')
        if 'port_aliases' not in columns:
            db.execute("ALTER TABLE devices ADD COLUMN port_aliases TEXT NOT NULL DEFAULT '{}'")
        if 'utilization_command' not in columns:
            db.execute("ALTER TABLE devices ADD COLUMN utilization_command TEXT NOT NULL DEFAULT 'show interface utilization'")
        # Correct only the old built-in typo; preserve custom commands and credentials.
        db.execute("UPDATE devices SET optics_command='show interface transceivers', "
                   "last_ssh=0, config_version=config_version+1 "
                   "WHERE kind='datacom' AND lower(trim(optics_command))='show interface tranceivers'")
    os.chmod(DB, 0o600)


class DeviceInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    host: str
    kind: str = 'ping'
    interval: int = Field(default=1, ge=1, le=300)
    ping_timeout: float = Field(default=4, ge=1, le=30, allow_inf_nan=False)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(default='', max_length=100)
    password: str = Field(default='', max_length=500)
    fingerprint: str = ''
    ports: list[str] = Field(default_factory=list, max_length=128)
    interface_type: str = 'auto'
    circuit_position: float | None = Field(default=None, ge=1, le=10000, allow_inf_nan=False)
    status_command: str = 'show interface link'
    optics_command: str = 'show interface transceivers'
    utilization_command: str = 'show interface utilization'
    circuits: list['CircuitConfigInput'] | None = Field(default=None, max_length=20)
    circuits_snapshot: dict[int, int] | None = None

    @field_validator('circuit_position', mode='before')
    @classmethod
    def valid_position(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if not re.fullmatch(r'\d+(?:[.,]\d+)?', value):
                raise ValueError('Informe uma posição como 2 ou 2.1.')
            return value.replace(',', '.')
        return value

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
        if value not in ('ping', 'datacom', 'siae'):
            raise ValueError('Tipo inválido.')
        return value

    @field_validator('interface_type')
    @classmethod
    def valid_interface_type(cls, value):
        if value not in INTERFACE_LABELS:
            raise ValueError('Selecione um tipo de interface válido.')
        return value

    @field_validator('ports')
    @classmethod
    def valid_ports(cls, value):
        if any(not re.fullmatch(r'[a-zA-Z0-9/_.:-]{1,40}', port) for port in value):
            raise ValueError('Nome de porta inválido.')
        if len(set(value)) != len(value):
            raise ValueError('Portas duplicadas.')
        return value

    @field_validator('utilization_command')
    @classmethod
    def valid_utilization_command(cls, value):
        value = value.strip()
        if not value:
            return ''
        if '{port}' in value:
            raise ValueError('Use uma consulta geral de utilização, sem {port}.')
        return cls.valid_command(value)

    @field_validator('status_command', 'optics_command')
    @classmethod
    def valid_command(cls, value):
        if value.strip().lower() == 'show interface tranceivers':
            value = 'show interface transceivers'
        if (not re.fullmatch(r'(?:show|display) [a-zA-Z0-9 /_.:{}-]{1,150}', value)
                or value.count('{port}') > 1 or '{' in value.replace('{port}', '')
                or '}' in value.replace('{port}', '')):
            raise ValueError('Use um comando show/display somente de leitura. {port} é opcional.')
        return value


class PortAliasInput(BaseModel):
    port: str
    interface_type: str = 'auto'
    display_name: str = Field(default='', max_length=120)

    @field_validator('port')
    @classmethod
    def valid_port(cls, value):
        return DeviceInput.valid_ports([value])[0]

    @field_validator('interface_type')
    @classmethod
    def valid_family(cls, value):
        if value == 'mixed':
            raise ValueError('Informe o tipo físico da porta: Gigabit ou Ten.')
        return DeviceInput.valid_interface_type(value)

    @field_validator('display_name')
    @classmethod
    def valid_alias(cls, value):
        value = value.strip()
        if re.search(r'[\x00-\x1f\x7f]', value):
            raise ValueError('O nome da porta deve ocupar uma única linha.')
        return value


class CircuitInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    host: str
    interval: int = Field(default=30, ge=10, le=300)
    port_identity: str | None = Field(default=None, max_length=80)

    @field_validator('port_identity', mode='before')
    @classmethod
    def valid_port_identity(cls, value):
        if value is None or value == '':
            return None
        if not isinstance(value, str) or not re.fullmatch(r'(?:auto|gigabit-ethernet|ten-gigabit-ethernet|hundred-gigabit-ethernet):\d+/\d+/\d+', value):
            raise ValueError('Selecione uma porta válida para o cartão do ping.')
        return value

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        return DeviceInput.clean_name(value)

    @field_validator('host')
    @classmethod
    def valid_host(cls, value):
        return DeviceInput.valid_host(value)


class CircuitConfigInput(CircuitInput):
    id: int | None = Field(default=None, ge=1)


DeviceInput.model_rebuild()


def port_alias_key(port, interface_type='auto'):
    number = re.search(r'(?<![\d/])\d+/\d+/\d+(?![\d/])', port)
    prefix_family = interface_family(port[:number.start()]) if number else ''
    return f"{prefix_family or interface_type}:{number.group() if number else port}"


def siae_consumption(trx_a_bps=None, trx_b_bps=None):
    """Combine rates in bits/s; a missing TRX must never become a zero or a total."""
    for value in (trx_a_bps, trx_b_bps):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or value < 0):
            raise ValueError('Consumo dos TRX deve ser uma taxa finita e não negativa em bps.')
    total = trx_a_bps + trx_b_bps if trx_a_bps is not None and trx_b_bps is not None else None
    if total is not None and not math.isfinite(total):
        raise ValueError('Consumo total fora do intervalo suportado.')
    return dict(trx_a_bps=trx_a_bps, trx_b_bps=trx_b_bps, total_bps=total)


def public_device(row, db=None):
    value = dict(row)
    value['has_password'] = bool(value.pop('password'))
    value['ping_backend'] = 'Windows ping.exe' if IS_WINDOWS else 'ICMP (icmplib)'
    value['ports'] = json.loads(value['ports'] or '[]')
    value['port_data'] = json.loads(value['port_data'] or '[]')
    value['port_aliases'] = json.loads(value['port_aliases'] or '{}')
    for port in value['port_data']:
        key = port_alias_key(port['name'], port.get('interface_type', value['interface_type']))
        port['custom_name'] = value['port_aliases'].get(key, '')
        port['display_name'] = port['custom_name'] or port.get('description', '')
    value['ssh_diagnostic'] = json.loads(value['ssh_diagnostic'] or '{}')
    if value['kind'] == 'siae':
        # Web login and the TRX source still need to be identified for this model.
        value['siae_consumption'] = dict(siae_consumption(), status='unconfigured')
    def read_circuits(connection):
        return [dict(row) for row in connection.execute(
            'SELECT * FROM circuits WHERE source_device_id=? ORDER BY id', (value['id'],))]
    if db is None:
        with connect() as connection:
            value['circuits'] = read_circuits(connection)
    else:
        value['circuits'] = read_circuits(db)
    return value


def public_alert(row, devices):
    """Enrich old unnamed port events without rewriting the stored history."""
    value = dict(row)
    match = re.fullmatch(
        r'Porta (?:(?P<family>(?:Hundred |Ten )?Gigabit Ethernet) )?'
        r'(?P<port>[a-zA-Z0-9/_.:-]+) (?P<change>caiu \(link down\)\.|restabelecida\.)',
        value['message'])
    device = devices.get(value['device_id'])
    if not match or not device or device['kind'] != 'datacom':
        return value
    family = next((key for key, label in INTERFACE_LABELS.items() if label == match['family']), 'auto')
    key = port_alias_key(match['port'], family)
    aliases = device.get('port_aliases', {})
    readings = {port_alias_key(p['name'], p.get('interface_type', device.get('interface_type', 'auto'))): p
                for p in device.get('port_data', [])}
    if key.startswith('auto:'):
        # Legacy numeric-only events cannot choose between Giga and Ten.
        number = key.split(':', 1)[1]
        candidates = {k for k in readings.keys() | aliases.keys() if k.split(':', 1)[1] == number}
        if len(candidates) != 1:
            return value
        key = candidates.pop()
    name = aliases.get(key) or readings.get(key, {}).get('description', '')
    if name:
        prefix = f"{match['family']} " if match['family'] else ''
        value['message'] = f"Porta {prefix}{match['port']} ({name}) {match['change']}"
    return value


def alert(db, device, level, message):
    db.execute('INSERT INTO alerts(device_id,device_name,at,level,message) VALUES(?,?,?,?,?)',
               (device['id'], device['name'], now(), level, message))


def record_ping(device_id, success, latency=None, error=None, expected_version=None, started_at=None, detail=None):
    """Only completed ICMP probes count as packet loss; local errors do not."""
    with LOCK, connect() as db:
        device = db.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone()
        if not device or (expected_version is not None and device['config_version'] != expected_version):
            return
        ping_at = started_at if started_at is not None else time.time()
        db.execute('UPDATE devices SET ping_detail=? WHERE id=?', ((detail or error or ('Resposta ICMP recebida.' if success else 'Sem resposta ICMP.'))[:5000], device_id))
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


class PingCollectionError(Exception):
    """Local execution failures must not count as missing echo replies."""


def windows_ping(host, timeout):
    address = ipaddress.ip_address(host)
    executable = str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'PING.EXE')
    args = [executable, '-4' if address.version == 4 else '-6', '-n', '1', '-w', str(round(timeout * 1000)), str(address)]
    try:
        result = subprocess.run(args, capture_output=True, encoding='oem', errors='replace',
                                timeout=timeout + 2, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PingCollectionError('Não foi possível executar o ping do Windows. Verifique se ping.exe está disponível.') from exc
    output = (result.stdout + '\n' + result.stderr).strip()
    local_failure = re.search(r'general failure|transmit failed|falha geral|falha na transmiss[aã]o|access (?:is )?denied|acesso negado', output, re.I)
    if local_failure or result.returncode not in (0, 1):
        raise PingCollectionError('Falha local do ping do Windows.\n' + output[:4000])
    for line in output.splitlines():
        # A Windows unreachable reply can exit zero: require an actual target echo.
        target = r'(?<![\w:.%])' + re.escape(str(address)) + r'(?::\s|\s|\])'
        if not re.search(target, line, re.I):
            continue
        timing = re.search(r'(?:time|tempo)\s*([=<])\s*(\d+(?:[.,]\d+)?)\s*ms', line, re.I)
        echo = bool(re.search(r'\bTTL\s*=\s*\d+', line, re.I)) if address.version == 4 else bool(timing)
        if echo:
            # Windows reports integer milliseconds; <1ms is below that resolution.
            latency = (0.0 if timing.group(1) == '<' else float(timing.group(2).replace(',', '.'))) if timing else None
            return True, latency, output
    loss = re.search(r'timed out|tempo limite|inacess[ií]vel|unreachable|TTL (?:expired|expirad)|100%|100\s*%|limite de saltos', output, re.I)
    if loss:
        return False, None, output
    raise PingCollectionError('Não foi possível interpretar o resultado do ping do Windows.\n' + output[:4000])


def check_ping(device):
    started_at = time.time()
    version = device.get('config_version')
    timeout = device.get('ping_timeout', 4)
    try:
        if IS_WINDOWS:
            success, latency, detail = windows_ping(device['host'], timeout)
        else:
            result = ping(device['host'], count=1, timeout=timeout, privileged=False, payload_size=32)
            success, latency = result.is_alive, result.avg_rtt if result.is_alive else None
            detail = f'ICMP: resposta em {latency:.2f} ms.' if success else f'Sem resposta ICMP dentro de {timeout:g} segundos.'
        record_ping(device['id'], success, latency, expected_version=version,
                    started_at=started_at, detail=detail)
    except Exception as exc:
        error = str(exc).splitlines()[0] if isinstance(exc, PingCollectionError) else 'Não foi possível executar ICMP. Verifique as permissões e a rede do servidor.'
        record_ping(device['id'], False, error=error, expected_version=version,
                    started_at=started_at, detail=f'{error}\n{type(exc).__name__}: {exc}'[:5000])


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
    return output.replace('\r\n', '\n').replace('\r', '\n').replace('\u2212', '-').replace('\xa0', ' ')


class InterfaceSelectionError(paramiko.SSHException):
    """A numeric ID can refer to different physical interface families."""


def interface_family(prefix):
    compact = re.sub(r'[^a-z0-9]', '', prefix.lower())
    aliases = {
        'hundred-gigabit-ethernet': ('hundredgigabitethernet', '100gigabitethernet', '100ge', 'hu', 'ce'),
        'ten-gigabit-ethernet': ('tengigabitethernet', '10gigabitethernet', 'xgigabitethernet', '10ge', 'xge', 'te', 'xe', 'ten'),
        'gigabit-ethernet': ('gigabitethernet', '1gigabitethernet', '1ge', 'ge', 'gi', 'giga'),
    }
    for family, names in aliases.items():
        for name in names:
            if compact.startswith(name) and compact[len(name):] in ('', 'interface', 'interfaces'):
                return family
    return ''


def interface_blocks(output):
    """Keep section headers and explicit prefixes attached to their own rows."""
    row_pattern = re.compile(
        r'^\s*(?:\|\s*)?(?:Interface\s*:\s*)?'
        r'(?:(?P<prefix>hundred[ _-]*gigabit[ _-]*ethernet|100[ _-]*(?:gigabit[ _-]*ethernet|ge)|'
        r'ten[ _-]*gigabit[ _-]*ethernet|10[ _-]*(?:gigabit[ _-]*ethernet|ge)|'
        r'xgigabit[ _-]*ethernet|gigabit[ _-]*ethernet|1[ _-]*(?:gigabit[ _-]*ethernet|ge)|xge|ge|gi|te|xe|hu|ce)[ _:-]*)?'
        r'(?P<number>\d+/\d+/\d+)(?=\s|[|:]|$)', re.I)
    blocks, headers = [], []
    section_family = ''
    current = None
    for line in clean_cli(output).splitlines():
        if re.match(r'^\s*[^:]+?Interfaces?\s*:?\s*$', line, re.I):
            current = None
            section_family = interface_family(line.rstrip(':'))
            headers = [line]
            continue
        row = row_pattern.match(line)
        if row:
            current = {'number': row['number'], 'family': interface_family(row['prefix'] or '') or section_family,
                       'header': '\n'.join(headers), 'lines': [line]}
            blocks.append(current)
        elif current is not None:
            current['lines'].append(line)
        else:
            headers.append(line)
    return blocks


def matching_interface_blocks(port, output, interface_type='auto'):
    number = re.search(r'(?<![\d/])\d+/\d+/\d+(?![\d/])', port)
    if not number:
        return []
    requested_family = interface_family(port[:number.start()])
    if interface_type not in ('auto', 'mixed') and requested_family and requested_family != interface_type:
        return []
    family = requested_family or (interface_type if interface_type not in ('auto', 'mixed') else '')
    matches = [row for row in interface_blocks(output) if row['number'] == number.group()]
    if family:
        typed = [row for row in matches if row['family'] == family]
        # Unlabelled single-family command output is still usable, but a known
        # different family must never supply a state or optical measurement.
        matches = typed if any(row['family'] for row in matches) else matches
    identities = {row['family'] for row in matches}
    if len(identities) > 1 or (identities == {''} and len({row['lines'][0].strip() for row in matches}) > 1):
        if family:
            raise InterfaceSelectionError(f'Não foi possível separar a porta {number.group()} como '
                                          f'{INTERFACE_LABELS[family]}. Confira o diagnóstico da consulta abaixo.')
        raise InterfaceSelectionError(f'A porta {number.group()} aparece em mais de um tipo ou seção. '
                                      'Edite o Datacom e selecione Gigabit, Ten Gigabit ou Hundred Gigabit.')
    # Some firmware emits RX and TX on separate rows of the same typed interface.
    # This is not a different physical port; keep all rows in the same family.
    unique = {}
    for row in matches:
        unique.setdefault((row['family'], tuple(row['lines'])), row)
    return list(unique.values())


def port_lines(port, output, interface_type='auto'):
    matches = matching_interface_blocks(port, output, interface_type)
    states = set()
    chunks = []
    for row in matches:
        state = re.match(r'^\s*(?:\|\s*)?(?:[a-z _:-]+)?\d+/\d+/\d+\s+(up|down)\b', row['lines'][0], re.I)
        if state:
            states.add(state.group(1).lower())
        chunks.append('\n'.join(filter(None, [row['header'], *row['lines']])))
    if len(states) > 1:
        raise InterfaceSelectionError(f'A porta {port} tem estados Up e Down conflitantes na mesma seção. '
                                      'Confira o diagnóstico da consulta abaixo.')
    return '\n'.join(chunks)


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


def utilization_values(output):
    """Read explicitly labelled rates/percentages, never packet or byte counters."""
    result = dict(rx_bps=None, tx_bps=None, l2_rx_bps=None, l2_tx_bps=None, rx_percent=None, tx_percent=None)
    number = r'\d+(?:[.,]\d+)?'
    unit = r'(?:[kmgt]?(?:bps|bits?/s)|%)'

    def store(label, cell):
        direction = re.search(r'\b(rx|tx|input|output|ingress|egress|receive|transmit|entrada|sa[ií]da)\b', label, re.I)
        if not direction or re.search(r'\b(?:packets?|pkts?|pps|bytes?|octets?|errors?|discards?)\b', label, re.I):
            return
        measurement = re.fullmatch(r'\s*(' + number + r')\s*(' + unit + r')?\s*', cell, re.I)
        if not measurement:
            return
        units = measurement[2] or next(iter(re.findall(unit, label, re.I)), '')
        if not units or 'B' in units:
            return
        value = float(measurement[1].replace(',', '.'))
        direction = 'rx' if direction[1].lower() in ('rx', 'input', 'ingress', 'receive', 'entrada') else 'tx'
        if units == '%':
            if value <= 100:
                result[direction + '_percent'] = value
        else:
            scale = {'k': 1e3, 'm': 1e6, 'g': 1e9, 't': 1e12}.get(units[0].lower(), 1)
            layer = 'l2_' if re.search(r'\bL2\b', label, re.I) else ''
            result[layer + direction + '_bps'] = value * scale

    # Explicit labels on a row or on separate lines.
    for label, cell in re.findall(
            r'\b((?:L[12]\s+)?(?:rx|tx|input|output|ingress|egress|receive|transmit|entrada|sa[ií]da)'
            r'(?:\s+(?:rate|utilization|bandwidth))?\s*[:=]?)\s*('
            + number + r'\s*' + unit + r')(?=\s|[|,;]|$)', output, re.I):
        store(label, cell)
    # Table headers carry direction and unit when cells contain only numbers.
    for block in interface_blocks(output):
        row = block['lines'][0]
        port = re.search(r'\d+/\d+/\d+', row)
        tail = row[port.end():].strip().strip('|').strip()
        cells = [c.strip() for c in tail.split('|')] if '|' in tail else re.split(r'\s{2,}', tail)
        if len(cells) == 1:
            cells = re.findall(number + r'(?:\s*' + unit + r')?|\S+', tail, re.I)
        for header in block['header'].splitlines():
            layers = re.findall(r'\bL[12]\s+(?:RX|TX)\b', header, re.I)
            if layers and len(layers) == len(cells):
                for label, cell in zip(layers, cells):
                    store(label, cell)
                continue
            columns = [c.strip() for c in header.strip().strip('|').split('|')] if '|' in header else re.split(r'\s{2,}', header.strip())
            if len(columns) == len(cells) + 1:
                for label, cell in zip(columns[1:], cells):
                    store(label, cell)
    return result


def collect_utilization(client, device, ports):
    """A missing traffic command must not hide link and optical monitoring."""
    command = device.get('utilization_command', 'show interface utilization')
    output, error = '', None
    if command:
        try:
            output = ssh_read(client, command)
        except CommandRejected as exc:
            error = str(exc)
        except Exception:
            error = 'Não foi possível consultar a utilização nesta leitura.'
    for port in ports:
        values = dict(rx_bps=None, tx_bps=None, l2_rx_bps=None, l2_tx_bps=None, rx_percent=None, tx_percent=None)
        port_error = error
        if output:
            try:
                selected = port_lines(port['name'], output, port['interface_type'])
                values = utilization_values(selected)
            except InterfaceSelectionError as exc:
                port_error = str(exc)
        port.update(values, utilization_output=output, utilization_error=port_error,
                    utilization_enabled=bool(command))


class CommandRejected(paramiko.SSHException):
    """A device can reject a CLI command while SSH still reports exit code zero."""


def ssh_read(client, command):
    _, stdout, stderr = client.exec_command(command, timeout=7)
    output = stdout.read(65536).decode('utf-8', 'replace')
    error = stderr.read(4096).decode('utf-8', 'replace')
    rejected = re.search(
        r'syntax\s+error\s*:|^\s*%?\s*(?:unknown|invalid|unrecognized|incomplete|ambiguous)\s+(?:command|argument|input)\b',
        clean_cli(output), re.I | re.M)
    if stdout.channel.recv_exit_status() not in (0, -1) or error.strip() or rejected:
        raise CommandRejected(f'O equipamento rejeitou o comando "{command}". '
                              'Confira a sintaxe em Editar → Comandos do equipamento.')
    return output


def check_ssh(device):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(VerifyFingerprint(device['fingerprint']))
    ports = []
    error = None
    diagnostic = {'interface_type': device.get('interface_type', 'auto'), 'stage': 'conexão SSH',
                  'status_command': device['status_command'], 'optics_command': device['optics_command'],
                  'status_output': '', 'optics_output': ''}
    try:
        client.connect(device['host'], port=device['ssh_port'], username=device['username'],
                       password=CIPHER.decrypt(device['password'].encode()).decode(),
                       timeout=6, auth_timeout=6, banner_timeout=6, look_for_keys=False, allow_agent=False)
        diagnostic['stage'] = 'consulta de portas'
        status_bulk = None if '{port}' in device['status_command'] else ssh_read(client, device['status_command'])
        diagnostic['status_output'] = status_bulk or ''
        diagnostic['stage'] = 'consulta de sinais'
        optics_bulk = None if '{port}' in device['optics_command'] else ssh_read(client, device['optics_command'])
        diagnostic['optics_output'] = optics_bulk or ''
        diagnostic['stage'] = 'identificação das portas'
        interface_type = device.get('interface_type', 'auto')
        selected_ports = json.loads(device['ports'])
        if not selected_ports and status_bulk is not None:
            rows = interface_blocks(status_bulk)
            if interface_type != 'auto':
                typed = [row for row in rows if row['family'] == interface_type]
                rows = typed if any(row['family'] for row in rows) else rows
            selected_ports = list(dict.fromkeys(row['number'] for row in rows))[:128]
            if not selected_ports:
                raise InterfaceSelectionError(f'Nenhuma interface {INTERFACE_LABELS[interface_type]} encontrada. '
                                              'Confira o tipo selecionado e a saída do comando de portas.')
        for port in selected_ports:
            query_port, query_type = port, interface_type
            if interface_type == 'mixed':
                number = re.search(r'(?<![\d/])\d+/\d+/\d+(?![\d/])', port)
                query_port = number.group()
                query_type = interface_family(port[:number.start()])
            diagnostic['stage'] = f"portas: {query_type} {query_port}" if interface_type == 'mixed' else f"portas: {port}"
            status_raw = ssh_read(client, device['status_command'].replace('{port}', port)) if status_bulk is None else status_bulk
            diagnostic['status_output'] = status_raw
            status = status_raw if status_bulk is None and not interface_blocks(status_raw) else port_lines(query_port, status_raw, query_type)
            status_rows = matching_interface_blocks(query_port, status_raw, query_type)
            family = status_rows[0]['family'] if status_rows else ''
            family = family or (query_type if query_type != 'auto' else 'auto')
            diagnostic['stage'] = f"sinais: {port}"
            optics_raw = ssh_read(client, device['optics_command'].replace('{port}', port)) if optics_bulk is None else optics_bulk
            diagnostic['optics_output'] = optics_raw
            optics = optics_raw if optics_bulk is None and not interface_blocks(optics_raw) else port_lines(query_port, optics_raw, family)
            result = parse_port(query_port, status, optics, optics_context=optics)
            result.update(interface_type=family, identity=f'{family}:{query_port}',
                          status_output=status_raw, optics_output=optics_raw)
            ports.append(result)
        collect_utilization(client, device, ports)
    except (CommandRejected, InterfaceSelectionError) as exc:
        error = str(exc)
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
            db.execute('UPDATE devices SET ssh_error=?,last_ssh=?,ssh_diagnostic=? WHERE id=?',
                       (error, time.time(), json.dumps(diagnostic), device['id']))
        else:
            previous = {p.get('identity', f"{p.get('interface_type', 'auto')}:{p['name']}"): p for p in json.loads(current['port_data'])}
            aliases = json.loads(current['port_aliases'] or '{}')
            for port in ports:
                old = previous.get(port['identity'], {}).get('state')
                label = (INTERFACE_LABELS[port['interface_type']] + ' ') if port['interface_type'] != 'auto' else ''
                display_name = aliases.get(port_alias_key(port['name'], port['interface_type'])) or port.get('description', '')
                alias_label = f' ({display_name})' if display_name else ''
                if port['state'] == 'down' and old != 'down':
                    alert(db, current, 'critical', f"Porta {label}{port['name']}{alias_label} caiu (link down).")
                elif port['state'] == 'up' and old == 'down':
                    alert(db, current, 'success', f"Porta {label}{port['name']}{alias_label} restabelecida.")
            db.execute("UPDATE devices SET ssh_error=NULL,last_ssh=?,port_data=?,ssh_diagnostic='{}' WHERE id=?",
                       (time.time(), json.dumps(ports), device['id']))


def record_circuit(circuit, device, result=None, error=None, output='', started_at=None):
    with LOCK, connect() as db:
        current = db.execute('SELECT * FROM circuits WHERE id=?', (circuit['id'],)).fetchone()
        parent = db.execute('SELECT * FROM devices WHERE id=?', (device['id'],)).fetchone()
        if (not current or not parent or parent['kind'] != 'datacom'
                or current['source_device_id'] != device['id']
                or current['config_version'] != circuit['config_version']
                or parent['config_version'] != device['config_version']):
            return
        at = now()
        polled = started_at if started_at is not None else time.time()
        if error:
            if current['error'] != error:
                alert(db, parent, 'warning', f"Circuito {current['name']} ({current['host']}): {error}")
            db.execute("UPDATE circuits SET state='error',error=?,last_check=?,last_poll=?,output=?,latency=NULL,transmitted=NULL,received=NULL WHERE id=?",
                       (error, at, polled, output[:16000], circuit['id']))
            return
        failures = current['failures']
        for success in result['probes']:
            if success:
                if failures > 20:
                    alert(db, parent, 'success', f"Circuito {current['name']} ({current['host']}) voltou a responder pelo Datacom.")
                failures = 0
            else:
                failures += 1
                if failures == 21:
                    alert(db, parent, 'critical', f"Circuito {current['name']} ({current['host']}): sem ping pelo Datacom, após 21 perdas consecutivas.")
        status = 'offline' if failures > 20 else 'unstable' if failures else 'online'
        db.execute('UPDATE circuits SET state=?,failures=?,latency=?,last_check=?,last_poll=?,output=?,error=NULL,transmitted=?,received=? WHERE id=?',
                   (status, failures, result['latency'], at, polled, output[:16000], result['transmitted'], result['received'], circuit['id']))
        db.execute('DELETE FROM alerts WHERE id NOT IN (SELECT id FROM alerts ORDER BY id DESC LIMIT 1000)')


def check_circuit(circuit, device):
    with LOCK, connect() as db:
        current = db.execute('SELECT * FROM circuits WHERE id=?', (circuit['id'],)).fetchone()
        source = db.execute('SELECT * FROM devices WHERE id=?', (device['id'],)).fetchone()
        if (not current or not source or source['kind'] != 'datacom'
                or current['source_device_id'] != device['id']
                or current['config_version'] != circuit['config_version']
                or source['config_version'] != device['config_version']):
            return
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(VerifyFingerprint(device['fingerprint']))
    started_at, output = time.time(), ''
    try:
        client.connect(device['host'], port=device['ssh_port'], username=device['username'],
                       password=CIPHER.decrypt(device['password'].encode()).decode(), timeout=6,
                       auth_timeout=6, banner_timeout=6, look_for_keys=False, allow_agent=False)
        output = read_remote_ping(client, circuit['host'], cancelled=STOP.is_set)
        result = parse_remote_ping(circuit['host'], output)
    except RemotePingError as exc:
        if not STOP.is_set():
            record_circuit(circuit, device, error=str(exc), output=exc.output, started_at=started_at)
    except paramiko.AuthenticationException:
        record_circuit(circuit, device, error='Autenticação SSH recusada no Datacom de origem.', started_at=started_at)
    except Exception:
        record_circuit(circuit, device, error='Falha na consulta SSH. Verifique o acesso e a chave do Datacom de origem.', started_at=started_at)
    else:
        record_circuit(circuit, device, result=result, output=output, started_at=started_at)
    finally:
        client.close()


def run_circuit_check(circuit, device):
    try:
        if not STOP.is_set():
            check_circuit(circuit, device)
    finally:
        with LOCK:
            INFLIGHT.discard((circuit['id'], 'circuit'))


def run_check(device, kind):
    try:
        (check_ping if kind == 'ping' else check_ssh)(device)
    finally:
        with LOCK:
            INFLIGHT.discard((device['id'], kind))


def monitor():
    # Remote CLI pings can take several seconds; keep them off the local ping pool.
    with ThreadPoolExecutor(max_workers=12) as pool, ThreadPoolExecutor(max_workers=4) as remote_pool:
        while not STOP.is_set():
            with LOCK, connect() as db:
                devices = db.execute('SELECT * FROM devices').fetchall()
                by_id = {row['id']: dict(row) for row in devices}
                for row in devices:
                    device = dict(row)
                    for kind, due in [('ping', time.time() - device['last_ping'] >= device['interval']),
                                      ('ssh', device['kind'] == 'datacom' and time.time() - device['last_ssh'] >= 30)]:
                        key = (device['id'], kind)
                        if due and key not in INFLIGHT:
                            INFLIGHT.add(key)
                            pool.submit(run_check, device, kind)
                for row in db.execute('SELECT * FROM circuits'):
                    circuit = dict(row)
                    device = by_id.get(circuit['source_device_id'])
                    key = (circuit['id'], 'circuit')
                    if device and device['kind'] == 'datacom' and time.time() - circuit['last_poll'] >= circuit['interval'] and key not in INFLIGHT:
                        INFLIGHT.add(key)
                        remote_pool.submit(run_circuit_check, circuit, device)
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


app = FastAPI(title='VELOSONET MONITORAMENTO', lifespan=lifespan)
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
        devices = [public_device(row, db) for row in db.execute('SELECT * FROM devices ORDER BY id')]
        by_id = {device['id']: device for device in devices}
        events = [public_alert(row, by_id) for row in db.execute('SELECT * FROM alerts ORDER BY id DESC LIMIT 60')]
        samples = [dict(row) for row in db.execute('SELECT * FROM samples ORDER BY id DESC LIMIT 720')][::-1]
    return dict(devices=devices, alerts=events, samples=samples, demo=False, updated_at=now())


def device_values(device, previous=None):
    values = device.model_dump(exclude={'circuits', 'circuits_snapshot'})
    if device.kind != 'datacom' and device.circuits:
        raise HTTPException(422, 'IPs de circuitos devem ser configurados em um Datacom.')
    password = device.password
    saved_password = previous['password'] if previous and previous['kind'] == 'datacom' else ''
    if device.kind == 'datacom' and (not device.username or not (password or saved_password)
            or not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}', device.fingerprint)):
        raise HTTPException(422, 'Datacom requer usuário, senha e impressão digital SSH SHA256 verificada.')
    if device.kind == 'datacom' and not device.ports and ('{port}' in device.status_command or '{port}' in device.optics_command):
        raise HTTPException(422, 'Informe as portas ao usar comandos com {port}.')
    if device.kind == 'datacom' and device.interface_type == 'mixed':
        if not device.ports:
            raise HTTPException(422, 'Informe ao menos uma porta na lista Ten ou Giga.')
        if '{port}' in device.status_command or '{port}' in device.optics_command:
            raise HTTPException(422, 'No modo Gigabit + Ten, use consultas gerais sem {port}, como show interface link e show interface transceivers.')
        for port in device.ports:
            qualified = re.fullmatch(r'(?P<prefix>[a-zA-Z][a-zA-Z:-]*?)(?P<number>\d+/\d+/\d+)', port)
            family = interface_family(qualified['prefix']) if qualified else ''
            if family not in ('gigabit-ethernet', 'ten-gigabit-ethernet'):
                raise HTTPException(422, 'Identifique cada porta com ten:1/1/10 ou giga:1/1/19 no modo misto.')
    values['ports'] = json.dumps(values['ports'])
    values['password'] = (CIPHER.encrypt(password.encode()).decode() if password else saved_password) if device.kind == 'datacom' else ''
    return values


def check_circuit_snapshot(db, device_id, snapshot):
    if snapshot is not None:
        current = {row['id']: row['config_version'] for row in db.execute('SELECT id,config_version FROM circuits WHERE source_device_id=?', (device_id,))}
        if current != snapshot:
            raise HTTPException(409, 'Os IPs deste Datacom foram alterados em outra consulta. Reabra a edição para atualizar a lista.')


def save_device_circuits(db, device_id, entries):
    if entries is None:
        return  # Older clients that omit the list must keep existing circuits.
    existing = {row['id']: dict(row) for row in db.execute('SELECT * FROM circuits WHERE source_device_id=?', (device_id,))}
    ids = [entry.id for entry in entries if entry.id is not None]
    if len(ids) != len(set(ids)) or any(circuit_id not in existing for circuit_id in ids):
        raise HTTPException(422, 'A lista contém um circuito inválido ou de outro Datacom. Reabra a edição.')
    if len({entry.host for entry in entries}) != len(entries):
        raise HTTPException(422, 'Cada IP deve aparecer apenas uma vez neste Datacom.')
    total = db.execute('SELECT count(*) FROM circuits').fetchone()[0]
    if total - len(existing) + len(entries) > 100:
        raise HTTPException(422, 'Limite de 100 circuitos no painel.')
    selected = {entry.id: entry for entry in entries if entry.id is not None}
    # Remove changed targets first so two retained circuits can swap addresses
    # without violating the unique source/IP index. IDs and version guards stay.
    for circuit_id, old in existing.items():
        entry = selected.get(circuit_id)
        if entry is None or entry.host != old['host']:
            db.execute('DELETE FROM circuits WHERE id=?', (circuit_id,))
    for entry in entries:
        old = existing.get(entry.id)
        binding = entry.port_identity if 'port_identity' in entry.model_fields_set else old.get('port_identity') if old else None
        if old is None:
            db.execute('INSERT INTO circuits(source_device_id,name,host,interval,port_identity) VALUES(?,?,?,?,?)',
                       (device_id, entry.name, entry.host, entry.interval, binding))
        elif old['host'] != entry.host:
            db.execute('INSERT INTO circuits(id,source_device_id,name,host,interval,config_version,port_identity) VALUES(?,?,?,?,?,?,?)',
                       (entry.id, device_id, entry.name, entry.host, entry.interval, old['config_version'] + 1, binding))
        elif old['name'] != entry.name or old['interval'] != entry.interval or old['port_identity'] != binding:
            db.execute('UPDATE circuits SET name=?,interval=?,port_identity=?,last_poll=0,config_version=config_version+1 WHERE id=?',
                       (entry.name, entry.interval, binding, entry.id))


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
        check_circuit_snapshot(db, cursor.lastrowid, device.circuits_snapshot)
        save_device_circuits(db, cursor.lastrowid, device.circuits)
        result = public_device(db.execute('SELECT * FROM devices WHERE id=?', (cursor.lastrowid,)).fetchone(), db)
    return result


@app.put('/api/devices/{device_id}')
def update_device(device_id: int, device: DeviceInput):
    with LOCK, connect() as db:
        previous = db.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone()
        if not previous:
            raise HTTPException(404, 'Equipamento não encontrado.')
        if device.circuits is not None:
            check_circuit_snapshot(db, device_id, device.circuits_snapshot)
        if device.kind != 'datacom' and db.execute('SELECT 1 FROM circuits WHERE source_device_id=?', (device_id,)).fetchone():
            raise HTTPException(422, 'Remova os circuitos vinculados antes de alterar o tipo do Datacom.')
        values = device_values(device, previous)
        if 'circuit_position' not in device.model_fields_set:
            values['circuit_position'] = previous['circuit_position']
        if 'utilization_command' not in device.model_fields_set:
            values['utilization_command'] = previous['utilization_command']
        if db.execute('SELECT id FROM devices WHERE host=? AND kind=? AND id<>?',
                      (device.host, device.kind, device_id)).fetchone():
            raise HTTPException(409, 'Este IP já está cadastrado para este tipo de monitoramento.')
        changed_target = device.host != previous['host'] or device.kind != previous['kind']
        changed_ssh = any(values[key] != previous[key] for key in
                          ('ssh_port', 'username', 'password', 'fingerprint', 'ports', 'interface_type', 'status_command', 'optics_command', 'utilization_command'))
        if changed_target:
            db.execute('DELETE FROM samples WHERE device_id=?', (device_id,))
            values.update(state='pending', failures=0, latency=None, last_check=None, ping_detail=None)
        if changed_target or changed_ssh:
            values.update(port_data='[]', ssh_error=None, ssh_diagnostic='{}')
        changed_source = any(values[key] != previous[key] for key in ('host', 'kind', 'ssh_port', 'username', 'password', 'fingerprint'))
        if changed_source:
            db.execute("UPDATE circuits SET state='pending',failures=0,latency=NULL,last_check=NULL,last_poll=0,output='',error=NULL,transmitted=NULL,received=NULL,config_version=config_version+1 WHERE source_device_id=?", (device_id,))
        values.update(config_version=previous['config_version'] + 1, last_ping=0, last_ssh=0)
        assignments = ','.join(f'{column}=?' for column in values)
        db.execute(f'UPDATE devices SET {assignments} WHERE id=?', (*values.values(), device_id))
        save_device_circuits(db, device_id, device.circuits)
        return public_device(db.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone(), db)


@app.post('/api/devices/{device_id}/circuits', status_code=201)
def create_circuit(device_id: int, entry: CircuitInput):
    with LOCK, connect() as db:
        parent = db.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone()
        if not parent:
            raise HTTPException(404, 'Datacom não encontrado.')
        if parent['kind'] != 'datacom':
            raise HTTPException(422, 'Selecione um Datacom como origem do ping.')
        if db.execute('SELECT id FROM circuits WHERE source_device_id=? AND host=?', (device_id, entry.host)).fetchone():
            raise HTTPException(409, 'Este IP já está monitorado por este Datacom.')
        if db.execute('SELECT count(*) FROM circuits').fetchone()[0] >= 100 or db.execute('SELECT count(*) FROM circuits WHERE source_device_id=?', (device_id,)).fetchone()[0] >= 20:
            raise HTTPException(422, 'Limite de 20 circuitos por Datacom e 100 circuitos no painel.')
        cursor = db.execute('INSERT INTO circuits(source_device_id,name,host,interval,port_identity) VALUES(?,?,?,?,?)',
                            (device_id, entry.name, entry.host, entry.interval, entry.port_identity))
        return dict(db.execute('SELECT * FROM circuits WHERE id=?', (cursor.lastrowid,)).fetchone())


@app.put('/api/circuits/{circuit_id}')
def update_circuit(circuit_id: int, entry: CircuitInput):
    with LOCK, connect() as db:
        current = db.execute('SELECT * FROM circuits WHERE id=?', (circuit_id,)).fetchone()
        if not current:
            raise HTTPException(404, 'Circuito não encontrado.')
        if db.execute('SELECT id FROM circuits WHERE source_device_id=? AND host=? AND id<>?',
                      (current['source_device_id'], entry.host, circuit_id)).fetchone():
            raise HTTPException(409, 'Este IP já está monitorado por este Datacom.')
        binding = entry.port_identity if 'port_identity' in entry.model_fields_set else current['port_identity']
        db.execute('UPDATE circuits SET name=?,host=?,interval=?,port_identity=?,last_poll=0,config_version=config_version+1 WHERE id=?',
                   (entry.name, entry.host, entry.interval, binding, circuit_id))
        if current['host'] != entry.host:
            db.execute("UPDATE circuits SET state='pending',failures=0,latency=NULL,last_check=NULL,output='',error=NULL,transmitted=NULL,received=NULL WHERE id=?", (circuit_id,))
        return dict(db.execute('SELECT * FROM circuits WHERE id=?', (circuit_id,)).fetchone())


@app.delete('/api/circuits/{circuit_id}', status_code=204)
def delete_circuit(circuit_id: int):
    with LOCK, connect() as db:
        if not db.execute('SELECT id FROM circuits WHERE id=?', (circuit_id,)).fetchone():
            raise HTTPException(404, 'Circuito não encontrado.')
        db.execute('DELETE FROM circuits WHERE id=?', (circuit_id,))


@app.post('/api/circuits/{circuit_id}/check', status_code=202)
def request_circuit_check(circuit_id: int):
    with LOCK, connect() as db:
        if not db.execute('SELECT id FROM circuits WHERE id=?', (circuit_id,)).fetchone():
            raise HTTPException(404, 'Circuito não encontrado.')
        db.execute('UPDATE circuits SET last_poll=0 WHERE id=?', (circuit_id,))
    return {'status': 'scheduled'}


@app.patch('/api/devices/{device_id}/port-name')
def update_port_alias(device_id: int, entry: PortAliasInput):
    with LOCK, connect() as db:
        device = db.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone()
        if not device:
            raise HTTPException(404, 'Equipamento não encontrado.')
        if device['kind'] != 'datacom':
            raise HTTPException(422, 'Nomes de portas são configurados nos Datacoms.')
        family = entry.interface_type
        if family == 'auto' and device['interface_type'] not in ('auto', 'mixed'):
            family = device['interface_type']
        key = port_alias_key(entry.port, family)
        if device['interface_type'] == 'mixed' and key.startswith('auto:'):
            raise HTTPException(422, 'Selecione Gigabit ou Ten para nomear esta porta.')
        aliases = json.loads(device['port_aliases'] or '{}')
        if entry.display_name:
            if key not in aliases and len(aliases) >= 512:
                raise HTTPException(422, 'Limite de 512 nomes personalizados por Datacom.')
            aliases[key] = entry.display_name
        else:
            aliases.pop(key, None)
        db.execute('UPDATE devices SET port_aliases=? WHERE id=?', (json.dumps(aliases), device_id))
        return public_device(db.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone(), db)


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
              ('Datacom • Distribuição sul', '10.0.4.1', 'datacom', 'online', 4.1),
              ('SIAE • Enlace principal', '192.0.2.70', 'siae', 'online', 2.8),
              ('SIAE • Enlace secundário', '192.0.2.71', 'siae', 'unstable', None)]
    for i, (name, host, kind, state, latency) in enumerate(labels, 1):
        ports = [] if kind != 'datacom' else [dict(name=f'ge1/1/{p}', description=f'Enlace de demonstração {p}', state='down' if i == 2 and p == 3 else 'up', rx=None if i == 2 and p == 3 else round(-8.3-p*1.2, 2), tx=-2.1,
            rx_bps=0 if i == 2 and p == 3 else p*120e6, tx_bps=0 if i == 2 and p == 3 else p*30e6,
            l2_rx_bps=0 if i == 2 and p == 3 else p*115e6, l2_tx_bps=0 if i == 2 and p == 3 else p*28e6,
            utilization_enabled=True, utilization_output='Banda simulada para demonstração.',
            checked_at=now(), status_output='Exemplo de saída simulada', optics_output='Dados de demonstração') for p in range(1, 5)]
        devices.append(dict(id=i, name=name, host=host, kind=kind, state=state, failures=24 if state == 'offline' else 7 if state == 'unstable' else 0, latency=latency, last_check=now(), interval=5, ports=[p['name'] for p in ports], port_data=ports, ssh_error=None))
        devices[-1]['circuits'] = [] if kind != 'datacom' or i != 1 else [dict(
            id=i, source_device_id=i, name='Circuito de demonstração', host=f'10.91.{i-1}.2',
            interval=30, state='online', failures=0, latency=3.204, last_check=now(),
            transmitted=5, received=5, error=None, output='Exemplo de ping simulado: 5 respostas, 0% de perda.')]
        if devices[-1]['circuits']:
            devices[-1]['circuits'][0]['port_identity'] = 'gigabit-ethernet:1/1/1'
        if kind == 'siae':
            devices[-1]['siae_consumption'] = dict(siae_consumption(120e6, 80e6), status='demo')
    samples = [dict(device_id=1, at=datetime.fromtimestamp(time.time()-(59-i)*5, timezone.utc).isoformat(), latency=round(3 + math.sin(i*.55)*.7 + math.cos(i*.17)*.45, 2), success=1) for i in range(60)]
    events = [dict(id=3, device_id=5, device_name=labels[4][0], at=now(), level='critical', message='Sem ping: 24 perdas consecutivas.'),
              dict(id=2, device_id=2, device_name=labels[1][0], at=now(), level='critical', message='Porta ge1/1/3 caiu (link down).'),
              dict(id=1, device_id=1, device_name=labels[0][0], at=now(), level='success', message='Ping restabelecido. Equipamento online.')]
    return dict(devices=devices, alerts=[public_alert(event, {d['id']: d for d in devices}) for event in events], samples=samples, demo=True, updated_at=now())
