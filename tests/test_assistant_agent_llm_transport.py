"""Exercise DF Agent through the real LLMClient and local provider HTTP replies."""
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from src.llm.client import LLMClient, ProviderConfig
from src.webui.services.assistant_agent import AgentDependencies, AgentRuntime, AgentTool


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["openai", "anthropic", "json-fallback"])
async def test_real_client_tool_response_reaches_agent_read_loop_and_confirmation(tmp_path, mode):
    provider_requests = []
    step_index = [0]
    steps = [
        {"tool": "read", "arguments": {}},
        {"tool": "write", "arguments": {"value": "reviewed"}},
        {"tool": "respond", "arguments": {}, "answer": "DF Agent is ready."},
    ]

    async def provider(request):
        body = await request.json()
        provider_requests.append(body)
        if mode == "json-fallback" and "tools" in body:
            return web.json_response({"error": "native tools unavailable"}, status=400)
        step = steps[step_index[0]]
        step_index[0] += 1
        if step["tool"] == "respond":
            call_name = "final_result"
            call_arguments = {"answer": step["answer"]}
        else:
            call_name = step["tool"]
            call_arguments = step["arguments"]
        if mode == "anthropic":
            return web.json_response({"content": [{"type": "tool_use", "id": "step",
                "name": call_name, "input": call_arguments}], "usage": {"input_tokens": 1, "output_tokens": 1}})
        if mode == "json-fallback":
            message = {"content": json.dumps({"tool_calls": [{"name": call_name, "arguments": call_arguments}]})}
        else:
            message = {"content": None, "tool_calls": [{"id": "step", "type": "function", "function": {
                "name": call_name, "arguments": json.dumps(call_arguments)}}]}
        return web.json_response({"choices": [{"message": message, "finish_reason": "stop"}], "usage": {"total_tokens": 2}})

    app = web.Application()
    app.router.add_post("/{path:.*}", provider)
    server = TestServer(app)
    await server.start_server()
    client = LLMClient([ProviderConfig("test", str(server.make_url("/")), "test-key", "test-model",
        api_format="anthropic" if mode == "anthropic" else "openai")], "test")
    writes = []
    async def read(args, owner):
        return {"ok": True, "resource": "available"}
    async def write(args, owner):
        writes.append((args, owner))
        return {"ok": True}
    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    schema = {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": False}
    agent = AgentRuntime(AgentDependencies(llm_client=lambda: client, configuration_error=lambda lang: None,
        tools=(AgentTool("read", "Read", empty, read), AgentTool("write", "Write", schema, write, mutation=True)),
        storage_dir=tmp_path / "agent"))
    events = []
    async def emit(event, payload):
        events.append((event, deepcopy(payload)))
    try:
        await agent.run("owner", [{"role": "user", "content": "Read and write"}], "en", {}, "", emit)
        sid = next(value["session_id"] for event, value in events if event == "session")
        plan = next(value for event, value in events if event == "approval")
        assert not writes
        assert any(event == "tool_result" and value["result"]["resource"] == "available" for event, value in events)
        assert step_index[0] == 2
        assert (await agent.confirm("owner", sid, plan["approval_id"], plan["plan_digest"], True))["ok"]
        assert writes == [({"value": "reviewed"}, "owner")]
        events.clear()
        await agent.run("owner", [{"role": "user", "content": "Hello"}], "en", {}, sid, emit)
        assert ("delta", {"delta": "DF Agent is ready."}) in events
        assert step_index[0] == 3 and len(writes) == 1
        if mode == "anthropic":
            assert all(body.get("tool_choice") == {"type": "auto"} for body in provider_requests if "tools" in body)
        else:
            assert all(body.get("tool_choice") == "auto" for body in provider_requests if "tools" in body)
        if mode == "json-fallback":
            assert any(body.get("response_format") == {"type": "json_object"} for body in provider_requests)
    finally:
        await client.close()
        await server.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("calls", [[], [None], [{"name": "other", "arguments": {}}],
    [{"name": "final_result", "arguments": {}}, {"name": "final_result", "arguments": {}}]])
async def test_malformed_client_response_is_rejected_without_executing(tmp_path, calls):
    class Planner:
        async def call_tools(self, *args, **kwargs):
            return SimpleNamespace(tool_calls=calls)
    agent = AgentRuntime(AgentDependencies(llm_client=Planner, configuration_error=lambda lang: None,
        tools=(), storage_dir=tmp_path / "agent"))
    async def emit(*args):
        pass
    with pytest.raises(Exception):
        await agent.run("owner", [{"role": "user", "content": "hi"}], "en", {}, "", emit)


@pytest.mark.asyncio
async def test_invalid_native_arguments_are_retried_before_approval(tmp_path):
    provider_requests = []
    attempt = [0]

    async def provider(request):
        body = await request.json()
        provider_requests.append(body)
        attempt[0] += 1
        arguments = {"value": True} if attempt[0] == 1 else {"value": "corrected"}
        return web.json_response({"choices": [{"message": {"content": None, "tool_calls": [{
            "id": f"write-{attempt[0]}", "type": "function", "function": {
                "name": "write", "arguments": json.dumps(arguments),
            },
        }]}, "finish_reason": "tool_calls"}], "usage": {"total_tokens": 2}})

    app = web.Application()
    app.router.add_post("/{path:.*}", provider)
    server = TestServer(app)
    await server.start_server()
    client = LLMClient([ProviderConfig("test", str(server.make_url("/")), "test-key", "test-model")], "test")
    writes = []

    async def write(args, owner):
        writes.append((args, owner))
        return {"ok": True}

    schema = {"type": "object", "properties": {"value": {"type": "string"}},
              "required": ["value"], "additionalProperties": False}
    agent = AgentRuntime(AgentDependencies(
        llm_client=lambda: client,
        configuration_error=lambda lang: None,
        tools=(AgentTool("write", "Write", schema, write, mutation=True),),
        storage_dir=tmp_path / "agent",
    ))
    events = []

    async def emit(event, payload):
        events.append((event, deepcopy(payload)))

    try:
        await agent.run("owner", [{"role": "user", "content": "Write it"}], "en", {}, "", emit)
        sid = next(value["session_id"] for event, value in events if event == "session")
        approval = next(value for event, value in events if event == "approval")
        assert writes == []
        assert len(provider_requests) == 2
        second_history = json.dumps(provider_requests[1], ensure_ascii=False).lower()
        assert "retry" in second_history or "expected string" in second_history
        result = await agent.confirm("owner", sid, approval["approval_id"], approval["plan_digest"], True)
        assert result["ok"]
        assert writes == [({"value": "corrected"}, "owner")]
    finally:
        await client.close()
        await server.close()


@pytest.mark.asyncio
async def test_multiple_native_calls_never_execute_business_handlers(tmp_path):
    provider_requests = []

    async def provider(request):
        body = await request.json()
        provider_requests.append(body)
        return web.json_response({"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "read-1", "type": "function", "function": {"name": "read", "arguments": "{}"}},
            {"id": "write-1", "type": "function", "function": {
                "name": "write", "arguments": json.dumps({"value": "must-not-run"}),
            }},
        ]}, "finish_reason": "tool_calls"}], "usage": {"total_tokens": 2}})

    app = web.Application()
    app.router.add_post("/{path:.*}", provider)
    server = TestServer(app)
    await server.start_server()
    client = LLMClient([ProviderConfig("test", str(server.make_url("/")), "test-key", "test-model")], "test")
    calls = []

    async def read(args, owner):
        calls.append(("read", args, owner))
        return {"ok": True}

    async def write(args, owner):
        calls.append(("write", args, owner))
        return {"ok": True}

    schema = {"type": "object", "properties": {"value": {"type": "string"}},
              "required": ["value"], "additionalProperties": False}
    agent = AgentRuntime(AgentDependencies(
        llm_client=lambda: client,
        configuration_error=lambda lang: None,
        tools=(
            AgentTool("read", "Read", {"type": "object", "properties": {}, "additionalProperties": False}, read),
            AgentTool("write", "Write", schema, write, mutation=True),
        ),
        storage_dir=tmp_path / "agent",
    ))

    async def emit(event, payload):
        pass

    try:
        with pytest.raises(Exception):
            await agent.run("owner", [{"role": "user", "content": "Read and write"}], "en", {}, "", emit)
        assert calls == []
        assert provider_requests
    finally:
        await client.close()
        await server.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["openai", "anthropic", "json-fallback"])
