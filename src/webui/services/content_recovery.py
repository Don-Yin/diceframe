"""Owner-private, transactional recovery of authored lorebook content.

Plans contain metadata, never before-images. Canonical snapshots and journal
rows commit in the same owning store transaction as the content mutation.
"""
from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from src.webui.services.assistant_agent import _digest

_MAX_SNAPSHOT_BYTES = 512 * 1024
_JSON_ENTRY_FIELDS = frozenset({
    'keywords', 'triggers_recursive', 'visible_to', 'connected_to', 'secondary_keys',
    'activation_conditions', 'provenance', 'extensions',
})
_LABELS = {
    'write_entries': '修改资料条目', 'set_book_enabled': '启停资料册',
    'set_entries_enabled': '启停资料条目', 'archive_entries': '资料条目移入回收站',
    'archive_book': '资料册移入回收站',
    'world_fields': '修改世界叙事', 'card_fields': '修改角色叙事',
}


@dataclass(frozen=True)
class ContentRecoveryDependencies:
    store: Any
    list_games: Callable
    get_game: Callable
    world_definition: Callable
    save_entry: Callable


class ContentRecoveryService:
    def __init__(self, deps: ContentRecoveryDependencies, metadata=None):
        self.deps = deps
        self.store = deps.store
        self.metadata = metadata

    @staticmethod
    def _owner(owner: str) -> str:
        if not isinstance(owner, str) or not owner:
            raise PermissionError('Owner identity required')
        return _digest(owner)

    @staticmethod
    def _ids(identities: list[str], maximum=10) -> list[str]:
        if (not isinstance(identities, list) or not 1 <= len(identities) <= maximum
                or any(not isinstance(value, str) or not value.strip() or len(value) > 200 for value in identities)
                or len(set(identities)) != len(identities)):
            raise ValueError('请选择明确且不重复的条目；单次最多 10 条，不支持全量清空')
        return identities

    def _snapshot(self, book_id: str, entry_ids: list[str] | None = None, *, whole=False) -> dict | None:
        snapshot = self.store.snapshot_lorebook(book_id)
        if snapshot is not None and not whole:
            snapshot['entries'] = [row for row in snapshot['entries'] if row['id'] in (entry_ids or [])]
        return snapshot

    def _book(self, book_id: str) -> dict:
        snapshot = self._snapshot(book_id)
        if snapshot is None:
            raise ValueError('资料册不存在或已移入回收站')
        return snapshot

    def _authored(self, snapshot: dict, *, whole=False) -> None:
        book, bindings = snapshot['book'], snapshot['bindings']
        primary = [row for row in bindings if row.get('role') == 'primary']
        if whole and primary:
            raise ValueError('主资料册不能由 Agent 移入回收站')
        kind = str(book.get('source_kind') or '')
        if primary:
            for binding in primary:
                if binding.get('scope_kind') != 'world':
                    raise ValueError('无法证明资料册来源可编辑')
                definition = self.deps.world_definition(binding['scope_id'])
                source = definition.get('world') or {}
                if source.get('source') != 'user' or source.get('editable') is not True:
                    raise ValueError('内置或插件源资料受保护，请先创建用户副本')
        elif kind not in {'native', 'user', 'device'}:
            raise ValueError('内置、插件或未知来源资料受保护，请先创建用户副本')

    def _targets(self, book_id: str, entry_ids: list[str], *, protect=True) -> dict:
        identities = self._ids(entry_ids)
        snapshot = self._snapshot(book_id, identities)
        if snapshot is None or {row['id'] for row in snapshot['entries']} != set(identities):
            raise ValueError('条目不存在于指定资料册，不能猜测或跨册操作')
        if protect:
            self._authored(snapshot)
            if any(row.get('source_plugin') for row in snapshot['entries']):
                raise ValueError('插件源条目受保护，请先创建用户副本')
        return snapshot

    def _affected_games(self, snapshot: dict) -> list[str]:
        bindings = snapshot['bindings']
        affected = {str(row.get('scope_id') or '') for row in bindings if row['scope_kind'] == 'game'}
        for game in self.deps.list_games().get('games', []):
            key = str(game.get('game_key') or '')
            instance = self.deps.get_game(key)
            if instance is None:
                continue
            content = (getattr(instance, 'modules', {}) or {}).get('content_binding', {})
            explicit = isinstance(content, dict) and content.get('book_selection') == 'explicit'
            if any((row['scope_kind'] == 'global' and not explicit)
                   or (row['scope_kind'] == 'world' and not explicit and row['scope_id'] == getattr(instance, 'world_id', ''))
                   or (row['scope_kind'] == 'character' and row['scope_id'] in (getattr(instance, 'players', {}) or {}))
                   for row in bindings):
                affected.add(key)
        return sorted(value for value in affected if value)

    def _unreferenced(self, snapshot: dict) -> None:
        if self._affected_games(snapshot) or any(row['scope_kind'] in {'game', 'character'} for row in snapshot['bindings']):
            raise ValueError('资料册仍被对局或角色引用；请先取消引用，再移入回收站')

    def _no_entry_links(self, entry_ids: list[str]) -> None:
        targets = set(entry_ids)
        for book in self.store.list_lorebooks():
            for entry in self.store.list_book_entries(book['id']):
                links = entry.get('connected_to') or []
                if entry['id'] not in targets and isinstance(links, list) and targets.intersection(links):
                    raise ValueError('条目仍被其它资料条目引用，请先处理引用')

    def preview(self, kind: str, book_id: str, entry_ids: list[str] | None = None) -> dict:
        if kind == 'archive_book':
            snapshot = self._snapshot(book_id, whole=True)
            if snapshot is None: raise ValueError('资料册不存在')
            self._authored(snapshot, whole=True)
            if any(row.get('source_plugin') for row in snapshot['entries']):
                raise ValueError('插件源条目受保护，请先创建用户副本')
            self._unreferenced(snapshot)
            if len(snapshot['entries']) > 10:
                raise ValueError('整册操作最多包含 10 个条目；请先分批整理')
            self._no_entry_links([row['id'] for row in snapshot['entries']])
        elif entry_ids:
            snapshot = self._targets(book_id, entry_ids)
            if kind == 'archive_entries': self._no_entry_links(entry_ids)
        else:
            snapshot = self._book(book_id)
            self._authored(snapshot)
        return {
            'target_name': snapshot['book']['name'], 'book_id': book_id,
            'target_count': len(snapshot['entries']) if entry_ids or kind == 'archive_book' else 1,
            'entries': [{'id': row['id'], 'name': row['name']} for row in snapshot['entries']],
            'binding_count': len(snapshot['bindings']), 'affected_games': self._affected_games(snapshot),
            'recovery_hint': '记录修改前内容；可在内容撤销 / 回收站恢复。后续编辑冲突时不会覆盖。',
        }

    def guard(self, kind: str, book_id: str, entry_ids: list[str] | None = None) -> str:
        preview = self.preview(kind, book_id, entry_ids)
        return _digest({'preview': preview, 'snapshot': self._snapshot(book_id, entry_ids, whole=kind == 'archive_book')})

    @staticmethod
    def _bounded(payload: dict) -> None:
        if len(json.dumps(payload, ensure_ascii=False).encode()) > _MAX_SNAPSHOT_BYTES:
            raise ValueError('恢复快照过大，请拆分为更小的明确操作')

    def _mutate(self, owner: str, kind: str, book_id: str, entry_ids: list[str] | None, action: Callable, *, fields=None, protect=True) -> dict:
        owner_key = self._owner(owner)
        with self.store.transaction():
            if protect:
                summary = self.preview(kind, book_id, entry_ids)
            else:
                current = self._book(book_id)
                summary = {'target_name': current['book']['name'], 'book_id': book_id,
                           'target_count': len(entry_ids or []), 'affected_games': self._affected_games(current)}
            before = self._snapshot(book_id, entry_ids, whole=kind == 'archive_book')
            payload = {'summary': summary, 'book_id': book_id, 'entry_ids': entry_ids or [], 'fields': fields or {}, 'before': before}
            self._bounded(payload)
            operation_id = uuid.uuid4().hex
            self.store.record_lorebook_operation({'id': operation_id, 'owner': owner_key, 'kind': kind, 'status': 'prepared', 'payload': payload})
            result = action()
            payload['after'] = self._snapshot(book_id, entry_ids, whole=kind == 'archive_book')
            self._bounded(payload)
            if not self.store.update_lorebook_operation(operation_id, owner_key, {'status': 'applied', 'payload': payload}):
                raise ValueError('无法保存恢复记录，操作已回滚')
        return {'ok': True, 'operation_id': operation_id, 'reversible': True, **(result or {}),
                'navigation': {'route': 'lorebook', 'query': {'book': book_id}}}

    def write_entries(self, owner: str, book_id: str, rows: list[dict]) -> dict:
        self._ids([row.get('id') for row in rows], maximum=16)
        allowed = {'id', 'name', 'content', 'type', 'keywords', 'visible_to'}
        if any(set(row) - allowed for row in rows): raise ValueError('Unsupported entry write fields')
        fields = {row['id']: [key for key in row if key != 'id'] for row in rows}
        def apply():
            results = []
            for row in rows:
                result = self.deps.save_entry(book_id, deepcopy(row))
                if result.get('ok') is not True: raise ValueError(result.get('error') or 'Entry write rejected')
                results.append({'id': row['id'], 'ok': True})
            return {'results': results}
        return self._mutate(owner, 'write_entries', book_id, [row['id'] for row in rows], apply, fields=fields, protect=False)

    def set_book_enabled(self, owner: str, book_id: str, enabled: bool) -> dict:
        if not isinstance(enabled, bool): raise ValueError('enabled must be boolean')
        return self._mutate(owner, 'set_book_enabled', book_id, None,
            lambda: self.store.update_lorebook(book_id, {'enabled': enabled}) and {}, fields={'book': ['enabled']})

    def set_entries_enabled(self, owner: str, book_id: str, entry_ids: list[str], enabled: bool) -> dict:
        if not isinstance(enabled, bool): raise ValueError('enabled must be boolean')
        def apply():
            for identity in entry_ids:
                if not self.store.update_book_entry(book_id, identity, {'enabled': enabled}): raise ValueError('Entry changed')
        return self._mutate(owner, 'set_entries_enabled', book_id, entry_ids, apply,
                            fields={identity: ['enabled'] for identity in entry_ids})

    def archive_entries(self, owner: str, book_id: str, entry_ids: list[str]) -> dict:
        def apply():
            for identity in entry_ids:
                if not self.store.delete_book_entry(book_id, identity): raise ValueError('Entry changed')
        return self._mutate(owner, 'archive_entries', book_id, entry_ids, apply)

    def archive_book(self, owner: str, book_id: str) -> dict:
        def apply():
            if not self.store.delete_lorebook(book_id): raise ValueError('Book changed')
        return self._mutate(owner, 'archive_book', book_id, None, apply)

    def _operation(self, owner: str, operation_id: str) -> dict:
        if not isinstance(operation_id, str) or not re.fullmatch(r'[a-f0-9]{32}', operation_id):
            raise ValueError('Invalid content operation identity')
        operation = self.store.get_lorebook_operation(operation_id, self._owner(owner))
        if operation is None or operation['status'] != 'applied':
            raise ValueError('恢复记录不存在、属于其它用户或已处理')
        return operation

    def recovery_preview(self, owner: str, operation_id: str, *, restore=False) -> dict:
        operation = self._operation(owner, operation_id)
        if operation['kind'] in {'world_fields', 'card_fields'}:
            if restore or self.metadata is None: raise ValueError('请对叙事修改使用撤销')
            return self.metadata.recovery_preview(owner, operation_id)
        archived = operation['kind'] in {'archive_entries', 'archive_book'}
        if restore != archived: raise ValueError('请选择适合该记录的撤销或恢复操作')
        payload = operation['payload']
        current = self._snapshot(payload['book_id'], payload['entry_ids'], whole=operation['kind'] == 'archive_book')
        if current != payload['after']:
            raise ValueError('内容或引用在该操作之后发生变化；请查看差异，不会覆盖后续编辑')
        if operation['kind'] == 'write_entries':
            existed = {row['id'] for row in payload['before']['entries']}
            self._no_entry_links([identity for identity in payload['entry_ids'] if identity not in existed])
        return {**deepcopy(payload['summary']), 'operation_id': operation_id,
                'recovery_hint': '仅恢复该记录触及的内容；不会回退存档回合或覆盖后续编辑。'}

    def recovery_guard(self, owner: str, operation_id: str, *, restore=False) -> str:
        operation = self._operation(owner, operation_id)
        if operation['kind'] in {'world_fields', 'card_fields'}:
            if restore or self.metadata is None: raise ValueError('请对叙事修改使用撤销')
            return self.metadata.recovery_guard(owner, operation_id)
        preview = self.recovery_preview(owner, operation_id, restore=restore)
        return _digest({'preview': preview, 'operation': self._operation(owner, operation_id)})

    @staticmethod
    def _field_value(row: dict, field: str):
        value = row[field]
        if field in _JSON_ENTRY_FIELDS and isinstance(value, str): value = json.loads(value)
        return value

    def _recover(self, owner: str, operation_id: str, *, restore=False) -> dict:
        with self.store.transaction():
            self.recovery_preview(owner, operation_id, restore=restore)
            operation = self._operation(owner, operation_id)
            payload, kind = operation['payload'], operation['kind']
            before, book_id = payload['before'], payload['book_id']
            if kind == 'archive_book':
                self.store.restore_lorebook_snapshot(before)
            elif kind == 'archive_entries':
                for row in before['entries']: self.store.restore_lorebook_entry(book_id, row)
            elif kind == 'set_book_enabled':
                self.store.update_lorebook(book_id, {'enabled': bool(before['book']['enabled'])})
            elif kind in {'write_entries', 'set_entries_enabled'}:
                previous = {row['id']: row for row in before['entries']}
                for identity in payload['entry_ids']:
                    if identity not in previous:
                        if not self.store.delete_book_entry(book_id, identity): raise ValueError('Entry changed')
                    else:
                        patch = {key: self._field_value(previous[identity], key) for key in payload['fields'][identity]}
                        if not self.store.update_book_entry(book_id, identity, patch): raise ValueError('Entry changed')
            else:
                raise ValueError('Unsupported recovery record')
            payload['recovered_after'] = self._snapshot(book_id, payload['entry_ids'], whole=kind == 'archive_book')
            self._bounded(payload)
            if not self.store.update_lorebook_operation(operation_id, self._owner(owner),
                {'status': 'restored' if restore else 'undone', 'payload': payload}):
                raise ValueError('无法保存恢复结果，操作已回滚')
        return {'ok': True, 'operation_id': operation_id, 'navigation': {'route': 'lorebook', 'query': {'book': book_id}}}

    def undo(self, owner: str, operation_id: str) -> dict:
        if self._operation(owner, operation_id)['kind'] in {'world_fields', 'card_fields'}:
            if self.metadata is None: raise ValueError('叙事恢复不可用')
            return self.metadata.undo(owner, operation_id)
        return self._recover(owner, operation_id)

    def restore(self, owner: str, operation_id: str) -> dict:
        return self._recover(owner, operation_id, restore=True)

    def list_operations(self, owner: str) -> dict:
        operations = []
        for operation in self.store.list_lorebook_operations(self._owner(owner)):
            if operation['kind'] not in _LABELS: continue
            summary = operation['payload'].get('summary') or {}
            archive = operation['kind'] in {'archive_entries', 'archive_book'}
            applied = operation['status'] == 'applied'
            operations.append({'operation_id': operation['id'], 'kind': operation['kind'],
                'label': _LABELS.get(operation['kind'], '内容操作'), 'status': operation['status'],
                'created_at': operation['created_at'], 'target_name': str(summary.get('target_name') or ''),
                'target_count': int(summary.get('target_count') or 0),
                'can_undo': applied and not archive, 'can_restore': applied and archive})
        return {'ok': True, 'operations': operations}
