# DiceFrame 平台方向落地施工计划

> 2026-10-15 已归档：旧分支的施工顺序和验收计数，仅用于追溯，不是当前待办。当前入口见[文档索引](../../README.md)。

> 这是一份实施计划，不是当前架构事实，也不是把讨论稿中的所有远景立即实现。
> 当前架构事实仍以 `ARCHITECTURE_CN.md`、`ENGINEERING_RULES.md` 和已经合并到 `main` 的代码为准。

## 1. 当前基线


旧工作区已做逐文件 SHA256 校验备份并保留，不能再作为后续功能的开发基线。本地整合包含：

- ContentRef / ContentDraft / CommitPlan、Book ownership、World v3、projection、legacy adapter、content binding；
- AI 席位 ready barrier、AI 失败后的安全推进；
- 完整的优势/劣势骰面与共享 click-to-reveal、release notes locale；
- Lorebook 导入重复策略和 plan digest；
- 世界书 #402–#405 布局修复与 World → Book → Entry 操作层次、俄语支持；
- Module / Adventure 编辑、安装、绑定，以及文字剧本导入、审核、发布、创建游戏和游玩的链路。

这仍是本地整合基线，GitHub 上的 PR 没有因此被合并。后续新功能以此分支为起点，保留 owning module 和可移植的功能提交；上游 PR 更新时同步整合并重新验证。不能再按旧 main 或零散复制的 PR 内容继续开发。

## 2. 讨论稿如何落到当前代码

讨论稿中的概念与当前项目的对应关系如下：

| 讨论稿概念 | 当前落点 | 现在的处理方式 |
|---|---|---|
| Gameplay Capability | `src/engine/modules/`、ruleset capability registry、D&D runtime | 继续用明确 owner 的模块槽和 capability contract；暂不做万能 DSL |
| Game Profile | 当前的 ruleset runtime + game creation 配置 | 先用现有 runtime capability 描述，不提前引入第二套 profile authority |
| Progression | 现有 round / adventure runtime / 后续 progression module | 保留 `free`、`adventure` 与未来 phase/calendar 的边界；不把所有玩法硬塞进 round |
| Content | World、Lorebook、Adventure、Ruleset Catalog、Assets | 继续通过 ContentKind / ContentRef / ContentDraft / CommitPlan 连接 |
| Module | Plugin/content package/catalog | 只做分发容器，不创建 Module 专属 store、规则 authority 或执行脚本 |
| UI Contribution | 固定 DiceFrame shell + 可信的 capability projection | 先做 server projection 和固定 surface；普通内容不能注入 Vue/JS/CSS |

第一阶段只验证“组合边界能否支持可玩的 Adventure”。等这一条链稳定后，再用 Heist 或 Survival 小型 demo 验证 Capability 和非 round progression。

## 3. 现有 PR 的合并和重排顺序

### 3.1 可以独立收口的 PR

- `#442`：AI 托管席位不阻塞遭遇 ready barrier；
- `#443`：release notes 按界面语言展示；
- `#444`：优势/劣势骰面和采用结果展示；
- `#445`：非阻塞 click-to-reveal dice presentation（含 schema v35）；
- `#401`：Imagegen 分镜与头像参考图。

这些 PR 不改变 Content ownership，可在最新 `main` 上分别 rebase、分别验收。

### 3.2 Track C 内容链

按依赖顺序处理：

```text
#453 contracts
  → #454 book ownership
  → #455 world v3 / AI drafts
  → #456 knowledge projection
  → #457 module catalog / Book import
  → #458 legacy import receipts
  → #459 projections + content_binding + import contracts
  → #460 legacy reads / route serialization / handoff
```

这条链是 Module/Adventure 后续施工的内容基础。`#459` 中涉及创建游戏和运行时调用的文件需要 Track R 复核；不能只按“内容 PR”快速合并。

### 3.3 Lorebook UI 链

`#402 → #403 → #404 → #405` 仍是一个依赖链。它与 `#459/#460` 都会改 `LorebookView.vue`，因此应在 Track C 链完成后统一 rebase，解决一次冲突，并用现行 Book/Binding contract 做 golden E2E。不要把旧 UI 分支直接覆盖新的 ownership 语义。

### 3.4 Module PR

- `#399`：规则集过滤和 Module 主题可以 rebase 最新 `main` 后合并；规则 ID 必须来自 `RulesetRuntimeRegistry`。
- `#400`：保持 HOLD。它的安全解析思路可以参考，但不能直接合并旧的 `ExternalModuleDraft`、Module Lorebook 读侧和旧 Human Review 流程。后续按 M6 重新接入统一 `ContentDraft`。
- `#437`：只是 Track R 验收台账，不代替任何实现 PR，也不应作为“大合并 PR”吞掉组件边界。

