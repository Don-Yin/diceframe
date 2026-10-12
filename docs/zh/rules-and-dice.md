# 规则与骰子

DiceFrame 把“玩家掷出了什么”与“这次行动是否成功”分开处理。随机层只生成骰值；规则层决定骰制、修正值、目标值、优势/劣势和成功等级；GM 只负责判断行动是否真的需要检定，以及选择合适的属性、技能和难度。

这条边界让 D&D、CoC、赛博朋克、武侠和内容包自定义玩法可以共用同一套稳定骰子，而不必把每个世界的房规写进随机数代码。

## 内置规则的判定方式

| 规则 | 判定方式 | 大成功/大失败 | 优势与协助 |
|---|---|---|---|
| D&D 5e 轻量规则 | `d20 + 修正值 >= DC` | 普通属性/技能检定不因自然 20 自动成功，也不因自然 1 自动失败 | 优势/劣势掷 2d20 取高/取低；有效协助给予优势 |
| 自由 d20（奇幻、赛博朋克、武侠） | `d20 + 修正值 >= DC` | 默认自然 20 大成功、自然 1 大失败 | 优势/劣势掷 2d20 取高/取低；有效协助给予优势 |
| CoC 7e 调查恐怖轻量规则 | d100 不高于技能/属性阈值 | 1 大成功；大失败按 CoC 7e 阈值；支持普通、困难、极难成功 | 奖励骰从最终候选值中取低，惩罚骰取高；`00 + 0` 正确视为 100 |
| 自由叙事 | 不自动检定 | 无 | 无 |

内置 D&D 和 CoC 是适合自然语言跑团的轻量辅助规则，不承诺完整复刻商业规则书。攻击、法术和职业能力仍可由具体规则或房规进一步约束。

## 什么时候应该掷骰

只有同时满足以下条件时才应检定：行动结果不确定，而且失败会带来有意义的代价。普通交谈、纯角色扮演、无阻碍移动、已经完成的事实，以及同一动作的重复描述不应被强行检定。

DiceFrame 会为每名角色、每个回合记录检定，避免同一行动在计划、解析和叙事阶段被重复掷骰。难度也受规则的 `max_check_dc` 限制，不会因为团跑得久就自动越来越高。

## 内容包如何声明检定能力

内容包应显式写出自己支持的能力，不要只在 `mechanics` 文案里描述。下面是带电影化自然 20/1 的 d20 示例：

```json
{
  "dice_system": "d20",
  "max_check_dc": 20,
  "check_mechanic": {
    "dice": "d20",
    "comparison": "roll_plus_modifier_gte_target",
    "critical": {"success": 20, "failure": 1},
    "advantage": {
      "type": "d20_keep_high_low",
      "allow_explicit": true,
      "assistance_grants": "advantage"
    }
  }
}
```

如果要采用 D&D 普通属性/技能检定语义，可将 `critical.success` 和 `critical.failure` 设为 `null`。不支持优势/劣势的规则应省略 `advantage`，系统不会擅自套用其他规则的能力。

世界模板只用 `default_rule` 选择规则；世界书负责设定和上下文，不应复制判定算法。规则可通过 `extends` 继承基础模板，再覆盖自己需要改变的字段。

## 内容包如何声明战斗扩展（行动条 / 动作伤害公式）

默认战斗仍是“一轮一次、先手固定”。如果规则需要**行动速度攒到阈值才出手**（ATB 行动条），或需要**法术/技艺自带伤害公式**，用规则的 `combat` 块显式声明；没有 `combat` 块时引擎不会猜测启用，玩法保持原样。

