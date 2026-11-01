"""Consistent SQLite + Fernet-key archives; restore only into a new directory.

Usage: python backups.py restore backup.zip --destination .data-restaurada
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import uuid
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

NAME = re.compile(r'(auto|manual)-\d{8}T\d{12}Z-[0-9a-f]{8}\.zip')
LIMIT = 512 * 1024 * 1024
BACKUP_LOCK = threading.Lock()


class BackupError(ValueError):
    pass


def check_database(path, key):
    """Validate structure/integrity and all encrypted credential fields."""
    try:
        cipher = Fernet(key)
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise BackupError('O banco do backup está corrompido.')
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'devices', 'samples', 'alerts'} <= tables:
                raise BackupError('Este arquivo não contém um banco do monitoramento.')
            if db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone():
                raise BackupError('O banco contém estruturas não suportadas.')
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise BackupError('O banco contém referências inválidas.')
            columns = {r[1] for r in db.execute('PRAGMA table_info(devices)')}
            if not {'id', 'name', 'host', 'kind', 'password'} <= columns:
                raise BackupError('O cadastro de equipamentos está incompleto.')
            for column in ('password', 'siae_session', 'siae_password'):
                if column in columns:
                    for (value,) in db.execute(f'SELECT {column} FROM devices WHERE {column} IS NOT NULL AND {column}!=\'\''):
                        cipher.decrypt(value.encode())
    except BackupError:
        raise
    except (sqlite3.Error, ValueError, TypeError, AttributeError, InvalidToken):
        raise BackupError('Banco inválido ou chave incompatível com as credenciais.') from None


def catalog(directory):
    directory = Path(directory)
    result = []
    if directory.exists():
        for path in directory.iterdir():
            if NAME.fullmatch(path.name) and path.is_file() and not path.is_symlink():
                stamp = path.name.split('-')[1]
                try:
                    at = datetime.strptime(stamp, '%Y%m%dT%H%M%S%fZ').replace(tzinfo=timezone.utc).isoformat()
                except ValueError:
                    continue
                result.append(dict(name=path.name, at=at, size=path.stat().st_size,
                                   automatic=path.name.startswith('auto-')))
    return sorted(result, key=lambda item: item['at'], reverse=True)


def backup_path(directory, name):
    if not NAME.fullmatch(name):
        raise BackupError('Backup não encontrado.')
    path = Path(directory) / name
    if not path.is_file() or path.is_symlink():
        raise BackupError('Backup não encontrado.')
    return path


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def create(data, automatic=False, at=None):
    data = Path(data)
    directory = data / 'backups'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    at = at or datetime.now(timezone.utc)
    with BACKUP_LOCK:
        entries = catalog(directory)
        if automatic and any(e['automatic'] and e['at'][:10] == at.date().isoformat() for e in entries):
            return None
        name = f"{'auto' if automatic else 'manual'}-{at.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:8]}.zip"
        with tempfile.TemporaryDirectory(prefix='.snapshot-', dir=directory) as temporary:
            temporary = Path(temporary)
            snapshot = temporary / 'monitor.db'
            with closing(sqlite3.connect((data / 'monitor.db').resolve().as_uri() + '?mode=ro', uri=True)) as source:
                with closing(sqlite3.connect(snapshot)) as target:
                    source.backup(target)
            os.chmod(snapshot, 0o600)
            key = (data / 'credentials.key').read_bytes()
            check_database(snapshot, key)
            (temporary / 'credentials.key').write_bytes(key)
            os.chmod(temporary / 'credentials.key', 0o600)
            files = ('monitor.db', 'credentials.key')
            if snapshot.stat().st_size > LIMIT:
                raise BackupError('O banco ultrapassa o limite de 512 MiB por backup.')
            manifest = dict(format='velosonet-backup', version=1, created_at=at.isoformat(),
                            sha256={f: digest(temporary / f) for f in files})
            archive = temporary / 'snapshot.zip'
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr('manifest.json', json.dumps(manifest))
                for file in files:
                    z.write(temporary / file, file)
            os.chmod(archive, 0o600)
            os.replace(archive, directory / name)
        # Keep seven daily automatic copies and five manual copies, only after success.
        for automatic_type, keep in ((True, 7), (False, 5)):
            group = [entry for entry in catalog(directory) if entry['automatic'] == automatic_type]
            for entry in group[keep:]:
                (directory / entry['name']).unlink()
        return next(entry for entry in catalog(directory) if entry['name'] == name)


def restore(archive, destination):
    destination = Path(destination).absolute()
    if destination.exists():
        raise BackupError('Escolha uma pasta nova. A restauração não sobrescreve dados existentes.')
    if not destination.parent.is_dir():
        raise BackupError('A pasta de destino precisa ter uma pasta pai existente.')
    try:
        with tempfile.TemporaryDirectory(prefix='.restore-', dir=destination.parent) as temporary:
            temporary = Path(temporary)
            with zipfile.ZipFile(archive) as z:
                if len(z.infolist()) != 3 or set(z.namelist()) != {'manifest.json', 'monitor.db', 'credentials.key'}:
                    raise BackupError('Conteúdo inesperado no backup.')
                for info in z.infolist():
                    limit = LIMIT if info.filename == 'monitor.db' else 4096
                    if info.file_size > limit or info.flag_bits & 1:
                        raise BackupError('Backup muito grande ou em formato não suportado.')
                    with z.open(info) as source, (temporary / info.filename).open('xb') as target:
                        os.chmod(temporary / info.filename, 0o600)
                        shutil.copyfileobj(source, target, length=1024 * 1024)
                manifest = json.loads((temporary / 'manifest.json').read_bytes())
                if manifest.get('format') != 'velosonet-backup' or manifest.get('version') != 1:
                    raise BackupError('Formato ou versão de backup não suportado.')
                for name in ('monitor.db', 'credentials.key'):
                    if digest(temporary / name) != manifest['sha256'][name]:
                        raise BackupError('O conteúdo do backup não corresponde à verificação de integridade.')
            check_database(temporary / 'monitor.db', (temporary / 'credentials.key').read_bytes())
            # All validation precedes creating the destination. Existing data is untouched.
            destination.mkdir(mode=0o700)
            try:
                for name in ('monitor.db', 'credentials.key'):
                    shutil.copyfile(temporary / name, destination / name)
                    os.chmod(destination / name, 0o600)
            except BaseException:
                shutil.rmtree(destination)
                raise
    except BackupError:
        raise
    except (zipfile.BadZipFile, KeyError, ValueError, TypeError, AttributeError, RuntimeError, EOFError):
        raise BackupError('Não foi possível validar o arquivo de backup.') from None
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Restaura um backup VELOSONET em uma pasta nova.')
    parser.add_argument('command', choices=['restore'])
    parser.add_argument('archive', type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    try:
        restored = restore(args.archive, args.destination)
    except BackupError as error:
        parser.exit(1, f'Restauração não concluída: {error}\n')
    except OSError:
        parser.exit(1, 'Restauração não concluída. Verifique o backup, a pasta nova e as permissões.\n')
    print(f'Backup validado e restaurado em {restored}.')
    print('Com o programa parado, configure MONITOR_DATA_DIR para esta pasta e inicie novamente.')
