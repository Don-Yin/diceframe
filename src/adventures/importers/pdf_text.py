"""Text-layer PDF extraction; no OCR, attachments, actions or external fetches."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

from src.adventures.importers.common import NativeDraft


def parse_pdf(payload: bytes, filename: str, runtime: dict, language: str) -> dict:
    try:
        completed = subprocess.run([sys.executable, "-m", "src.adventures.importers.pdf_worker"], input=payload,
            capture_output=True, timeout=8, cwd=Path(__file__).resolve().parents[3],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if completed.returncode or len(completed.stdout) > 2 * 1024 * 1024:
            raise ValueError("PDF text extraction worker failed")
        result = json.loads(completed.stdout)
        if not result.get("ok"):
            raise ValueError(str(result.get("error") or "PDF text extraction failed"))
        pages = result["pages"]
        name = PurePosixPath(filename).stem
        builder = NativeDraft(payload, filename, name, runtime, language, "pdf-text")
        for page in pages:
            if page["text"]:
                builder.scene(f"page:{page['page']}", f"Page {page['page']}", page["text"])
        if not builder.graph["nodes"]:
            raise ValueError("PDF contains no readable text layer; OCR is required for scanned pages")
        builder.draft["warnings"].append("pdfReviewLayout")
        builder.draft["provenance"]["pages"] = len(pages)
        return builder.finish(name)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("PDF text extraction exceeded its time limit") from exc
    except (OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("PDF text extraction failed") from exc
