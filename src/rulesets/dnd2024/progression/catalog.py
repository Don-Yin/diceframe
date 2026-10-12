"""Validated, presentation-neutral access to the SRD class feature tables."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from src.rulesets.bundle import LoadedRulesetBundle
class ProgressionCatalogError(ValueError):
    """Raised when bundled progression data cannot safely drive the runtime."""


def _class_id(class_ref: str) -> str:
    prefix = "class:"
    value = str(class_ref or "")
    return value[len(prefix):] if value.startswith(prefix) else ""


def _twenty_rows(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list) or len(value) != 20:
        raise ProgressionCatalogError(f"{field} must contain exactly 20 levels")
    return value


def _proficiency_bonus(level: int) -> int:
    return 2 + (level - 1) // 4


@dataclass(frozen=True, slots=True)
class Dnd2024ProgressionCatalog:
    """Read-only class progression data after structural validation."""

    content_version: str
    source_ref: str
    slot_profiles: dict[str, list[list[int]]]
    classes: dict[str, dict[str, Any]]
    subclasses: dict[str, dict[str, Any]]

    @classmethod
    def from_bundle(cls, bundle: LoadedRulesetBundle) -> Dnd2024ProgressionCatalog:
        raw = bundle.get("progression_catalog", "srd_classes")
        if raw is None:
            raise ProgressionCatalogError("D&D 2024 progression catalog is missing")
        if int(raw.get("max_level", 0) or 0) != 20:
            raise ProgressionCatalogError("progression max_level must be 20")

        raw_profiles = raw.get("slot_profiles")
        if not isinstance(raw_profiles, dict):
            raise ProgressionCatalogError("slot_profiles must be an object")
        slot_profiles: dict[str, list[list[int]]] = {}
        expected_widths = {"full": 9, "half": 5}
        for profile_id, width in expected_widths.items():
            rows = _twenty_rows(raw_profiles.get(profile_id), f"slot_profiles.{profile_id}")
            parsed_rows: list[list[int]] = []
            for level, row in enumerate(rows, start=1):
                if not isinstance(row, list) or len(row) != width:
                    raise ProgressionCatalogError(
                        f"slot_profiles.{profile_id}[{level}] must contain {width} slots"
                    )
                if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in row):
                    raise ProgressionCatalogError(
                        f"slot_profiles.{profile_id}[{level}] contains an invalid slot count"
                    )
                parsed_rows.append(list(row))
            slot_profiles[profile_id] = parsed_rows

        raw_classes = raw.get("classes")
        if not isinstance(raw_classes, dict):
            raise ProgressionCatalogError("progression classes must be an object")
        bundle_class_ids = {str(item["id"]) for item in bundle.list("class")}
        if set(raw_classes) != bundle_class_ids:
            missing = sorted(bundle_class_ids.difference(raw_classes))
            extra = sorted(set(raw_classes).difference(bundle_class_ids))
            raise ProgressionCatalogError(
                f"progression class coverage mismatch: missing={missing}, extra={extra}"
            )

        classes: dict[str, dict[str, Any]] = {}
        for class_id, raw_class in raw_classes.items():
            if not isinstance(raw_class, dict):
                raise ProgressionCatalogError(f"classes.{class_id} must be an object")
            source_ref = str(raw_class.get("source_ref") or "").strip()
            if not source_ref:
                raise ProgressionCatalogError(f"classes.{class_id}.source_ref is required")
            features = _twenty_rows(
                raw_class.get("features_by_level"), f"classes.{class_id}.features_by_level"
            )
            if any(
                not isinstance(row, list)
                or any(not isinstance(feature, str) or not feature for feature in row)
                for row in features
            ):
                raise ProgressionCatalogError(
                    f"classes.{class_id}.features_by_level contains an invalid feature id"
                )
            tracks = raw_class.get("tracks")
            if not isinstance(tracks, dict):
                raise ProgressionCatalogError(f"classes.{class_id}.tracks must be an object")
            for track_id, values in tracks.items():
                _twenty_rows(values, f"classes.{class_id}.tracks.{track_id}")
                if any(
                    isinstance(value, bool) or not isinstance(value, int) or value < 0
                    for value in values
                ):
                    raise ProgressionCatalogError(
                        f"classes.{class_id}.tracks.{track_id} contains an invalid value"
                    )
            slot_profile = str(raw_class.get("slot_profile") or "")
            if slot_profile and slot_profile not in {*slot_profiles, "pact"}:
                raise ProgressionCatalogError(
                    f"classes.{class_id}.slot_profile is unsupported: {slot_profile}"
                )
            classes[class_id] = deepcopy(raw_class)

        raw_subclasses = bundle.get("subclass_catalog", "srd_subclasses")
        if raw_subclasses is None or not isinstance(raw_subclasses.get("subclasses"), dict):
            raise ProgressionCatalogError("D&D 2024 subclass catalog is missing")
        subclasses = raw_subclasses["subclasses"]
        if set(subclasses) != bundle_class_ids:
            raise ProgressionCatalogError("subclass catalog must cover every SRD class exactly once")
        parsed_subclasses: dict[str, dict[str, Any]] = {}
        for class_id, subclass in subclasses.items():
            if not isinstance(subclass, dict):
                raise ProgressionCatalogError(f"subclasses.{class_id} must be an object")
            if subclass.get("class_ref") != f"class:{class_id}":
                raise ProgressionCatalogError(f"subclasses.{class_id}.class_ref is invalid")
            if not str(subclass.get("id") or "") or not str(subclass.get("source_ref") or ""):
                raise ProgressionCatalogError(f"subclasses.{class_id} identity is incomplete")
            by_level = subclass.get("feature_ids_by_level")
            if not isinstance(by_level, dict) or not by_level:
                raise ProgressionCatalogError(
                    f"subclasses.{class_id}.feature_ids_by_level must be an object"
                )
            for raw_level, feature_ids in by_level.items():
                try:
                    feature_level = int(raw_level)
                except (TypeError, ValueError) as exc:
                    raise ProgressionCatalogError(
                        f"subclasses.{class_id} contains an invalid feature level"
                    ) from exc
                if not 1 <= feature_level <= 20 or not isinstance(feature_ids, list):
                    raise ProgressionCatalogError(
                        f"subclasses.{class_id} contains an invalid feature level"
                    )
                if any(not isinstance(item, str) or not item for item in feature_ids):
                    raise ProgressionCatalogError(
                        f"subclasses.{class_id} contains an invalid feature id"
                    )
            parsed_subclasses[class_id] = deepcopy(subclass)

        return cls(
            content_version=bundle.manifest.content_version,
            source_ref=str(raw["source_ref"]),
            slot_profiles=slot_profiles,
            classes=classes,
            subclasses=parsed_subclasses,
        )

    def snapshot(self, class_ref: str, level: int) -> dict[str, Any]:
        """Return the exact table row and current caps for one single-class level."""

        class_id = _class_id(class_ref)
        progression = self.classes.get(class_id)
        if progression is None:
            raise ProgressionCatalogError(f"unknown class progression: {class_ref}")
        if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 20:
            raise ProgressionCatalogError("class level must be an integer from 1 to 20")
        index = level - 1
        tracks = {
            track_id: values[index]
            for track_id, values in progression["tracks"].items()
        }
        previous_tracks = {
            track_id: (values[index - 1] if index else 0)
            for track_id, values in progression["tracks"].items()
        }
        track_deltas = {
            track_id: value - previous_tracks[track_id]
            for track_id, value in tracks.items()
            if value != previous_tracks[track_id]
        }

        spell_slots: dict[str, int] = {}
        slot_profile = str(progression.get("slot_profile") or "")
        if slot_profile in self.slot_profiles:
            spell_slots = {
                str(spell_level): count
                for spell_level, count in enumerate(
                    self.slot_profiles[slot_profile][index], start=1
                )
                if count
            }
        elif slot_profile == "pact":
            pact_level = int(tracks["pact_slot_level"])
            pact_slots = int(tracks["pact_slots"])
            spell_slots = {str(pact_level): pact_slots} if pact_slots else {}

        return {
            "class_ref": f"class:{class_id}",
            "level": level,
            "proficiency_bonus": _proficiency_bonus(level),
            "gained_feature_ids": list(progression["features_by_level"][index]),
            "tracks": tracks,
            "track_deltas": track_deltas,
            "slot_profile": slot_profile,
            "spell_slots": spell_slots,
            "source_ref": str(progression["source_ref"]),
            "content_version": self.content_version,
        }

    def subclass_choice(self, class_ref: str) -> dict[str, Any]:
        class_id = _class_id(class_ref)
        subclass = self.subclasses.get(class_id)
        if subclass is None:
            raise ProgressionCatalogError(f"unknown class progression: {class_ref}")
        return deepcopy(subclass)

    def range(self, class_ref: str, start_level: int = 1, end_level: int = 20) -> list[dict[str, Any]]:
        if start_level > end_level:
            raise ProgressionCatalogError("start_level must not exceed end_level")
        return [self.snapshot(class_ref, level) for level in range(start_level, end_level + 1)]