## 4. 第一条真正可玩的产品链：Module → Adventure → Game

当前后端已经有大部分接缝：

- Adventure Bundle / graph v2 校验和 viewer projection；
- `content_binding` 保存 world、book、adventure 的 source-aware refs；
- `game_lifecycle` 已能接收 adventure id、source 和 book bindings；
- `CreateView.vue` 已有 Adventure / Module 选择器。

2026-10-06 本地已补齐 Module Detail 的“用此冒险创建游戏”入口和 source-aware 预选。创建页会选取兼容规则及固定/推荐世界，缺少资源或不兼容时阻断；用户可明确改为自由模式。安装资源的统一说明仍需要后续产品整理。

施工顺序：

1. Module Detail 的每个 Adventure 增加“预览”和“创建游戏”按钮。
2. 创建页支持 `module_id`、`adventure_id` 查询参数预选，并保留用户修改规则、世界和 Book 的能力。
3. 服务端在创建时解析 Adventure、规则 runtime、World ref 和 required Book refs；缺失、digest 不符、runtime 不兼容时 fail closed。
4. 创建成功后只写 `content_binding` 和 Adventure run 初始状态；不把包内容复制进 World，也不修改原始模组。
5. 游玩页显示 GM/玩家安全的 Adventure projection；进度由 Adventure runtime 持有，规则变化仍经过规则 runtime / Intent / EventBatch / reducer。

验收必须覆盖：固定世界、可携带世界、无世界依赖三种 world policy；缺包、错误版本、错误 ruleset、隐藏节点投影；已有存档绑定后禁止原地更新/卸载。

## 5. 剧本导入的第一版

不要从 PDF 或第三方 VTT 直接生成可运行模块。第一版只做确定、可审查的文本来源：`.md` / `.txt`。

```text
文本文件
  → 纯函数解析器
  → ContentDraft + Adventure Graph v2 draft
  → Preview（warnings / blockers / unresolved refs / resource map）
  → 用户在现有 AdventuresView 编辑
  → 服务端校验并发布 immutable Adventure version
  → Module/standalone package
  → Create Game binding
```

建议的最小标记：

- `#`：冒险标题；
- `##`：章节；
- `###`：场景/步骤；
- `@npc`、`@location`、`@encounter`：显式引用；
- `@choice 描述 -> node_id`：后续节点；当前遵循 v2 的并行图语义，多条无条件边会同时开放，不是互斥玩家选项；
- `GM:`：单行 GM 私密备注，拆成独立私密 reference 节点。

没有标记的文本只能作为叙事草稿，不能猜成怪物、法术、伤害或规则效果。未知引用进入 unresolved references；发布前必须处理或明确仅保留为文字。第一版不提供自动资源映射、PDF/OCR 或 AI 解析。全部导入节点默认 GM 可见，用户可逐节点改为公开。AI 的后续扩展只能生成 Draft，不能直接发布或改变规则数值。

## 6. D&D 模组如何映射

外部 D&D 内容要拆成四种对象，而不是把整本书塞进世界书：

| 来源内容 | DiceFrame 对象 |
|---|---|
| 剧情章节、场景、分支、结局 | Adventure graph |
| 长期地点、势力、背景事实 | World / Lorebook |
| 怪物、物品、法术、职业、遭遇模板 | Ruleset Catalog 或 Adventure-local resource |
| 本局已经发生的选择、战斗、线索、奖励 | Session / Adventure runtime state |

