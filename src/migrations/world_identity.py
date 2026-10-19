"""Cold-start repair of native world IDs written before ContentRef validation.

This runs before stores/registries become live, never during config hot reload.
SQLite commits a migration identity with the ownership changes; a durable file
plan then rolls forward the matching template/save refs. An interrupted startup
resumes that plan before serving requests. User edits never get overwritten.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Iterator
from uuid import uuid4

from src.content_modules.refs import parse_content_ref
from src.migrations.world_identity_payload import rebind_lorebook_worlds, rewrite_references

JOURNAL_NAME = 'world-identity-v1.pending.json'
TABLE = 'diceframe_world_identity_migrations'


class WorldIdentityMigrationError(ValueError):
    """Unsafe or conflicting migration; startup must not publish partial data."""


def migrated_world_id(old: str) -> str:
    # Hash the old *identity*, not a translated display name. Distinct worlds
    # with identical titles stay distinct, independent of locale or file order.
    prefix = 'ai_world_' if old.startswith('ai_') else 'world_'
    return prefix + hashlib.sha256(old.encode('utf-8')).hexdigest()[:20]


def _path(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise WorldIdentityMigrationError('invalid world migration path')
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise WorldIdentityMigrationError('world migration path escapes data directory')
    return path


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError, UnicodeError) as exc:
        raise WorldIdentityMigrationError(f'invalid migration JSON: {path.name}') from exc


def _encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.world-migration-tmp')
    try:
        with temporary.open('wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _exclusive(root: Path) -> Iterator[None]:
    folder = _path(root, 'migrations')
    folder.mkdir(parents=True, exist_ok=True)
    path = _path(root, 'migrations/world-identity-v1.lock')
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise WorldIdentityMigrationError('world identity upgrade is already running') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _valid_id(identity: str) -> bool:
    try:
        parse_content_ref({'source_kind': 'world', 'source_id': identity,
                           'kind': 'lorebook', 'id': f'world:{identity}'}, default_source='')
        return True
    except ValueError:
        return False


def _record(root: Path, path: Path, before: bytes | None, after: bytes | None) -> dict:
    relative = path.relative_to(root).as_posix()
    _path(root, relative)
    return {'path': relative, 'before_sha256': hashlib.sha256(before).hexdigest() if before is not None else None,
            'after': base64.b64encode(after).decode('ascii') if after is not None else None}


def _plan(root: Path, worlds: Path) -> dict | None:
    mapping: dict[str, str] = {}
    native = {}
    for path in sorted(worlds.glob('*.json')):
        try:
            payload = _read(path)
        except WorldIdentityMigrationError:
            continue  # Unrelated malformed templates are left to their owner.
        identity = payload.get('world_id') if isinstance(payload, dict) else None
        if not isinstance(identity, str) or _valid_id(identity):
            continue
        if path.stem != identity or '/' in identity or '\\' in identity or '..' in identity:
            raise WorldIdentityMigrationError('legacy world template has ambiguous storage identity')
        if identity in native:
            raise WorldIdentityMigrationError('duplicate legacy world identity')
        native[identity] = path
        mapping[identity] = migrated_world_id(identity)
    if not mapping:
        return None
    if not worlds.is_relative_to(root):
        raise WorldIdentityMigrationError('native world migration requires templates inside the data directory')
    targets = set(mapping.values())
    if len(targets) != len(mapping):
        raise WorldIdentityMigrationError('world migration identity collision')
    for path in worlds.rglob('*.json'):
        value = _read(path)
        if isinstance(value, dict) and value.get('world_id') in targets:
            raise WorldIdentityMigrationError('target world template already exists')
    paths = set((root / 'templates').rglob('*.json'))
    paths.update((root / 'saves').glob('*/state*.json'))
    if (root / 'character_cards.json').is_file():
        paths.add(root / 'character_cards.json')
    records = []
    deletions = []
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        _path(root, relative)  # Refuse symlink escapes before reading content.
        before = path.read_bytes()
        try:
            value = json.loads(before.decode('utf-8-sig'))
        except (ValueError, UnicodeError):
            # Broken saves must not be erased or replaced by a partial rewrite.
            if path.parent.parent == root / 'saves':
                raise WorldIdentityMigrationError(f'invalid save JSON during world upgrade: {relative}')
            continue
        if path.parent.parent == root / 'saves':
            from src.migrations.instance import CURRENT_INSTANCE_SCHEMA_VERSION
            version = value.get('instance_schema_version', 1)
            if type(version) is not int or not 1 <= version <= CURRENT_INSTANCE_SCHEMA_VERSION:
                raise WorldIdentityMigrationError(f'unsupported save schema during world upgrade: {relative}')
        updated = rewrite_references(value, mapping)
        if updated == value:
            continue
        target = path
        if path.is_relative_to(worlds) and path.stem in mapping:
            target = path.with_name(mapping[path.stem] + '.json')
            if target.exists():
                raise WorldIdentityMigrationError('target world template already exists')
            deletions.append(_record(root, path, before, None))
            records.append(_record(root, target, None, _encoded(updated)))
        else:
            records.append(_record(root, target, before, _encoded(updated)))
    return {'schema_version': 1, 'id': uuid4().hex, 'mapping': mapping,
            'worlds': worlds.relative_to(root).as_posix(), 'files': records + deletions}


def _validate_plan(root: Path, value: Any, worlds: Path) -> dict:
    if (not isinstance(value, dict) or value.get('schema_version') != 1 or type(value.get('schema_version')) is not int
            or not isinstance(value.get('mapping'), dict) or not value['mapping']
            or not isinstance(value.get('id'), str) or len(value['id']) != 32
            or value.get('worlds') != worlds.relative_to(root).as_posix()
            or not isinstance(value.get('files'), list) or not value['files']):
        raise WorldIdentityMigrationError('unsupported or damaged world identity migration journal')
    for old, new in value['mapping'].items():
        if not isinstance(old, str) or not isinstance(new, str) or migrated_world_id(old) != new or not _valid_id(new):
            raise WorldIdentityMigrationError('invalid world migration mapping')
    paths = set()
    for item in value['files']:
        if not isinstance(item, dict):
            raise WorldIdentityMigrationError('invalid world migration file record')
        path = _path(root, item.get('path'))
        relative = path.relative_to(root)
        if (not (relative.parts[0] in {'templates', 'saves'} or relative.as_posix() == 'character_cards.json')
                or path.suffix != '.json' or path in paths):
            raise WorldIdentityMigrationError('invalid or duplicate migration file path')
        paths.add(path)
        digest = item.get('before_sha256')
        if digest is not None and (not isinstance(digest, str) or len(digest) != 64):
            raise WorldIdentityMigrationError('invalid migration file digest')
        if item.get('after') is not None:
            try:
                json.loads(base64.b64decode(item['after'], validate=True))
            except (ValueError, TypeError) as exc:
                raise WorldIdentityMigrationError('invalid planned world file content') from exc
    return value


def _commit_database(root: Path, plan: dict) -> None:
    database = _path(root, 'lorebook.db')
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('BEGIN IMMEDIATE')
        conn.execute(f'CREATE TABLE IF NOT EXISTS {TABLE} (id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL, mapping_json TEXT NOT NULL)')
        existing = conn.execute(f'SELECT schema_version,mapping_json FROM {TABLE} WHERE id=?', (plan['id'],)).fetchone()
        if existing is not None:
            if existing['schema_version'] != 1 or json.loads(existing['mapping_json']) != plan['mapping']:
                raise WorldIdentityMigrationError('world migration database receipt disagrees with journal')
        else:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables - {TABLE}:
                rebind_lorebook_worlds(conn, plan['mapping'])
            conn.execute(f'INSERT INTO {TABLE}(id,schema_version,mapping_json) VALUES(?,1,?)',
                         (plan['id'], json.dumps(plan['mapping'], sort_keys=True)))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _publish_file(root: Path, record: dict) -> None:
    path = _path(root, record['path'])
    current = path.read_bytes() if path.exists() else None
    after = base64.b64decode(record['after'], validate=True) if record['after'] is not None else None
    if current == after:
        return
    digest = hashlib.sha256(current).hexdigest() if current is not None else None
    if digest != record['before_sha256']:
        raise WorldIdentityMigrationError(f'file changed during interrupted world upgrade: {record["path"]}')
    if after is None:
        path.unlink(missing_ok=True)
    else:
        _atomic(path, after)


def migrate_legacy_world_ids(data_dir: Path, worlds_dir: Path) -> dict[str, str]:
    root, worlds = Path(data_dir).resolve(), Path(worlds_dir).resolve()
    journal = root / 'migrations' / JOURNAL_NAME
    if not worlds.is_dir() and not journal.exists():
        return {}
    root.mkdir(parents=True, exist_ok=True)
    with _exclusive(root):
        journal = _path(root, 'migrations/' + JOURNAL_NAME)
        plan = _validate_plan(root, _read(journal), worlds) if journal.is_file() else _plan(root, worlds)
        if plan is None:
            return {}
        if not journal.exists():
            _atomic(journal, _encoded(plan))
        _commit_database(root, plan)
        for record in plan['files']:
            _publish_file(root, record)
        journal.unlink()
        return dict(plan['mapping'])
