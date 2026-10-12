# DiceFrame v2.6.1

> 正式版本：世界书检索全面升级为通用的 Hybrid Lore Retrieval（场景锚点 + 关键词 + 可选向量语义），世界书在提示词中的呈现补上权威边界与可靠性标注；创建向导的角色控制方式改为与「编辑」并排的一键循环按钮。

## 中文

### 新增内容

- **通用 Hybrid Lore Retrieval（所有规则集共用）**：正常回合、重掷（swipe）与桌外问答（问 GM / KP）现在都走同一套检索层，检索输入从「只有本轮玩家文本」扩展为：本轮行动 + 当前场景 + 当前地点（WorldState 中的 canonical location）+ 真实在场的 NPC。因此「玩家只说『我看看桌子』，但场景是世界书里定义过的地点」这类情况，相关设定也能进入上下文。
- **可选的向量语义检索**：沿用它现有的向量配置（开关、服务商、模型、输入上限），不新增任何配置字段。启用后，除了关键词命中，还会用语义相似度补充召回；未启用、服务商不可用、调用失败或返回异常向量时，都会自动退回「锚点 + 关键词」并继续正常回合，**不会因为向量问题中断游戏**。
- **条目向量缓存**：世界书条目的向量按「条目 + 语言 + 模型/端点」缓存并随内容变化自动重建，因此不会每回合重新计算整个世界书；缓存是纯派生数据，删掉也会自动重建。
- **世界书提示词投影升级**：模型现在能看到每条设定的 `type` / `tier`，以及标记为 `unreliable`（传闻、NPC 认知或主观说法）的条目；同时明确写入一致性规则——权威世界状态、系统裁定与规则运行时高于世界书，世界书只约束它明确声明的事实，未声明部分可以合理即兴，世界书不是剧情脚本，玩家的后续行动造成的改变以当前世界状态为准。
- **玩家侧问答不暴露内部条目 ID**：桌外问答引用世界书时仍保留 `type` / `tier` / `unreliable` 与正文，但不再把内部条目标识交给玩家侧模型（避免 `npc_traitor_mary` 这类 ID 本身泄露幕后信息）。GM 侧不受影响。
- **创建向导：控制方式一键循环**：创建冒险的「角色」步骤里，每张角色卡的控制方式从下拉框改为与「编辑 / 删除」并排的按钮，点一下在「玩家 → AI 托管 → 等待认领」之间循环；确认页不再重复列出每张角色的控制方式。

### 修复内容

- **世界书检索顺序**：关键词命中与语义命中合并后，统一按 `tier → order → 来源 → 相似度 → ID` 排序，避免低优先级的旧条目先占用上下文预算、把高优先级设定挤掉。
- **异常向量的容错**：缓存或向量服务返回非数字、`NaN`、`Inf` 等坏数据时，只跳过对应的语义召回，不再可能影响正常回合。
- **结构标签不再误触发关键词**：检索文本里用于向量语义提示的结构标签不会参与关键词匹配，避免英文世界书中关键词恰好是 `scene` / `location` / `action` 时每回合固定误命中。
- **设置页文案**：四语言的「向量记忆」统一改为「向量检索 / Vector · Semantic Retrieval」，并说明它同时服务于长期记忆与世界书的语义检索、未配置时会继续使用关键词与场景检索。
- 德语设置说明的冠词修正（`Aktiviere hier die Steuerung …`）。

### 升级说明

- 本版只有一处**新增**数据库表（世界书向量缓存），随启动自动建立，无破坏性 schema 变更；旧存档、自定义规则与插件继续可用，无需手动迁移。
- 未配置向量服务也能正常游玩：此时使用场景锚点 + 关键词检索，行为与旧版本一致或更好。
- 本版为正式版，Docker 镜像会同时更新 `latest` 标签。
- 升级重要对局前建议备份完整的 `data/` 目录。

### 下载与校验

- **普通 Windows 用户**：`DiceFrame-v2.6.1-windows-portable.zip`
- **源码运行用户**：`DiceFrame-v2.6.1-windows.zip`
- **托管 Docker 更新**：`DiceFrame-v2.6.1-docker-update-linux-amd64.zip`
- 每个压缩包旁提供 `.sha256`，另有合集 `SHA256SUMS`。

## English

### New

- **Generic Hybrid Lore Retrieval for every ruleset**: normal rounds, swipes, and out-of-character questions now share one retrieval layer. Its input is this round's actions plus the current scene, the canonical location from world state, and the NPCs actually present — so lore defined for a location can be recalled even when the player's own text never names it.
- **Optional vector (semantic) retrieval**: reuses the existing embedding settings (toggle, provider, model, input limit) with **no new configuration fields**. When it is enabled, semantic similarity supplements keyword hits; when it is disabled, unreachable, failing, or returning malformed vectors, retrieval silently falls back to anchors plus keywords and **never blocks a round**.
- **Entry vector cache**: vectors are cached per entry, language, and model/endpoint, and rebuilt automatically when content changes, so the whole worldbook is not re-embedded every round. The cache is derived data and can be deleted safely.
- **Better worldbook projection**: the model now sees each entry's `type` / `tier` and whether it is marked `unreliable` (rumour, NPC belief, or subjective claim), together with explicit consistency rules: authoritative world state, system rulings, and ruleset runtime outrank the worldbook; the worldbook constrains only the facts it states; unstated areas may be improvised; the worldbook is not a script; later player-caused changes follow the current world state.
- **Player-facing answers no longer expose internal entry IDs**: out-of-character answers keep `type` / `tier` / `unreliable` and the entry text, but no longer hand internal canonical IDs (for example `npc_traitor_mary`) to the player-side model. GM-side prompts are unchanged.
- **Character creation: one-click control mode**: on the character step, each card's control mode is now a button next to Edit / Remove that cycles 玩家 → AI 托管 → 等待认领; the confirmation step no longer repeats the per-character control list.

### Fixes

- **Retrieval ordering**: keyword and semantic hits are merged and then sorted by `tier → order → source → similarity → id`, so a low-priority archived entry can no longer consume the context budget ahead of a high-priority one.
- **Malformed-vector tolerance**: non-numeric, `NaN`, or `Inf` vectors from a cache or an embedding service now only skip the affected semantic recall and can no longer affect a normal round.
- **Structural labels no longer trigger keywords**: labels used purely to structure the semantic query no longer participate in keyword matching, so English worldbooks whose keywords happen to be `scene` / `location` / `action` no longer match every single round.
- **Settings copy**: the four locales now call the capability "Vector / Semantic Retrieval" and explain that it powers both long-term memory and worldbook search, and that keyword/scene/structured retrieval is used when it is not configured.
- German settings hint article fix (`Aktiviere hier die Steuerung …`).

### Upgrade notes

- This release only **adds** one database table (the worldbook vector cache); it is created automatically at startup. No destructive schema change, no manual migration, and existing saves, custom rules, and plugins keep working.
- Playing without an embedding service stays fully supported: anchors plus keyword retrieval are used instead.
- This is a stable release, so Docker images also update the `latest` tag.
- Back up your whole `data/` directory before upgrading an important campaign.

### Downloads

- **Regular Windows users**: `DiceFrame-v2.6.1-windows-portable.zip`
- **Running from source**: `DiceFrame-v2.6.1-windows.zip`
- **Managed Docker update**: `DiceFrame-v2.6.1-docker-update-linux-amd64.zip`
- Each archive ships with a `.sha256` sidecar, plus a combined `SHA256SUMS`.
