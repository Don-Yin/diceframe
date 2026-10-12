from __future__ import annotations

import os

import pytest

from src.webui import assistant_knowledge


def test_content_doc_paths_include_standalone_webui_guide():
    assert "standalone-webui.md" in assistant_knowledge._CONTENT_DOC_PATHS["zh"]
    assert "standalone-webui.md" in assistant_knowledge._CONTENT_DOC_PATHS["en"]


@pytest.fixture
def knowledge_docs(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    guide = tmp_path / "docs" / "GUIDE_CN.md"
    guide.write_text(
        "# 用户指南\n\n## API 配置\n在设置页面填写模型地址、模型名和 API Key。\n\n"
        "## 插件\n在插件商店安装插件。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(assistant_knowledge, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(assistant_knowledge, "_DOCUMENTS", {
        "zh": ("docs/GUIDE_CN.md",),
        "en": ("docs/GUIDE_CN.md",),
    })
    monkeypatch.setattr(assistant_knowledge, "_CACHE", {})
    monkeypatch.setattr(assistant_knowledge, "_REMOTE_CACHE", {})
    # 测试不联网：远程文档拉取一律返回失败（走内置索引兜底路径）
    async def _no_remote(lang_key):
        return None
    monkeypatch.setattr(assistant_knowledge, "_fetch_remote_docs", _no_remote)
    monkeypatch.setattr(assistant_knowledge, "INDEX_FILE", tmp_path / "nonexistent.json")
    return guide


@pytest.mark.asyncio
async def test_search_returns_relevant_chunk_and_source(knowledge_docs):
    result = await assistant_knowledge.search_knowledge("怎么配置 API", "zh-CN")
    assert "填写模型地址" in result.context
    assert result.sources == [{"source": "docs/GUIDE_CN.md", "heading": "用户指南 > API 配置"}]


@pytest.mark.asyncio
async def test_index_refreshes_after_document_change(knowledge_docs):
    first = await assistant_knowledge.search_knowledge("插件怎么安装", "zh-CN")
    assert "插件商店" in first.context

    knowledge_docs.write_text(
        "# 用户指南\n\n## 插件\n新版说明：从插件页上传 dfplugin。\n",
        encoding="utf-8",
    )
    stat = knowledge_docs.stat()
    os.utime(knowledge_docs, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    second = await assistant_knowledge.search_knowledge("插件怎么安装", "zh-CN")
    assert "新版说明" in second.context
    assert "插件商店" not in second.context


@pytest.mark.asyncio
async def test_unrelated_query_returns_no_context(knowledge_docs):
    result = await assistant_knowledge.search_knowledge("量子物理光谱", "zh-CN")
    assert result.context == ""
    assert result.sources == []


@pytest.mark.asyncio
async def test_remote_docs_replace_builtin_chunks(knowledge_docs, monkeypatch):
    """远程文档按 source 全量替换内置快照：上游更新即时生效，其余文档保留。"""
    async def _remote(lang_key):
        return {"guide.md": "# 用户指南\n\n## 插件\n新版：从插件页上传 dfplugin。\n"}
    monkeypatch.setattr(assistant_knowledge, "_fetch_remote_docs", _remote)

    result = await assistant_knowledge.search_knowledge("插件怎么安装", "zh-CN")
    assert "新版：从插件页上传 dfplugin" in result.context
    assert any(s["source"] == "docs/zh/guide.md" for s in result.sources)

    # 内置文档未被远程覆盖的部分仍然可检索（GUIDE_CN.md 不在远程清单里）
    result_api = await assistant_knowledge.search_knowledge("怎么配置 API", "zh-CN")
    assert "填写模型地址" in result_api.context


@pytest.mark.asyncio
async def test_remote_failure_is_cached_to_avoid_refetch(knowledge_docs, monkeypatch):
    """离线时失败结果按 TTL 缓存，不会每条消息都重撞网络。"""
    calls = []

    async def _remote(lang_key):
        calls.append(lang_key)
        return None
    monkeypatch.setattr(assistant_knowledge, "_fetch_remote_docs", _remote)

    for _ in range(3):
        await assistant_knowledge.search_knowledge("怎么配置 API", "zh-CN")
    assert calls == ["zh"]
