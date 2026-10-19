"""Explicit, isolated acceptance against the owner's configured model.

Run with DICEFRAME_AGENT_LIVE=1. Only synthetic prompts leave the machine;
all generated content, sessions and confirmations use pytest's temporary data.
"""
import json
import os
import uuid
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from src.ai_providers import is_provider_secret_key, resolve_provider
from src.llm.client import LLMClient, ProviderConfig
from src.runtime_env import load_project_env
from src.webui.runtime_config import RuntimePaths


pytestmark = [pytest.mark.optional, pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("DICEFRAME_AGENT_LIVE") != "1", reason="Live provider acceptance is explicitly opt-in")]


def configured_client():
    root = Path(__file__).resolve().parents[1]
    load_project_env(root / ".env")
    paths = RuntimePaths.from_root(root, os.environ)
    state = json.loads(paths.config_file.read_text(encoding="utf-8"))
    secrets = json.loads(paths.secrets_file.read_text(encoding="utf-8"))
    state.update({key: value for key, value in secrets.items() if is_provider_secret_key(key)})
    resolved = resolve_provider(state, state.get("llm_provider_ref", ""))
    assert resolved and resolved["base_url"] and state.get("model"), "A configured provider reference is required"
    providers = [ProviderConfig("acceptance", resolved["base_url"], resolved["api_key"], state["model"], api_format=resolved["api_format"])]
    for index in (1, 2):
        fallback = resolve_provider(state, state.get(f"fallback{index}_provider_ref", ""))
        if state.get(f"fallback{index}_enabled") and fallback and state.get(f"fallback{index}_model"):
            providers.append(ProviderConfig(f"fallback{index}", fallback["base_url"], fallback["api_key"],
                state[f"fallback{index}_model"], api_format=fallback["api_format"], fallback=True))
    proxy = secrets.get("proxy_url", state.get("proxy_url", "")) if state.get("proxy_enabled") else ""
    return LLMClient(providers, "acceptance", proxy_url=proxy)


@pytest.mark.parametrize("kind,prompt", [
    ("adventure", "随便想一个冒险包"),
    ("lorebook", "请生成一个简短海港小镇世界书草稿，包含三个公开地点条目，每个条目两三句话，不含隐藏信息或秘密。不创建游戏。"),
    ("adventure", "请生成一个简短冒险包草稿：海港旧灯塔失踪案。只包含一个章节、一个场景，使用 #、##、### Markdown 标题，附一行 GM: 隐藏线索。不使用 @npc、@location、@encounter、@choice 引用，不创建游戏。"),
], ids=["casual-adventure", "lorebook", "structured-adventure"])
async def test_live_model_authors_and_saves_real_content_through_framework(tmp_path, kind, prompt):
    from tests.test_module_install_hardening import _make_api
    api, _host, store = _make_api(tmp_path / "data")
    client = configured_client()
    api._llm_client = client
    api._generation_dependencies = replace(api._generation_dependencies, llm_client=client, text_gen_max_tokens=2048)
    agent = api._assistant_agent
    agent.deps = replace(agent.deps, knowledge=None)
    events = []
    async def emit(event, value):
        events.append((event, deepcopy(value)))
    try:
        await agent.run("live-acceptance", [{"role": "user", "content": prompt}], "zh-CN", {}, "", emit)
        sid = next(value["session_id"] for event, value in events if event == "session")
        drafts = [value for event, value in events if event == "draft"]
        assert drafts and drafts[-1]["review"]["kind"] == kind, "The requested content must become a real reviewable draft"
        assert not drafts[-1]["review"].get("blockers"), "Synthetic content must pass the existing content review"
        plan = next((value for event, value in events if event == "approval"), None)
        if plan is None:
            events.clear()
            await agent.run("live-acceptance", [{"role": "user", "content": "请保存刚才已审查的草稿，提出 save_content 保存确认。"}], "zh-CN", {}, sid, emit)
            plan = next((value for event, value in events if event == "approval"), None)
        assert plan and plan["tool"] == "save_content", "Saving must produce a server-held confirmation"
        result = await agent.confirm("live-acceptance", sid, plan["approval_id"], plan["plan_digest"], True)
        assert result["ok"] and result["result"]["ok"], "Confirmed content must be persisted by its real owner"
        again = await agent.confirm("live-acceptance", sid, plan["approval_id"], plan["plan_digest"], True)
        assert again == result, "Live model integration must preserve confirmation idempotence"
        if kind == "lorebook":
            assert api.list_lorebooks(include_all=True)["books"]
        else:
            assert api.list_adventures()["adventures"]
    finally:
        await agent.close()
        await client.close()
        store.close()


