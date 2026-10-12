from __future__ import annotations

import pytest

from src.webui.routes import games


class _Part:
    name = "file"

    def __init__(self, chunks: list[bytes]):
        self._chunks = iter(chunks)

    async def read_chunk(self) -> bytes:
        return next(self._chunks, b"")


class _Reader:
    def __init__(self, *parts: _Part):
        self._parts = iter(parts)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._parts)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.mark.asyncio
async def test_read_save_upload_enforces_incremental_limit(monkeypatch):
    monkeypatch.setattr(games, "MAX_SAVE_PACKAGE_BYTES", 5)

    with pytest.raises(games._SavePackageTooLarge):
        await games._read_save_upload(_Reader(_Part([b"123", b"456"])))


@pytest.mark.asyncio
async def test_read_save_upload_rejects_multiple_file_parts():
    with pytest.raises(ValueError, match="只能上传一个"):
        await games._read_save_upload(_Reader(_Part([b"a"]), _Part([b"b"])))
