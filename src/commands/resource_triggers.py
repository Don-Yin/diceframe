"""规则资源阈值触发器。

规则模板在 special_stats 里声明 triggers（如 KPI 到 100 触发结局提醒），
资源变化后由本模块检查；命中时向 GM 注入下一轮私密指令并记录健康事件，
不直接改写叙事或结局--结局仍由 GM 依据提示执行。
"""

from __future__ import annotations

import logging
import time
import uuid

from src.engine import progression
from src.engine.character_utils import get_resource
from src.engine.game_instance import GameInstance
from src.rules.rule_system import RuleSystem

logger = logging.getLogger("trpg")


def check_resource_triggers(instance: GameInstance, uid: str, rule: RuleSystem | None) -> list[str]:
    """检查 uid 角色的资源阈值；返回触发的提示文本列表（一次性，跨轮不重复）。"""
    if rule is None:
        return []
    cs = instance.get_character_sheet(uid)
    fired = list(cs.get("_fired_triggers") or [])
    messages: list[str] = []
    for stat in rule.special_stats:
        key = str(stat.get("key") or "")
        for trigger in stat.get("triggers") or []:
            if not isinstance(trigger, dict):
                continue
            try:
                at = int(trigger.get("at"))
            except (TypeError, ValueError):
                continue
            direction = "down" if str(trigger.get("direction") or "up") == "down" else "up"
            token = f"{key}:{at}:{direction}"
            if token in fired:
                continue
            resource = get_resource(cs, key)
            if resource is None:
                continue
            current = int(resource.get("current", 0) or 0)
            hit = current >= at if direction == "up" else current <= at
            if not hit:
                continue
            fired.append(token)
            label = str(stat.get("name") or key)
            notify = str(trigger.get("notify") or "").strip()
            message = f"【系统触发】{label} 到达 {at}" + (f"：{notify}" if notify else "")
            instance.add_gm_directive({
                "id": uuid.uuid4().hex,
                "text": message,
                "created_at": time.time(),
                "target_round": progression.current_round(instance) + 1,
            })
            messages.append(message)
            logger.info("资源触发器命中: %s %s %s", instance.game_key, uid, message)
    if len(fired) != len(cs.get("_fired_triggers") or []):
        cs["_fired_triggers"] = fired
        instance.set_character_sheet(uid, cs)
    return messages
