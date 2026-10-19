"""Explicit foreign format selection at the common native draft boundary."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Callable

from src.adventures.importers.fantasy_grounds import parse_fantasy_grounds
from src.adventures.importers.foundry import parse_foundry
from src.adventures.importers.pdf_text import parse_pdf
from src.adventures.script_import import MAX_SCRIPT_BYTES, parse_script

MAX_EXTERNAL_BYTES = 5 * 1024 * 1024
ADAPTERS: dict[str, Callable] = {".md": parse_script, ".txt": parse_script, ".json": parse_foundry,
                                ".xml": parse_fantasy_grounds, ".mod": parse_fantasy_grounds, ".pdf": parse_pdf}


def source_limit(filename: str) -> int:
    return MAX_SCRIPT_BYTES if PurePosixPath(filename.lower()).suffix in {".md", ".txt"} else MAX_EXTERNAL_BYTES


def parse_import(payload: bytes, filename: str, runtime: dict, language: str) -> dict:
    filename = PurePosixPath(filename.replace("\\", "/")).name
    extension = PurePosixPath(filename).suffix.lower()
    parser = ADAPTERS.get(extension)
    if parser is None:
        raise ValueError("supported imports: Markdown/TXT, Foundry Adventure JSON, Fantasy Grounds XML/.mod, text-layer PDF")
    if not payload or len(payload) > source_limit(filename):
        raise ValueError("import source is empty or too large")
    return parser(payload, filename, runtime, language)
