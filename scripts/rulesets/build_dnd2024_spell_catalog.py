"""Build the DiceFrame D&D 2024 spell index from the official SRD 5.2.1 PDF.

The generated catalog contains compact mechanics metadata only; it deliberately
does not copy spell description prose. Run this maintenance tool explicitly
with a locally obtained official PDF. The PDF is not a runtime dependency.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader


PAGE_MARKER_RE = re.compile(r"^System Reference Document 5\.2\.1$")
LEVEL_RE = re.compile(r"^Level ([1-9]) ([A-Za-z]+) \(([^)]+)\)$")
CANTRIP_RE = re.compile(r"^([A-Za-z]+) Cantrip \(([^)]+)\)$")
NON_ID_RE = re.compile(r"[^a-z0-9]+")
CLASS_IDS = {
    "Bard": "bard",
    "Cleric": "cleric",
    "Druid": "druid",
    "Paladin": "paladin",
    "Ranger": "ranger",
    "Sorcerer": "sorcerer",
    "Warlock": "warlock",
    "Wizard": "wizard",
}
# Five entries are split across PDF columns in extraction order, so their
# metadata labels are not contiguous even though the printed rows are clear.
# Keep this compact correction table sourced from those printed rows rather
# than copying any spell description prose.
METADATA_OVERRIDES: dict[str, dict[str, Any]] = {
    "vicious_mockery": {
        "range": "60 feet", "components": ["V"], "duration": "Instantaneous",
    },
    "arcanist_s_magic_aura": {
        "range": "Touch", "components": ["V", "S", "M"], "duration": "24 hours",
    },
    "magic_weapon": {
        "range": "Touch", "components": ["V", "S"], "duration": "1 hour",
    },
    "water_walk": {
        "range": "30 feet", "components": ["V", "S", "M"], "duration": "1 hour",
    },
    "hold_monster": {
        "range": "90 feet", "components": ["V", "S", "M"],
        "duration": "Concentration, up to 1 minute",
    },
}


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace(" -\n", "")).strip()


def _title(value: str) -> str:
    # PDF small-caps extraction produces strings such as ``Acid SplASh``.
    return _compact(value).lower().title().replace("’S", "’s").replace("'S", "'s")


def _spell_id(name: str) -> str:
    ascii_name = name.replace("’", "'").lower()
    return NON_ID_RE.sub("_", ascii_name).strip("_")


def _metadata(lines: list[str], casting_index: int) -> tuple[int, re.Match[str]] | None:
    for width in range(1, 4):
        start = casting_index - width
        if start < 1:
            continue
        candidate = _compact(" ".join(lines[start:casting_index]))
        match = LEVEL_RE.fullmatch(candidate) or CANTRIP_RE.fullmatch(candidate)
        if match:
            return start, match
    return None


def _field(lines: list[str], start: int, label: str) -> str:
    # The official PDF occasionally flattens the four metadata rows onto one
    # extracted line and alternates between ``Component`` and ``Components``.
    # Parse the compact metadata block by labels rather than by visual lines.
    window = _compact(" ".join(lines[start:min(start + 10, len(lines))]))
    labels = {
        "Casting Time": (r"Casting Time", r"Range"),
        "Range": (r"Range", r"Components?"),
        "Components": (r"Components?", r"Duration"),
    }
    if label in labels:
        current, following = labels[label]
        match = re.search(
            rf"(?:^|\s){current}:\s*(.+?)(?=\s+{following}:)", window,
        )
        return match.group(1).strip() if match else ""
    duration = re.search(
        r"(?:^|\s)Duration:\s*("
        r"(?:Concentration,?\s*)?(?:up to\s+)?\d+\s+"
        r"(?:rounds?|minutes?|hours?|days?)|"
        r"Instantaneous|Until dispelled(?: or triggered)?|Special"
        r")\b",
        window,
        re.IGNORECASE,
    )
    return duration.group(1).strip() if duration else ""


def extract(pdf_path: Path) -> list[dict[str, Any]]:
    reader = PdfReader(pdf_path)
    spells: dict[str, dict[str, Any]] = {}
    # Printed pages 107–175 contain the spell descriptions. The PDF has no
    # front-matter offset in this release, so zero-based indexes are 106–174.
    for page_number in range(107, 176):
        lines = [line.strip() for line in (reader.pages[page_number - 1].extract_text() or "").splitlines()]
        for index, line in enumerate(lines):
            if not _compact(line).startswith("Casting Time:"):
                continue
            metadata = _metadata(lines, index)
            if metadata is None:
                continue
            metadata_start, match = metadata
            title_index = metadata_start - 1
            while title_index >= 0 and (
                not lines[title_index]
                or PAGE_MARKER_RE.fullmatch(lines[title_index])
                or lines[title_index].isdigit()
            ):
                title_index -= 1
            if title_index < 0:
                continue
            name = _title(lines[title_index])
            spell_id = _spell_id(name)
            is_cantrip = match.re is CANTRIP_RE
            level = 0 if is_cantrip else int(match.group(1))
            school = (match.group(1) if is_cantrip else match.group(2)).lower()
            raw_classes = match.group(2) if is_cantrip else match.group(3)
            class_ids = [
                CLASS_IDS[item.strip()]
                for item in raw_classes.split(",")
                if item.strip() in CLASS_IDS
            ]
            casting_time = _field(lines, index, "Casting Time")
            spell_range = _field(lines, index, "Range")
            components = _field(lines, index, "Components")
            duration = _field(lines, index, "Duration")
            entity = {
                "id": spell_id,
                "name": name,
                "level": level,
                "school": school,
                "class_refs": [f"class:{class_id}" for class_id in class_ids],
                "casting_time": casting_time,
                "range": spell_range,
                "components": [
                    component for component in ("V", "S", "M")
                    if re.search(rf"(?:^|, )?{component}(?:,| |$)", components)
                ],
                "ritual": "Ritual" in casting_time,
                "concentration": duration.startswith("Concentration"),
                "duration": duration,
                "source_ref": f"srd-5.2.1:p{page_number}:{spell_id}",
            }
            entity.update(METADATA_OVERRIDES.get(spell_id, {}))
            entity["concentration"] = str(entity["duration"]).startswith("Concentration")
            existing = spells.get(spell_id)
            if existing is not None and existing != entity:
                raise ValueError(f"conflicting duplicate spell id: {spell_id}")
            spells[spell_id] = entity
    return sorted(spells.values(), key=lambda item: (item["level"], item["id"]))


def build_catalog(spells: list[dict[str, Any]]) -> dict[str, Any]:
    mechanics = [
        {key: value for key, value in spell.items() if key != "name"}
        for spell in spells
    ]
    return {
        "schema_version": 1,
        "kind": "spell_catalog",
        "id": "srd_spells",
        "source_ref": "srd-5.2.1:p107-p175:spell-descriptions",
        "automation_level": "reference",
        "spells": mechanics,
    }


def build_english_locale(spells: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "locale_schema_version": 1,
        "locale": "en",
        "target": {"kind": "spell_catalog", "id": "srd_spells"},
        "fields": {
            "name": "SRD 5.2.1 Spells",
            "labels": {spell["id"]: spell["name"] for spell in spells},
        },
    }


def build_zh_locale(spells: list[dict[str, Any]]) -> dict[str, Any]:
    # Official English names are an intentional, deterministic fallback until
    # a DiceFrame-authored Chinese label is reviewed; mechanics never depend on it.
    return {
        "locale_schema_version": 1,
        "locale": "zh-CN",
        "target": {"kind": "spell_catalog", "id": "srd_spells"},
        "fields": {
            "name": "SRD 5.2.1 法术",
            "labels": {spell["id"]: spell["name"] for spell in spells},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("english_locale_output", type=Path)
    parser.add_argument("zh_locale_output", type=Path)
    args = parser.parse_args()
    spells = extract(args.pdf)
    if len(spells) < 300:
        raise SystemExit(f"refusing to write incomplete spell catalog: only {len(spells)} spells")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_catalog(spells), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.english_locale_output.parent.mkdir(parents=True, exist_ok=True)
    args.english_locale_output.write_text(
        json.dumps(build_english_locale(spells), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.zh_locale_output.parent.mkdir(parents=True, exist_ok=True)
    args.zh_locale_output.write_text(
        json.dumps(build_zh_locale(spells), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {len(spells)} spells to {args.output}, {args.english_locale_output}, "
        f"and {args.zh_locale_output}"
    )


if __name__ == "__main__":
    main()
