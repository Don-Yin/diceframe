"""Measure which capability modules the core game flow cannot run without (#515).

For each module under ``src/engine/modules`` this runs the core-flow test set
with the module's capability API replaced by stubs that raise, and reports how
many tests fail beyond the unmodified baseline run, plus the core code that hit
a stub first.  The module's lifecycle hooks are detached as well, so the run
matches a build without the module.  Storage contracts (``fresh``/``ensure``/codec helpers) are kept,
so the numbers measure "capability gone", not "save slot gone".

This is a report, not a gate: the counts move whenever core-flow tests are
added.  ``tests/architecture/test_module_pluggability.py`` is the CI guard.

Usage::

    python scripts/audit_module_pluggability.py                 # every module
    python scripts/audit_module_pluggability.py media health    # some modules
    python scripts/audit_module_pluggability.py --jobs 4 --json out.json
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import pkgutil
import subprocess
import sys
import tempfile
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODULES_DIR = ROOT / "src" / "engine" / "modules"

CORE_FLOW_TESTS = (
    "tests/test_golden_e2e_54pr.py",
    "tests/test_check_and_gm_command_flow.py",
    "tests/test_action_run_pipeline.py",
    "tests/test_game_lifecycle_transactions.py",
    "tests/test_webui_create_flow.py",
    "tests/integration/",
    "tests/test_world_runtime_integration.py",
    "tests/test_run_lifecycle_economy.py",
)
# test_in_flight_* wait on an event without a timeout and hang instead of
# failing when the round errors before reaching the fake LLM.
DESELECT = "not in_flight"

# Storage and codec contracts every module keeps; stubbing them measures a
# missing save slot rather than a missing capability.
KEEP_FUNCS = frozenset({
    "fresh", "ensure", "require_writable", "persisted_state",
    "ensure_economy_state", "fresh_economy_state", "normalize_timers",
    "health_events", "normalize_decoded_play_mode", "payload_container",
})

ENV_MODULE = "DICEFRAME_AUDIT_DISABLE_MODULE"
ENV_HITS = "DICEFRAME_AUDIT_HITS_FILE"
RUN_TIMEOUT_SECONDS = 900


class ModuleDisabled(RuntimeError):
    pass


class DisableModulePlugin:
    """pytest plugin: stub every public function of one module and its aliases."""

    def __init__(self, module: str, hits_file: str) -> None:
        self.module = module
        self.hits_file = hits_file

    def _caller(self) -> str:
        own = f"/engine/modules/{self.module}.py"
        for frame in reversed(traceback.extract_stack()[:-2]):
            path = frame.filename.replace("\\", "/")
            if "/src/" in path and not path.endswith(own):
                return f"{path.split('/src/', 1)[1]}::{frame.name}"
        return "<tests>"

    def _stub(self, name: str) -> Any:
        def stub(*_args: Any, **_kwargs: Any) -> Any:
            caller = self._caller()
            with open(self.hits_file, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "func": name, "caller": caller,
                    "test": os.environ.get("PYTEST_CURRENT_TEST", "").rsplit(" ", 1)[0],
                }) + "\n")
            raise ModuleDisabled(f"{self.module}.{name} disabled (called from {caller})")
        return stub

    def pytest_configure(self, config: Any) -> None:
        import src

        for info in pkgutil.walk_packages(src.__path__, "src."):
            try:
                importlib.import_module(info.name)
            except Exception:  # noqa: BLE001 - optional deps; unimportable code cannot alias
                pass
        target = importlib.import_module(f"src.engine.modules.{self.module}")
        # A deleted module also never attaches to lifecycle hooks; the
        # registry holds the original functions, which stubbing cannot reach.
        from src.engine import module_hooks

        module_hooks.unregister_owner(getattr(target, "MODULE_NAME", self.module))
        originals = {
            name: obj for name, obj in vars(target).items()
            if callable(obj) and not isinstance(obj, type) and not name.startswith("_")
            and name not in KEEP_FUNCS and getattr(obj, "__module__", None) == target.__name__
        }
        stubs = {id(obj): self._stub(name) for name, obj in originals.items()}
        for name, obj in originals.items():
            setattr(target, name, stubs[id(obj)])
        for loaded_name, loaded in list(sys.modules.items()):
            if not loaded_name.startswith("src.") or loaded is target:
                continue
            for name, obj in list(vars(loaded).items()):
                if id(obj) in stubs and any(obj is original for original in originals.values()):
                    setattr(loaded, name, stubs[id(obj)])


class FailureCollector:
    def __init__(self) -> None:
        self.failed: set[str] = set()
        self.total = 0

    def pytest_runtest_logreport(self, report: Any) -> None:
        if report.when == "call":
            self.total += 1
        if report.failed:
            self.failed.add(report.nodeid)


def _worker(module: str, hits_file: str, result_file: str) -> int:
    sys.path.insert(0, str(ROOT))
    import pytest

    collector = FailureCollector()
    plugins: list[Any] = [collector]
    if module:
        plugins.append(DisableModulePlugin(module, hits_file))
    args = ["-q", "-p", "no:cacheprovider", "-k", DESELECT, *CORE_FLOW_TESTS]
    code = pytest.main(args, plugins=plugins)
    Path(result_file).write_text(
        json.dumps({"failed": sorted(collector.failed), "total": collector.total}), encoding="utf-8",
    )
    return 0 if code in (0, 1) else int(code)


def _run(module: str, workdir: Path) -> dict[str, Any]:
    tag = module or "_baseline"
    hits, result = workdir / f"{tag}.hits.jsonl", workdir / f"{tag}.json"
    hits.touch()
    command = [sys.executable, __file__, "--worker", module, str(hits), str(result)]
    try:
        completed = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"module": tag, "error": f"timed out after {RUN_TIMEOUT_SECONDS}s"}
    if not result.is_file():
        return {"module": tag, "error": completed.stderr[-2000:] or completed.stdout[-2000:]}
    data = json.loads(result.read_text(encoding="utf-8"))
    first_hit: dict[str, str] = {}
    for line in hits.read_text(encoding="utf-8").splitlines():
        hit = json.loads(line)
        first_hit.setdefault(hit["test"], hit["caller"])
    return {"module": tag, **data, "first_hit": first_hit}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("modules", nargs="*", help="modules to measure (default: all)")
    parser.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 2) // 2)))
    parser.add_argument("--json", type=Path, help="also write the full report here")
    parser.add_argument("--worker", nargs=3, metavar=("MODULE", "HITS", "RESULT"), help=argparse.SUPPRESS)
    options = parser.parse_args(argv)
    if options.worker:
        return _worker(*options.worker)

    available = sorted(p.stem for p in MODULES_DIR.glob("*.py") if p.stem != "__init__")
    unknown = sorted(set(options.modules) - set(available))
    if unknown:
        parser.error(f"unknown modules: {unknown}")
    modules = options.modules or available

    with tempfile.TemporaryDirectory(prefix="pluggability-") as tmp:
        with ThreadPoolExecutor(max_workers=options.jobs) as pool:
            runs = list(pool.map(lambda name: _run(name, Path(tmp)), ["", *modules]))
    baseline, results = runs[0], runs[1:]
    if "error" in baseline:
        print(f"baseline run failed: {baseline['error']}", file=sys.stderr)
        return 2
    known = set(baseline["failed"])
    print(f"core-flow tests: {baseline['total']}, failing without any stub: {len(known)}\n")
    print(f"{'module':<26}{'new failures':>14}  top first-hit callers")
    report = []
    for result in sorted(results, key=lambda r: len(r.get("failed", [])) - len(known)):
        if "error" in result:
            print(f"{result['module']:<26}{'error':>14}  {result['error'].splitlines()[-1]}")
            report.append(result)
            continue
        new = sorted(set(result["failed"]) - known)
        callers = Counter(result["first_hit"].get(test, "<no stub hit>") for test in new)
        top = ", ".join(f"{caller} ({count})" for caller, count in callers.most_common(3))
        print(f"{result['module']:<26}{len(new):>14}  {top}")
        report.append({"module": result["module"], "new_failures": new, "callers": dict(callers)})
    if options.json:
        options.json.write_text(json.dumps({
            "total": baseline["total"], "baseline_failures": sorted(known), "modules": report,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