Foundry 的 Adventure 本身就是将 Actors、Scenes、Items、Roll Tables、Journal 等关联内容打包供导入的内容对象；Fantasy Grounds Module 也把 Stories、NPC、Encounters、Items、Parcels 和地图资源作为可安装内容。DiceFrame 应吸收这种“结构化内容包”的思想，但仍把规则 authority 和存档状态留在自己的 runtime 中：[Foundry Adventure Documents](https://foundryvtt.com/article/adventure/)、[Fantasy Grounds Modules](https://fantasygroundsunity.atlassian.net/wiki/spaces/FGCP/pages/996640899)。

适配器顺序：

1. Markdown/TXT：先做，产出统一 Draft；
2. DiceFrame native `.dfadventure.zip`：现有路径继续作为无损交换格式；
3. Foundry Adventure JSON：结构化程度高，作为 M6 第一个外部 adapter；
4. Fantasy Grounds `.mod`：只读安全解析 XML/ZIP，映射 Stories/NPC/Encounters/Items/Parcels/assets；
5. PDF、Roll20 等：最后做，始终先生成 Draft，不承诺自动得到可运行的规则内容。

任何外部格式都必须 fail closed、限制大小、拒绝可执行字段，并经过 Human Review。解析器不能绕过 ContentDraft、CommitPlan、ContentRef 和 Adventure validator。

## 7. 讨论稿的第二阶段：Capability 验证

当 Module/Adventure 闭环和 Content Track 稳定后，再做一个极小的 Heist demo：

```text
checks + moves + clocks + stress + harm + factions + downtime
```

只验证以下问题：

- 是否能用现有 Game Shell，而不复制 D&D PlayView；
- 是否能用 phase/scene progression，而不伪装成 round；
- AI 是否只提交 structured intent，由 capability/runtime 校验和落账；
- Character、Action Bar、Status/Track、GM Panel 是否可以由 projection 组合。

如果这个 demo 需要大量 `if heist`，才说明应继续抽 capability contract。此之前不做 Universal RPG DSL、通用公式编辑器、可视化节点编辑器或第三方任意 UI 执行。

## 8. 当前用户交互完成度


| 改动 | UI 状态 | 结论 |
|---|---|---|
| Dice reveal | #445 卡片、房间设置和共享揭示已接入，但有 10 秒本地倒计时自动翻开 | 非阻塞链路已做；仍需对齐原计划“不计秒、不倒计时” |
| Release notes locale | presenter、设置页和启动检查页已有 | 端到端完成 |
| Advantage dice | #444 双骰及采用结果、来源解释已接入 | 结果展示已做；掷骰前入口、申请/授予流程和 CoC 专门表现仍需补齐 |
| Lorebook 导入冲突 | update / duplicate / skip 和 plan digest 已接入 | 主要完成；unresolved references 仍缺少清晰的前端列表和阻断提示 |
| AI 失败/自动继续 | 后端安全 fallback、日志和推进已接入；已有通用停止托管按钮 | 失败专属状态、原因、重试和恢复操作未形成完整流程 |
| 每个 AI 队友的模型和风格 | 只有控制方式切换；叙事生成仍接收共享 LLM client | provider/model 引用、风格、继承和失效状态未完成 |
| Module → Adventure → Create Game | 模组/冒险页面入口、准确来源预选、兼容性阻断、实际开团已接通 | 本地已实现，等待按边界整理 PR |
| 剧本 `.md/.txt` 导入 | 上传 → 图预览/修改 → 引用阻断 → 人工确认 → native 发布 → 创建游戏 | 第一版本地已实现 |

仍有交互缺口，尤其是每座位 AI 配置、AI 失败提示和骰子原计划对齐。模组启动与文字剧本第一版已完成；统一多类型内容审核、完整模组产品面、Foundry、Fantasy Grounds、PDF、Heist 和通用平台仍需后续施工。音乐继续挂起。

## 9. 下一批 PR 的边界

按下面顺序拆，不再把整个大版本塞进一个 PR：

1. **Adventure Launch UI**：Module Detail CTA、CreateView 预选、创建前兼容性摘要、绑定回显。
2. **Text Script Adapter**：Markdown/TXT parser、golden fixtures、preview API、unresolved refs。
3. **Adventure Review UI**：把 Draft preview 接到现有 AdventuresView，发布前校验和版本化。
4. **AI Failure UX**：托管席位状态、fallback 原因、重试/交还控制权。
5. **Foundry Adapter**：仅在前四项和 Track C/M1–M5 稳定后启动。
6. **Heist Capability Spike**：只做实验分支和验收样例，不提前承诺通用平台 DSL。

每个 PR 都要说明是否升存档 schema、是否改变 binding contract、旧数据是保留/适配/迁移/拒绝，以及对应的后端、前端和 E2E 验收。

## 10. 2026-10-06 本轮交付与验证

本轮只交付上述第 1–3 项的本地实现，未合并、发布或升版本。Parser、review/commit service、routes、图编辑表单和创建页 selection owner 分开实现；沿用现有 source-aware Adventure binding、v2 progress 和 native import 校验，没有新增存档 schema 或自动迁移。

- 后端全量：5344 passed、1 skipped；其中新增文字导入测试 18 项，覆盖权限、体积、路径、未审查/陈旧预览/未解析引用拒绝、重复身份、来源信息保存、实际开团及存档恢复。
- 前端全量：111 个文件、654 项通过；包含准确来源启动、兼容性阻断、编辑后重新校验、发布确认，以及 v2 编辑不丢资源和条件。
- Playwright：桌面/手机共 4 项通过；真实上传、修改、发布、预选创建、角色创建、游玩、节点推进，以及模组启用后的准确来源交接。
- 类型检查、ESLint、Ruff、生产构建、diff whitespace 检查通过。

用户操作及文本样例见 [冒险与创建游戏](../../user/adventures.md)。下一批仍为 AI Failure UX；外部 VTT adapter 和 Capability demo 继续按第 9 节依赖顺序推进。
