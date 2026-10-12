"""谜题交互处理器。

从 game_handler 拆出的 active puzzle 检测、自动检定和状态文本生成逻辑。
"""

from __future__ import annotations

import logging

from src.engine.constants import PUZZLE_KEYWORDS
from src.engine.dice import roll as dice_roll
from src.engine.game_instance import GameInstance
from src.engine.language import localized_text
from src.engine.puzzle import PuzzleType

logger = logging.getLogger("trpg")


class PuzzleProcessor:
    """处理谜题交互：检测解谜行动，执行技能检定，返回谜题状态文本。"""

    def process_puzzles(self, instance: GameInstance, actions_text: str) -> str:
        if not instance.puzzle_manager:
            return ""

        active_puzzles = instance.puzzle_manager.get_active_puzzles()
        if not active_puzzles:
            return ""

        has_puzzle_intent = any(kw in actions_text for kw in PUZZLE_KEYWORDS)
        if not has_puzzle_intent:
            return ""

        language = instance.language
        puzzle_lines: list[str] = [localized_text(language, {"en": "[Current Puzzle]", "zh-CN": "【当前谜题】", "ja": "【現在の謎】", "de": "[Aktuelles Rätsel]"})]
        for puzzle in active_puzzles:
            skill = puzzle.required_skill or (puzzle.allowed_skills[0] if puzzle.allowed_skills else None)
            status = localized_text(language, {
                "en": f"Status: active (attempts {puzzle.attempts}/{puzzle.max_attempts})",
                "zh-CN": f"状态: active (已尝试{puzzle.attempts}/{puzzle.max_attempts})",
                "ja": f"状態: active (試行{puzzle.attempts}/{puzzle.max_attempts})",
                "de": f"Status: aktiv (Versuche {puzzle.attempts}/{puzzle.max_attempts})",
            })
            puzzle_lines.append(localized_text(language, {
                "en": f"Name: {puzzle.name}",
                "zh-CN": f"名称: {puzzle.name}",
                "ja": f"名前: {puzzle.name}",
                "de": f"Name: {puzzle.name}",
            }))
            puzzle_lines.append(status)
            if skill:
                puzzle_lines.append(localized_text(language, {
                    "en": f"Required skill: {skill} DC {puzzle.required_dc}",
                    "zh-CN": f"所需技能: {skill} DC {puzzle.required_dc}",
                    "ja": f"必要技能: {skill} DC {puzzle.required_dc}",
                    "de": f"Benötigte Fertigkeit: {skill} SG {puzzle.required_dc}",
                }))
            if puzzle.hint_given:
                puzzle_lines.append(localized_text(language, {
                    "en": f"Hint: {puzzle.description}",
                    "zh-CN": f"提示: {puzzle.description}",
                    "ja": f"ヒント: {puzzle.description}",
                    "de": f"Hinweis: {puzzle.description}",
                }))

            # 技能检定型谜题：自动掷骰
            if skill and puzzle.puzzle_type != PuzzleType.RIDDLE:
                d20_result = dice_roll("d20")
                # P1: actor 从 action_queue 取（user_id 明确），优先有结构化字段的；
                # 不再遍历 players 按角色名猜，也不 fallback 到第一个玩家
                action = next(
                    (a for a in instance.action_queue
                     if a.get("selected_attribute") or a.get("selected_skill")),
                    instance.action_queue[0] if instance.action_queue else None,
                )
                attr_mod = 0
                if action:
                    uid = action.get("user_id", "")
                    cs = instance.get_character_sheet(uid)
                    if cs:
                        mods = cs.get("_modifiers", {})
                        selected_attribute = action.get("selected_attribute", "")
                        attr_mod = mods.get(selected_attribute, 0) if selected_attribute else mods.get(skill, 0)
                total = d20_result.total + attr_mod
                success = total >= puzzle.required_dc

                if success:
                    puzzle.solve()
                    puzzle_lines.append(localized_text(language, {
                        "en": f"Check: d20={d20_result.natural}+{attr_mod}={total} >= DC {puzzle.required_dc} -> Success!",
                        "zh-CN": f"检定: d20={d20_result.natural}+{attr_mod}={total} ≥ DC {puzzle.required_dc} → 成功！",
                        "ja": f"判定: d20={d20_result.natural}+{attr_mod}={total} ≥ DC {puzzle.required_dc} → 成功！",
                        "de": f"Probe: d20={d20_result.natural}+{attr_mod}={total} >= SG {puzzle.required_dc} -> Erfolg!",
                    }))
                    if puzzle.success_narration:
                        puzzle_lines.append(localized_text(language, {
                            "en": f"Result: {puzzle.success_narration}",
                            "zh-CN": f"结果: {puzzle.success_narration}",
                            "ja": f"結果: {puzzle.success_narration}",
                            "de": f"Ergebnis: {puzzle.success_narration}",
                        }))
                else:
                    can_continue = puzzle.attempt()
                    puzzle_lines.append(localized_text(language, {
                        "en": f"Check: d20={d20_result.natural}+{attr_mod}={total} < DC {puzzle.required_dc} -> Failure",
                        "zh-CN": f"检定: d20={d20_result.natural}+{attr_mod}={total} < DC {puzzle.required_dc} → 失败",
                        "ja": f"判定: d20={d20_result.natural}+{attr_mod}={total} < DC {puzzle.required_dc} → 失敗",
                        "de": f"Probe: d20={d20_result.natural}+{attr_mod}={total} < SG {puzzle.required_dc} -> Fehlschlag",
                    }))
                    if not can_continue:
                        puzzle_lines.append(localized_text(language, {
                            "en": "Result: maximum attempts exceeded; the puzzle fails.",
                            "zh-CN": "结果: 超过最大尝试次数，谜题失败！",
                            "ja": "結果: 最大試行回数を超えました。謎は失敗します！",
                            "de": "Ergebnis: maximale Versuchszahl überschritten; das Rätsel ist gescheitert.",
                        }))
                        if puzzle.failure_narration:
                            puzzle_lines.append(puzzle.failure_narration)

        puzzle_lines.append(localized_text(language, {
            "en": "Requirement: GM narration must reflect the puzzle check result and state change.",
            "zh-CN": "要求: GM叙事必须体现谜题的检定结果和状态变化",
            "ja": "要件: GMのナレーションは謎の判定結果と状態変化を反映すること",
            "de": "Anforderung: Die GM-Erzählung muss das Rätsel-Probenergebnis und die Statusänderung widerspiegeln",
        }))

        logger.info(
            "谜题处理: active=%d, attempts=%s",
            len(active_puzzles),
            ", ".join(f"{p.name}({p.attempts}/{p.max_attempts})" for p in active_puzzles),
        )
        return "\n".join(puzzle_lines)
