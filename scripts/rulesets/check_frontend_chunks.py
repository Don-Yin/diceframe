"""Fail when optional D&D 2024 UI chunks exceed their reviewed raw-size budgets."""

from __future__ import annotations

import argparse
from pathlib import Path


BUDGETS_KIB = {
    "Dnd2024CharacterBuilder": 40,
    "Dnd2024CampaignPanel": 24,
    "Dnd2024CombatPanel": 24,
}


def check_assets(assets_dir: Path) -> list[tuple[str, float, int]]:
    results: list[tuple[str, float, int]] = []
    errors: list[str] = []
    for prefix, budget_kib in BUDGETS_KIB.items():
        matches = sorted(assets_dir.glob(f"{prefix}-*.js"))
        if len(matches) != 1:
            errors.append(
                f"expected one lazy {prefix} chunk in {assets_dir}, found {len(matches)}"
            )
            continue
        size_kib = matches[0].stat().st_size / 1024
        results.append((prefix, size_kib, budget_kib))
        if size_kib > budget_kib:
            errors.append(
                f"{prefix} is {size_kib:.2f} KiB, above {budget_kib} KiB raw budget"
            )
    if errors:
        raise RuntimeError("\n".join(errors))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "static-v2" / "assets",
    )
    args = parser.parse_args()
    for prefix, size_kib, budget_kib in check_assets(args.assets_dir.resolve()):
        print(f"{prefix}: {size_kib:.2f} KiB / {budget_kib} KiB raw")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
