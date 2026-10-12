from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _python_files(*roots: Path):
    for root in roots:
        if root.exists():
            yield from root.rglob("*.py")


def test_generic_commands_and_engine_do_not_import_concrete_rulesets() -> None:
    concrete_packages = {
        f"src.rulesets.{path.parent.name}"
        for path in (SRC / "rulesets").glob("*/runtime.py")
    }
    violations: list[str] = []
    for path in _python_files(SRC / "commands", SRC / "engine"):
        for module in _imports(path):
            if any(
                module == package or module.startswith(f"{package}.")
                for package in concrete_packages
            ):
                violations.append(f"{path.relative_to(ROOT)} -> {module}")

    assert violations == [], "generic layer imports concrete rulesets:\n" + "\n".join(violations)


def test_core_compat_and_migrations_do_not_import_webui() -> None:
    violations: list[str] = []
    for path in _python_files(
        SRC / "commands", SRC / "engine", SRC / "compat", SRC / "migrations",
    ):
        for module in _imports(path):
            if module == "src.webui" or module.startswith("src.webui."):
                violations.append(f"{path.relative_to(ROOT)} -> {module}")

    assert violations == [], "inner layer imports WebUI:\n" + "\n".join(violations)


def test_game_routes_use_public_api_for_instance_lookup_and_persistence() -> None:
    path = SRC / "webui" / "routes" / "games.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    private_facade_access = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in {"_reg", "_handler", "_parse_key", "_save_path"}
    ]
    direct_lookup_access = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and any("_parse_key" in ast.unparse(argument) for argument in node.args)
    ]

    assert private_facade_access == [], f"games route accesses private WebAPI state at {private_facade_access}"
    assert direct_lookup_access == [], f"games route parses keys inside registry.get at {direct_lookup_access}"


def test_games_route_remains_a_composition_facade() -> None:
    path = SRC / "webui" / "routes" / "games.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    local_functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    domain_modules = {
        "game_query_routes.py",
        "game_control_routes.py",
        "game_gameplay_routes.py",
        "game_character_routes.py",
        "game_package_routes.py",
        "game_lifecycle_routes.py",
    }

    assert len(local_functions) <= 4, (
        f"games route should remain a small composition facade, found {local_functions}"
    )
    assert domain_modules <= {
        item.name for item in path.parent.glob("game_*_routes.py")
    }


def test_migrated_game_services_do_not_receive_the_webapi_locator() -> None:
    service_names = {
        "game_packages.py",
        "game_controls.py",
        "game_master.py",
        "game_media.py",
        "game_lifecycle.py",
        "game_lifecycle_context.py",
        "game_creation_phases.py",
        "game_seed_lifecycle.py",
        "generated_images.py",
        "avatars.py",
        "map_backgrounds.py",
        "scene_images.py",
        "memory.py",
        "bot_access.py",
        "logs.py",
        "asr.py",
        "knowledge.py",
        "kp_questions.py",
        "system.py",
        "bot_extensions.py",
        "announcements.py",
        "content.py",
        "legal.py",
        "hub.py",
        "speech.py",
        "tavern.py",
    }
    violations: list[str] = []
    services = SRC / "webui" / "services"
    for path in sorted(services.glob("*.py")):
        if path.name not in service_names:
            continue
        tree = ast.parse(
            path.read_text(encoding="utf-8-sig"), filename=str(path),
        )
        for module in _imports(path):
            if module == "src.webui.api" or module.startswith("src.webui.api."):
                violations.append(f"{path.name} imports {module}")
        for function in (
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            if any(argument.arg == "api" for argument in function.args.args):
                violations.append(f"{path.name}:{function.name} receives api")

    assert violations == [], "migrated services regained WebAPI coupling:\n" + "\n".join(violations)


def test_all_routes_have_no_unreviewed_private_facade_access() -> None:
    """Reject route access to any non-dunder private member."""

    found: set[tuple[str, str, str, int]] = set()
    routes = SRC / "webui" / "routes"
    for path in sorted(routes.rglob("*.py")):
        tree = ast.parse(
            path.read_text(encoding="utf-8-sig"), filename=str(path),
        )
        for function in (
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Attribute)
                    and node.attr.startswith("_")
                    and not node.attr.startswith("__")
                ):
                    found.add((path.name, function.name, node.attr, node.lineno))
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "getattr"
                    and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)
                    and node.args[1].value.startswith("_")
                    and not node.args[1].value.startswith("__")
                ):
                    found.add((
                        path.name,
                        function.name,
                        node.args[1].value,
                        node.lineno,
                    ))

    assert found == set(), (
        "routes contain unreviewed private facade access:\n"
        + "\n".join(map(str, sorted(found)))
    )
