from src.migrations.instance import CURRENT_INSTANCE_SCHEMA_VERSION, migrate_game_state_payload


def _manual_roll_requests(payload):
    # Shape-aware: the list moves from the top level into modules["checks"].
    checks = payload.get("modules", {}).get("checks")
    if isinstance(checks, dict) and "manual_roll_requests" in checks:
        return checks["manual_roll_requests"]
    return payload["manual_roll_requests"]


def test_schema10_manual_rolls_default_to_record_only_purpose():
    payload = migrate_game_state_payload({
        "instance_schema_version": 10,
        "manual_roll_requests": [{"id": "mr-1", "results": {}}],
    })
    # 顺序迁移：v10 经过 v11（purpose 默认值）继续走到当前版本（Currency V2 步骤）。
    assert payload["instance_schema_version"] == CURRENT_INSTANCE_SCHEMA_VERSION
    assert _manual_roll_requests(payload)[0]["purpose"] == "free"
