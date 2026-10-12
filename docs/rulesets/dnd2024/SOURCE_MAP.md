# 5E 2024 SRD 内容来源映射

本文件记录 `templates/rulesets/dnd2024_srd` 中角色创建与成长内容的来源边界。可执行内容只取自官方发布的 System Reference Document 5.2.1；快速角色预设及推荐文案为 DiceFrame 原创。

官方入口：https://www.dndbeyond.com/srd

## 版本与许可

- 内容快照：`srd-5.2.1+r5`
- 许可：Creative Commons Attribution 4.0 International（CC BY 4.0）
- 精确归属文本：`templates/rulesets/dnd2024_srd/legal/ATTRIBUTION.md`
- 页码含义：`source_ref` 中的 `pNN` 是 SRD 5.2.1 文档印刷页码。

## 角色创建来源

| 内容 | 数量 | SRD 5.2.1 页码 | 备注 |
| --- | ---: | --- | --- |
| 属性 | 6 | p21 | 属性、标准数组、27 点购点与随机生成 |
| 技能 | 18 | p9 | canonical 技能与对应属性 |
| 标准语言 | 10 | p20 | 包含通用语；角色创建固定选择三种标准语言 |
| 职业 | 12 | p28、31、36、41、47、49、53、57、61、64、70、77 | 一级核心特质、熟练、生命骰、装备和建议属性 |
| 物种 | 9 | p84–86 | Dragonborn、Dwarf、Elf、Gnome、Goliath、Halfling、Human、Orc、Tiefling |
| 背景 | 4 | p83 | Acolyte、Criminal、Sage、Soldier |
| 起源专长 | 6 个可执行实体 | p87 | Alert、Magic Initiate 三个法术列表变体、Savage Attacker、Skilled |
| Magic Initiate 牧师选项 | 7 戏法、15 个 1 环法术 | p38 | 作为专长的受约束选择表保存 |
| Magic Initiate 德鲁伊选项 | 11 戏法、18 个 1 环法术 | p44 | 作为专长的受约束选择表保存 |
| Magic Initiate 法师选项 | 15 戏法、30 个 1 环法术 | p79 | 作为专长的受约束选择表保存 |
| 武器 | 角色创建子集 | p91 | 起始装备闭环所需条目 |
| 护甲 | 角色创建子集 | p92 | AC 派生所需条目 |
| 工具 | 32 | p93–94 | 细分工匠工具、乐器、套装与职业工具选择 |
| 冒险装备 | 角色创建子集 | p95 起 | 起始装备闭环所需条目 |

## 成长、法术与休息来源

| 内容 | 数量 | SRD 5.2.1 页码 | 自动化边界 |
| --- | ---: | --- | --- |
| 职业成长表 | 12 × 20 级 | p28–79 | 特性获得等级、熟练加值、职业轨道和法术位确定性派生 |
| SRD 子职 | 12 | 各职业章节 | 每职业唯一开放子职，选择与获得等级确定性验证，具体能力多为 guided |
| 法术索引 | 339 | p99–319 | 仅机械提取名称键、环位、学派、职业列表、施法时间、距离、成分、仪式、专注、持续时间和来源页；不复制描述正文 |
| 通用专长 | 2 | p87 | 属性提升与 Grappler 前置条件、能力提升确定性验证 |
| 战斗风格 | 4 | p87–88 | 结构化目录；游戏内效果留待战斗状态机 |
| 史诗恩惠 | 7 | p88 | 19 级前置、施法前置和能力提升确定性验证 |
| 短休与长休 | 2 | p185、p188 | HP、生命骰、法术位、专注、力竭和职业资源恢复 |
| 职业特性目录 | 1 套（Monk） | p49–52 | 只记录 feature 的最小 canonical 参数：最低等级、职业资源引用、标量参数、装备前提与 combat capability 声明；获得等级仍以职业成长表为权威，Monk Weapon 定义来自 p90–91 的武器档案（Simple Melee，或带 Light 的 Martial Melee） |

## 战斗来源与原创预设

| 内容 | 数量 | SRD 5.2.1 页码 | 自动化边界 |
| --- | ---: | --- | --- |
| 战斗核心 | 1 套状态机 | p24–27 | 先攻、回合、动作经济、移动、距离、攻击、伤害、治疗、条件、专注、反应和濒死的权威结算 |
| 武器档案 | 15 | p90–92 | 从角色实际装备解析攻击、伤害、距离与类别，不信任客户端数值 |
| 常用法术效果 | 21 | p107–175 | 只对效果目录内法术做确定性命中/豁免、伤害/治疗、升环、条件和专注结算 |
| 训练敌人参考 | 3 | p290、p325、p364 | 只取原创战斗参考与独立冒险所需的 Goblin、Skeleton、Wolf 档案 |

所有来自 SRD 的实体都必须携带非空 `source_ref`。Bundle 加载器会拒绝缺少来源、无法解析的内部引用、未知效果原语和可执行代码字段。

## DiceFrame 原创内容

以下六个快速角色预设仅组合 SRD 选项，其名称、推荐理由和角色定位文案为 DiceFrame 原创，不是 SRD 正文：

- `curious_arcanist`
- `kindly_bulwark`
- `lucky_scout`
- `relentless_vanguard`
- `stalwart_guardian`
- `woodland_guide`

它们使用 `diceframe-original:` 来源命名空间，服务端测试会逐一执行 validate、derive 与 finalize。

Ruleset Bundle 中两个通用战斗参考 `goblin_patrol`、`crypt_pair` 的编排、难度提示和说明为 DiceFrame 原创；其中引用的怪物数值按上表追溯到 SRD。

三章短冒险 `core:lanterns_of_greymoor`（《灰沼失灯记》）及其专属遭遇 `first_skirmish` 位于独立 `templates/adventures/lanterns_of_greymoor/`。场景、NPC、任务、线索、物品、关系、提示、选择与结局全部为 DiceFrame 原创，使用 `diceframe-original:dnd2024-adventures/lanterns-of-greymoor`，不复制任何第三方冒险文本。

## 本地化边界

- canonical JSON 不放展示名称或翻译正文。
- `locales/zh-CN` 的中文说明由 DiceFrame 自行编写和翻译，不复制第三方中文站点。
- `locales/en` 明确覆盖中文拥有的全部展示字段，避免英文界面回退为中文。
- locale overlay 只允许 `name`、`summary`、`description`、`hint`、`recommendation_reason`、`tutorial`、`labels`、`text`，不得修改 mechanics 或 canonical identity。

## 尚未纳入此快照

本快照不复制法术描述正文，也不包含完整怪物图鉴、完整装备图鉴、第三方冒险或全部法术/职业/物种/专长效果自动化。只有已由运行时执行并有测试覆盖的条目标记为 deterministic；其余保持 guided/reference。
