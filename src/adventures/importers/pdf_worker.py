"""Disposable, time-bounded PDF text extraction process."""
from __future__ import annotations

import io
import json
import sys

from pypdf import PdfReader


def extract(payload: bytes) -> list[dict]:
    reader = PdfReader(io.BytesIO(payload), strict=True)
    if reader.is_encrypted:
        raise ValueError("encrypted PDFs are not supported")
    if not 1 <= len(reader.pages) <= 128:
        raise ValueError("PDF must contain 1–128 pages")
    rows, total = [], 0
    for index, page in enumerate(reader.pages):
        content = page.get_contents()
        if content and len(content.get_data()) > 2 * 1024 * 1024:
            raise ValueError("PDF page content stream is too large")
        text = page.extract_text() or ""
        total += len(text.encode("utf-8"))
        if total > 512 * 1024:
            raise ValueError("PDF extracted text exceeds 512 KiB")
        rows.append({"page": index + 1, "text": text.strip()})
    return rows


if __name__ == "__main__":
    try:
        payload = sys.stdin.buffer.read(5 * 1024 * 1024 + 1)
        if not payload or len(payload) > 5 * 1024 * 1024:
            raise ValueError("PDF source is empty or too large")
        result = {"ok": True, "pages": extract(payload)}
    except Exception as exc:
        result = {"ok": False, "error": str(exc)[:300]}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