async def test_real_client_batched_read_tools_run_sequentially_and_reach_draft(tmp_path, mode):
    requests = []
    dispatched = []

    async def provider(request):
        body = await request.json()
        if mode == "json-fallback" and "tools" in body:
            return web.json_response({"error": "native tools unavailable"}, status=400)
        requests.append(body)
        calls = ([{"name": "read", "arguments": {"catalog": name}} for name in ("worlds", "adventures")]
                 if len(requests) == 1 else [{"name": "draft", "arguments": {}}]
                 if len(requests) == 2 else [{"name": "final_result", "arguments": {"answer": "Draft ready."}}])
        if mode == "anthropic":
            return web.json_response({"content": [{"type": "tool_use", "id": str(index), "name": call["name"], "input": call["arguments"]}
                for index, call in enumerate(calls)], "usage": {"input_tokens": 1, "output_tokens": 1}})
        if mode == "json-fallback":
            message = {"content": json.dumps({"tool_calls": calls})}
        else:
            message = {"tool_calls": [{"id": str(index), "type": "function", "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])}}
                for index, call in enumerate(calls)]}
        return web.json_response({"choices": [{"message": message, "finish_reason": "stop"}], "usage": {"total_tokens": 2}})

    app = web.Application()
    app.router.add_post("/{path:.*}", provider)
    server = TestServer(app)
    await server.start_server()
    client = LLMClient([ProviderConfig("test", str(server.make_url("/")), "test-key", "test-model",
        api_format="anthropic" if mode == "anthropic" else "openai")], "test")

    async def read(args, owner):
        dispatched.append(args["catalog"])
        return {"ok": True, "catalog": args["catalog"]}

    async def draft(args, owner):
        assert dispatched == ["worlds", "adventures"]
        return {"ok": True, "kind": "adventure", "draft": {"items": []}, "blockers": [], "plan_digest": "sha256:test"}

    agent = AgentRuntime(AgentDependencies(lambda: client, lambda lang: None, (
        AgentTool("read", "Read", {"type": "object", "properties": {"catalog": {"type": "string"}}, "required": ["catalog"], "additionalProperties": False}, read),
        AgentTool("draft", "Draft", {"type": "object", "properties": {}, "additionalProperties": False}, draft, creates_draft=True),
    ), tmp_path / "agent"))
    events = []

    async def emit(event, value):
        events.append((event, deepcopy(value)))

    try:
        await agent.run("owner", [{"role": "user", "content": "随便想一个冒险包"}], "zh-CN", {}, "", emit)
        assert len(requests) == 3 and dispatched == ["worlds", "adventures"]
        assert any(event == "draft" for event, _ in events)
        assert not any(event == "approval" for event, _ in events)
        history = json.loads(next(message["content"] for message in requests[1]["messages"] if message["role"] == "user"))["agent_history"]
        returns = [part for message in history for part in message["parts"] if part["part_kind"] == "tool-return"]
        assert [part["tool_name"] for part in returns] == ["read", "read"]
        assert all(part["part_kind"] != "retry-prompt" for message in history for part in message["parts"])
    finally:
        await client.close()
        await server.close()