async def test_live_chinese_visibility_request_discovers_whole_book_patch(tmp_path):
    """Use synthetic data to check model choice, not just scripted dispatch."""
    from tests.test_module_install_hardening import _make_api
    api, _host, store = _make_api(tmp_path / 'data')
    client = configured_client()
    api._llm_client = client
    agent = api._assistant_agent
    agent.deps = replace(agent.deps, knowledge=None)
    book_id = f'book:{uuid.uuid4().hex}'
    store.create_lorebook({'id': book_id, 'name': '港口调查资料册', 'source_kind': 'user'})
    for index in range(35):
        store.add_book_entry(book_id, {'id': f'clue-{index}', 'name': f'港口线索 {index}',
            'content': f'需要完整保留的调查资料 {index}', 'visible_to': ['*'], 'extensions': {'custom': index}})
    before = store.list_book_entries(book_id)
    events = []

    async def emit(event, value):
        events.append((event, deepcopy(value)))

    try:
        await agent.run('live-acceptance', [{'role': 'user', 'content':
            '请把我所有资料册的全部条目设为仅 GM 可见。只修改可见性，保留原文。列出影响并提出执行确认。'}],
            'zh-CN', {'route': 'overview'}, '', emit)
        plan = next((value for event, value in events if event == 'approval'), None)
        assert plan and plan['tool'] == 'set_lorebook_visibility', 'A Chinese whole-book request must discover the audience-only action'
        assert plan['arguments']['book_id'] == book_id and plan['arguments']['audience'] == 'gm'
        assert plan['preview']['changed_count'] == 35
        assert store.list_book_entries(book_id) == before
        sid = next(value['session_id'] for event, value in events if event == 'session')
        result = await agent.confirm('live-acceptance', sid, plan['approval_id'], plan['plan_digest'], True)
        assert result['result']['changed_count'] == 35
        for original, current in zip(before, store.list_book_entries(book_id)):
            assert current['visible_to'] == []
            assert {key: value for key, value in current.items() if key not in {'visible_to', 'updated_at'}} == {
                key: value for key, value in original.items() if key not in {'visible_to', 'updated_at'}}
    finally:
        await agent.close()
        await client.close()
        store.close()


@pytest.mark.parametrize('audience', ['gm', 'public'])
async def test_live_chinese_task_uses_one_plan_for_twenty_lorebooks(tmp_path, audience):
    from tests.test_module_install_hardening import _make_api
    api, _host, store = _make_api(tmp_path / 'data')
    client = configured_client()
    api._llm_client = client
    agent = api._assistant_agent
    agent.deps = replace(agent.deps, knowledge=None)
    book_ids = []
    for index in range(20):
        book_id = f'book:{uuid.uuid4().hex}'
        book_ids.append(book_id)
        store.create_lorebook({'id': book_id, 'name': f'港口资料册 {index + 1}', 'source_kind': 'user'})
        for entry in range(2):
            store.add_book_entry(book_id, {'id': f'clue-{index}-{entry}', 'name': f'线索 {entry}',
                'content': f'保持不变的调查记录 {index}-{entry}', 'visible_to': ['*'] if audience == 'gm' else [],
                'extensions': {'custom': index}})
    before = {book_id: store.list_book_entries(book_id) for book_id in book_ids}
    grant = agent.authorize('live-acceptance', '', 'task', {}, ['lorebook'], 8)
    events = []
    async def emit(event, value):
        events.append((event, deepcopy(value)))
    prompt = ('把我所有资料册的全部条目改成仅 GM 可见，不修改任何正文。请自动完成并汇报。'
              if audience == 'gm' else '把我所有资料册的全部条目公开给玩家，不修改正文。请整理完整计划，统一让我确认一次后执行。')
    try:
        await agent.run('live-acceptance', [{'role': 'user', 'content': prompt}], 'zh-CN',
                        {'route': 'overview'}, grant['session_id'], emit)
        approvals = [value for event, value in events if event == 'approval']
        if audience == 'public':
            assert len(approvals) == 1 and approvals[0]['tool'] == 'set_lorebooks_visibility'
            assert approvals[0]['preview']['book_count'] == 20
            assert {book_id: store.list_book_entries(book_id) for book_id in book_ids} == before
            plan = approvals[0]
            response = await agent.confirm('live-acceptance', grant['session_id'], plan['approval_id'], plan['plan_digest'], True)
            assert response['result']['success_count'] == 20
        else:
            assert not approvals, 'A covering Task grant must allow GM-only narrowing without book approvals'
        snapshot = agent.snapshot('live-acceptance', grant['session_id'])
        batch_receipts = [receipt for receipt in snapshot['receipts']
                          if isinstance(receipt.get('result'), dict) and receipt['result'].get('success_count') == 20]
        assert len(batch_receipts) == 1, 'The planner must use one grouped command for all twenty books'
        for book_id in book_ids:
            for original, current in zip(before[book_id], store.list_book_entries(book_id)):
                assert current['visible_to'] == ([] if audience == 'gm' else ['*'])
                assert {key: value for key, value in current.items() if key not in {'visible_to', 'updated_at'}} == {
                    key: value for key, value in original.items() if key not in {'visible_to', 'updated_at'}}
    finally:
        await agent.close()
        await client.close()
        store.close()
