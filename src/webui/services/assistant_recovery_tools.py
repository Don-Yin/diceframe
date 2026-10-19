"""Bounded, approval-only Agent adapters for content recovery."""
from src.webui.services.assistant_agent import AgentTool
from src.webui.services.assistant_agent_application import obj, string


def recovery_tools(service):
    book = {'book_id': string(200, minimum=1)}
    entries = {**book, 'entry_ids': {'type': 'array', 'minItems': 1, 'maxItems': 10, 'items': string(200, minimum=1)}}
    operation = {'operation_id': string(32, minimum=32)}
    tools = [AgentTool('list_content_operations', 'List your private content undo and recycle-bin records', obj(),
                       lambda args, owner: service.list_operations(owner))]
    for name, kind, properties, handler in (
        ('set_lorebook_enabled', 'set_book_enabled', {**book, 'enabled': {'type': 'boolean'}},
         lambda args, owner: service.set_book_enabled(owner, args['book_id'], args['enabled'])),
        ('set_lorebook_entries_enabled', 'set_entries_enabled', {**entries, 'enabled': {'type': 'boolean'}},
         lambda args, owner: service.set_entries_enabled(owner, args['book_id'], args['entry_ids'], args['enabled'])),
        ('archive_lorebook_entries', 'archive_entries', entries,
         lambda args, owner: service.archive_entries(owner, args['book_id'], args['entry_ids'])),
        ('archive_lorebook', 'archive_book', book,
         lambda args, owner: service.archive_book(owner, args['book_id'])),
    ):
        tools.append(AgentTool(name, {
            'set_book_enabled': 'Enable or disable an authored lorebook across its references',
            'set_entries_enabled': 'Enable or disable up to 10 explicitly selected authored entries',
            'archive_entries': 'Move up to 10 authored entries into a recoverable recycle bin',
            'archive_book': 'Archive an unreferenced authored non-primary book with at most 10 entries',
        }[kind], obj(properties, tuple(properties)), handler, mutation=True,
            guard=lambda args, owner, kind=kind: service.guard(kind, args['book_id'], args.get('entry_ids')),
            preview=lambda args, owner, kind=kind: service.preview(kind, args['book_id'], args.get('entry_ids'))))
    for name, restore in (('undo_content_operation', False), ('restore_content_operation', True)):
        tools.append(AgentTool(name, 'Restore an owner-confirmed content operation without overwriting later edits',
            obj(operation, ('operation_id',)),
            lambda args, owner, restore=restore: (service.restore if restore else service.undo)(owner, args['operation_id']),
            mutation=True,
            guard=lambda args, owner, restore=restore: service.recovery_guard(owner, args['operation_id'], restore=restore),
            preview=lambda args, owner, restore=restore: service.recovery_preview(owner, args['operation_id'], restore=restore)))
    return tuple(tools)