```json
{
  "attributes": [{"key": "wu_xing", "name": "悟性"}, {"key": "shen_fa", "name": "身法"}],
  "special_stats": [{"key": "ling_li", "name": "灵力", "max": 100, "initial": 100}],
  "combat": {
    "scheduler": {
      "kind": "threshold", "gauge": "action_gauge", "speed": "action_speed",
      "threshold": 100, "overflow": "carry", "consume": "reset",
      "speed_formula": {"op": "multiply", "args": [
        {"op": "attribute", "id": "shen_fa"}, {"op": "constant", "value": 4}]}
    },
    "resources": [
      {"id": "hp", "source": "hp"},
      {"id": "ling_li", "source": "special_stat", "stat": "ling_li"}
    ],
    "actions": [
      {"id": "spell:fireball", "kind": "ability", "name": "火球术",
       "costs": [{"resource": "ling_li", "amount": {"op": "constant", "value": 10}}],
       "effects": [{"kind": "damage", "damage_type": "fire", "amount": {
         "op": "multiply", "args": [
           {"op": "attribute", "id": "wu_xing"}, {"op": "constant", "value": 3}]}}]},
      {"id": "technique:escape_light", "kind": "ability", "name": "遁术·轻身",
       "costs": [{"resource": "ling_li", "amount": {"op": "constant", "value": 5}}],
       "effects": [{"kind": "modify_stat", "resource": "action_speed",
                    "duration": 2, "amount": {"op": "constant", "value": 40}}]}
    ]
  }
}
```

- `scheduler.kind` 支持 `threshold`（ATB 行动条）、`initiative`、`round_robin`；`threshold` 下每个实体按 `speed_formula` 求值累积 `gauge`，攒满 `threshold` 才轮到他，`overflow` 决定溢出取 `carry` 还是 `clamp`，`consume` 决定出手后 `reset` 还是 `carry`。GM 通过“推进时间”让行动条前进。
- `speed_formula` 只读角色属性与常数（不允许骰子）：行动速度因此可以真的由身法/敏捷这类属性派生，而不是写死的数字。
- `resources` 声明可结算的资源池：`hp`（生命）、`special_stat`（角色卡的灵力/内力等字段）、`combat_state`（战斗会话内的护盾等，配合 `"damage_priority": "before_hp"` 可先扣盾再扣血）。未声明的字段不会自动变成可消耗资源。
- `actions` 是动作目录：`kind` 只有通用类别 `attack` / `ability` / `consumable`；具体是法术、遁术还是丹药由规则自己命名 canonical `action_id`（例如 `spell:fireball`、`technique:escape_light`）。`costs` 是资源消耗，`effects` 支持 `damage`、`resource_change`、`modify_stat`（状态修正，带 `duration`，可用来提升 `action_speed` 实现“遁术加速”），`consume_item` 可从背包扣物品。
- 数值与消耗都是受限公式 AST：白名单节点 `constant` / `attribute` / `resource` / `dice` / `add` / `subtract` / `multiply` / `min` / `max` / `negate`（本适配层不支持 `derived_stat` / `equipment_stat`），未知引用直接拒绝，不会 `eval`，也不会回退成猜测值。
- 客户端只提交 `action_id` + 目标；伤害、速度、资源与行动条数值全部由服务端结算，客户端提交的数值一律忽略。

## 旧存档兼容

现有存档不需要转换。只要对应的 `rule_id` 仍然存在，角色、世界书和剧情日志会原样保留，并继续使用当前版本的骰子与判定实现。

外部内容包若新增了显式优势/劣势声明，需要更新并重新启用内容包；这不会重写旧存档正文或角色卡。更新前仍建议备份 `data/`。

## 发布前自检

审计内置规则、已安装插件和额外内容包源码：

```powershell
python scripts\audit_rules.py --strict --path ..\content-packs
```

模拟 6 人、25 回合，并独立复算每次 d20/d100 判定：

```powershell
python scripts\audit_dice_campaigns.py --rounds 25 --players 6 --distribution-samples 20000 --rule-path ..\content-packs --output .codex_tmp\dice-audit.json
```

更高强度的发布前统计可把 `--rounds` 提高到 10000，把 `--distribution-samples` 提高到 200000。随机分布测试只能发现明显偏差；规则矩阵、长团复算和真实 API 交互测试仍应一起保留。
