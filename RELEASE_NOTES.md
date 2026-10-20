# DiceFrame v3.0.0

> 正式版本：从 v2.6.1 到 3.0.0 的累计更新。3.0 将模块化运行时、通用内容与冒险包、DF Agent、剧情计划、CoC 资源恢复和新的多人安全边界整合到同一条稳定主线。

## 中文

### 核心运行时与内容

- **模块化运行时**：规则、战斗、健康、世界书、媒体、席位、私聊、检查和玩家控制等能力通过生命周期 hooks 接入回合、重置、回退、恢复和状态读写，各模块拥有自己的状态边界。
- **Lorebook 运行时**：资料册按 canonical Book 及 world/game/character scope 解析；每本资料册保留自己的 token budget，条目经过统一的启用、可见性、时间状态、分组和预算判定。
- **激活诊断与计时**：关键词、递归和语义候选使用统一的激活流程；激活记录可查看命中、跳过和预算原因，持续生效、冷却和延迟在回合生命周期中推进。
- **通用内容库**：World 与 Book（资料册）使用分离的 canonical identity、来源和绑定投影；内容导入采用预览、确认和回执边界，保留语言、版本、来源和 profile 校验。
- **内容与导入契约**：资料册、角色卡和内容包在写入前校验 identity、来源、绑定范围和结构；确认后的操作可核对，歧义或冲突输入停在边界，不覆盖已有内容。
- **通用冒险包**：冒险包不再绑定 D&D；故事冒险支持目标、run plan、自由冒险与模组冒险边界、数据包校验、创作者 starter 和发布源所有权检查。
- **冒险建议**：AI 可以根据已提交的对局记录提醒 GM 检查节点或目标；提醒不会推进节点，完成仍由 GM 手动确认。
- **剧情计划与结团**：本局剧情计划、目标投影、幕间成长和不可变结团档案通过权威生命周期保存，公开日志只投影允许公开的字段。
- **规则与战斗**：规则运行时在创建时绑定并在权威写入时校验；D&D 2024 战斗回合来自规则投影，遭遇预设与怪物数据保持 GM 可见，手动骰、检定揭示、资源和多人行动由服务端结算。
- **CoC 资源恢复**：区分轻量房规与 CoC 7e 风格策略，可申请过夜休整和治疗、领取 GM 授权的 SAN/Luck 剧情奖励，并按启用的策略进行幕间 Luck 恢复检定；服务端负责时间、权限和一次性结算，普通恢复不能解除永久疯狂。

### DF Agent

- **发现可用能力**：Agent 可按需发现世界、房间、冒险和资料册等已接入的操作，通过应用现有业务入口查询或修改，保留权限与版本校验。
- **按范围授权**：建议、日常与任务模式分别用于提供建议、自动处理普通工作和接管指定任务。改变规则决策权、对外操作及破坏性修改仍需具体确认；没有有效页面资源时，不会将“当前范围”默认为全部资源。
- **批量修改资料册可见性**：一句话可让 Agent 查找多本资料册并制定统一计划。已有覆盖目标的任务授权时，可自动收紧为 GM 可见；公开给玩家或扩大可见范围，只确认整个计划一次。可见性操作只更新 `visible_to`，保留正文和其他创作字段；拆成单条操作仍遵守相同授权规则。
- **工作区与恢复**：新增待审批数字徽标，可折叠工作区、语音和版本匹配的帮助。批量计划保留逐册事务、结果与恢复记录；在服务端保留期内，暂停、部分失败或重启后可继续剩余目标，已完成目标不会重复执行。取消会阻止尚未派发的写操作。
- **独立预算**：每次回复默认上限为 4,096 token；Agent 模型调用的任务累计预算默认为 256,000，可配置为 16,000–2,000,000。内容生成工具仍使用对应能力的独立输出配置；任务预算并非供应商账单上限。
- **更大的内容生成额度**：世界、资料册和冒险草稿等文本生成的默认输出上限提高到 **16,384 token**，包括 Agent 发起的内容生成，减少完整冒险被低输出额度截断的问题。

### 游玩、设置与多人体验

- **冒险面板**：冒险入口位于场景标题栏的检定旁，打开独立弹窗；长内容可以滚动，不再挤占桌面或手机对话区。角色栏将地图移到感知上方，并移除重复的当前冒险条目。
- **GM 与邀请**：GM 工作台点击外部仍保持打开并保留草稿；房间密码放在“邀请玩家”旁。普通新角色邀请与已有角色认领链接的用途说明分开显示。
- **创建与内容管理**：整理内容库、世界画廊、资料册、角色与冒险包页面的卡片和按钮；创建模组冒险时，明确标注“不使用额外内容包”的选项，并改善未完成专业角色卡的提交提示。
- **Getting Started**：概览页提供可收起、可关闭的入门指引；关闭后可从概览入口重新打开，手机布局同样保留启动路径。
- **共享休息活动**：队伍成员可查看当前 run 的恢复请求、结算状态和协同短休/长休活动。通知默认开启、非打断式；提示可关闭并约 5 秒后消失，每个 actor 可按游戏在自己的设备上静音，历史记录由用户手动打开。
- **响应式游玩**：统一快捷行动、行动输入、队伍和角色状态入口；骰子揭示偏好持久化，优势骰、结构化旁白/对话、场景图与分镜流程得到支持，亮色模式和二级导航更易读。
- **设置与语言**：系统语言与设置共用设备偏好；语音引擎选项归入模型卡。更新检查、下载和安装位于“设置 → 关于”，保留版本回退位于“通用 → 系统维护”。
- **手机、分享与安全**：移动端最低支持版本为 0.6.0；席位、分享链接、房间密码、设备 token 和撤销按游戏与设备隔离。GM、玩家、Bot、P2P 和分享访客收到相应的服务端投影。
- **Docker 与本地化**：托管 Docker 使用版本化数据副本、健康检查、观察期和可验证回退；稳定版镜像移动 latest 到 3.0.0。英文与简体中文为核心语言，其他语言在缺失或过期时回退英文。

### 重要修复

- 修复公开结团档案和旧 action 数据的过滤，非字符串内部字段不会进入公开投影；修复冒险源所有权、Bot/KP 问答范围、撤销凭据后的 SSE 流和多人席位接管边界。
- 修复世界书绑定、内容来源、导入回执、资料册语言范围、数据包 profile、外部模块预览和公开日志的一致性问题。
- 修复移动端覆盖层、角色状态入口、冒险面板滚动、GM 段落缩进、骰子揭示状态、亮色存档标题对比度和前端依赖安全问题。

### 升级、兼容与下载

- 这是 `3.0.0` 正式版。升级重要对局前请备份完整的 `data/` 文件夹，并保留 `data/_updater/`、`data-bindings/` 和 `data-pending/`。
- GameInstance 存档迁移到 schema 47，资料册数据库迁移到 schema 12；44→45 拆分本局配置与展示偏好，45→46 建立剧情、成长和结团写入边界，46→47 增加一次性资源恢复的权威记录边界。
- beta.2 及更早版本的读者不能直接读取 schema 47 存档；降级请使用对应版本保留的数据或升级前备份。启动时会安全重绑定旧世界和资料册 identity，保留展示标题、条目、角色、game_key 和聊天/日志文本；歧义、冲突或未知未来格式会在写入前拒绝迁移。
- AI 配置只接受共享服务商目录 `ai_providers`、独立凭据 `ai_provider_key_<id>` 与能力级 `*_provider_ref`。旧直填地址、密钥、API 字段及旧 AI 环境配置不会自动转换；缺失或失效引用会使能力保持未配置或停用。升级后如显示未配置，请在设置中选择有效服务商和模型。
- 首次升级到 3.0.0 时，低于 `16,384` 的旧文本生成上限（包括旧自定义低值）会一次性提高到 `16,384`；更高的值保留。升级后仍可自行降低，后续启动不会再次强制提高；其他能力预算保持原设置；显式设置的 `TRPG_TEXT_GEN_MAX_TOKENS` 环境覆盖仍优先，不会被自动提额替代。
- TTS 的 `browser`、`edge-tts` 和 ASR 的 `disabled` 无需服务商引用；其他需要远端地址的 TTS（含 `gpt-sovits`）和 ASR 必须选择有效服务商。
- 托管 Docker 更新包要求 Python ABI、系统运行时和 launcher 兼容；基础镜像、系统库、CA、字体或 launcher 协议变化仍需拉取新镜像。稳定版将 GHCR 与 Docker Hub 的 `latest` 同步更新到 `3.0.0`。
- 内容包、规则包与插件需匹配各自的格式和运行时契约；不支持的数据格式在对应校验边界拒绝。插件的最低应用版本提示不等于所有插件都存在统一的安装门禁。移动端最低支持 `0.6.0`。
- **普通 Windows 用户**：`DiceFrame-v3.0.0-windows-portable.zip`
- **源码运行用户**：`DiceFrame-v3.0.0-windows.zip`
- **托管 Docker 更新**：`DiceFrame-v3.0.0-docker-update-linux-amd64.zip`
- Release 提供以上三个压缩包及一个合集校验文件：`SHA256SUMS`。

## English

### Core runtime and content

- **Modular runtime**: rules, combat, health, lore, media, seats, private channels, checks, and player control join round, reset, rewind, recovery, and state boundaries through lifecycle hooks with clear ownership.
- **Lorebook runtime**: books resolve through canonical Book identity and world/game/character scopes; each book keeps its own token budget, while entries pass one eligibility pipeline for enabled state, visibility, timers, groups, and budget.
- **Activation diagnostics and timers**: keyword, recursive, and semantic candidates share one activation pipeline. The activation trace explains hits, skips, and budget decisions; sticky, cooldown, and delay advance at round lifecycle boundaries.
- **Unified content library**: Worlds and Books have separate canonical identities, sources, and binding projections. Imports use preview, confirmation, and receipt boundaries with locale, version, source, and profile validation.
- **Content and import contracts**: lorebooks, character cards, and packages validate identity, source, binding scope, and structure before writes. Confirmed operations remain auditable, while ambiguous or conflicting input stops at the boundary without overwriting existing content.
- **Universal adventure bundles**: adventure packages are no longer tied to D&D and support objectives, run plans, free-play and module-play boundaries, data-only validation, creator starters, and source ownership.
- **Adventure suggestions**: AI may remind the GM to review a node or objective from committed history; a suggestion never advances it, and completion still requires explicit GM confirmation.
- **Story plans and finales**: per-run plans, objective projections, intermission growth, and immutable finale archives persist through authoritative lifecycle boundaries, while public logs expose only allowed fields.
- **Rules and combat**: rulesets bind at game creation and are checked at authoritative writes. D&D 2024 combat turns are ruleset projections, encounter presets and monster data remain GM-only, and manual rolls, check reveals, resources, and multiplayer actions stay server-authoritative.
- **CoC resource recovery**: separate lightweight house rules and CoC 7e-style strategies support rest and treatment requests, GM-authorized SAN/Luck story rewards, and intermission Luck checks according to the enabled policy. Time, permissions, and one-use settlement remain server-authoritative; ordinary recovery cannot reverse permanent madness.

### DF Agent

- **Discover available capabilities**: the Agent discovers supported world, room, adventure, and lorebook operations on demand. Reads and writes use existing application services with permission and version checks.
- **Authorize by scope**: Suggest, Routine, and Task modes support advice, automatic routine work, and delegated tasks. Changes to rules authority, external actions, and destructive operations still require concrete approval. Without a valid page resource, “current scope” no longer silently means all resources.
- **Grouped lorebook visibility**: one instruction can discover multiple books and prepare one plan. A covering Task grant allows automatic narrowing to GM-only; public disclosure or wider audiences require one approval for the whole plan. Visibility actions patch only `visible_to`, preserving bodies and other creative fields; entry-level calls follow the same semantic authorization.
- **Workspace and resume**: pending-approval badges, a collapsible workspace, speech, and version-matched help make tasks easier to follow. Batch plans retain per-book transactions, results, and recovery records. Within server retention, paused, partially failed, or restarted work resumes remaining targets without replaying completed books. Cancellation stops undispatched writes.
- **Independent budgets**: the default per-reply limit is 4,096 tokens; cumulative Agent model usage has a separate task budget of 256,000, configurable from 16,000 to 2,000,000. Content-generation tools retain their capability-specific output settings; the task budget is not a provider billing cap.
- **Larger content output**: text generation for world, lorebook, and adventure drafts now defaults to **16,384 tokens**, including content generation invoked by the Agent, reducing truncation from low output limits.

### Play, settings, and multiplayer

- **Adventure panel**: the Adventure entry sits beside Checks in the scene header and opens an independent dialog. Long content scrolls without shrinking desktop or mobile chat; the character rail places the map above perception and removes the duplicate current-adventure section.
- **GM and invitations**: outside clicks leave the GM workbench open and preserve drafts; room-password controls sit beside Invite player. New-character invitations and existing-character claim links now explain their different purposes.
- **Creation and content management**: library, world gallery, lorebook, character, and adventure cards and buttons are more consistent. Module creation explicitly labels the option to use no additional content pack, and incomplete professional character submissions receive clearer feedback.
- **Getting Started**: Overview includes a collapsible, dismissible onboarding guide. After dismissal it can be reopened from the Overview entry, including on mobile.
- **Shared rest activity**: party members can review current-run recovery requests, settlement states, and cooperative short/long rest activity. Notices are enabled by default and non-interrupting; a toast can be dismissed and disappears after about five seconds, while each actor can mute it per game on their own device and open history manually.
- **Responsive play**: compact actions, action input, party and character controls are unified; dice reveal preferences persist, advantage dice are visible, structured narration/dialogue and storyboard flows are supported, and light-mode contrast and secondary navigation are improved.
- **Settings and language**: the header and General settings share a device-local language preference; speech options live with model cards. Update checks, downloads, and installation remain in Settings → About, while retained-version rollback is under General → System maintenance.
- **Mobile, sharing, and security**: the minimum mobile client is 0.6.0. Seats, share links, room passwords, device tokens, and revocation are scoped per game and device; GM, player, Bot, P2P, and share visitors receive the corresponding server-side projection.
- **Docker and localization**: managed Docker uses versioned data copies, health checks, probation, and verifiable rollback; stable images move latest to 3.0.0. English and Simplified Chinese are core locales, with English fallback for missing or stale community translations.

### Notable fixes

- Public finale archives and legacy action data are filtered so non-string internal fields do not enter public projections; adventure ownership, Bot/KP scope, revoked SSE streams, and multiplayer seat takeover boundaries are enforced.
- World/Book binding, content provenance, import receipts, locale-scoped lore, package profiles, external-module previews, and public-log projection now handle ambiguous input consistently.
- Mobile overlays, character-state access, adventure-panel scrolling, GM paragraph indentation, dice reveal state, light-mode archive contrast, and frontend dependency security were corrected.

### Upgrade, compatibility, and downloads

- This is the `3.0.0` stable release. Back up the complete `data/` directory before upgrading an important campaign, including `data/_updater/`, `data-bindings/`, and `data-pending/`.
- GameInstance saves migrate to schema 47 and Lorebook databases to schema 12. 44→45 separates table configuration and presentation preferences; 45→46 establishes story, growth, and finale write boundaries; 46→47 adds the authoritative one-use recovery boundary.
- beta.2 and older readers cannot read schema-47 saves. Downgrade with the matching retained dataset or a pre-upgrade backup. Startup safely rebinds legacy world and Book identities while preserving display titles, entries, characters, game_key, and chat/log text; ambiguous, conflicting, or unknown-future layouts stop before writes.
- AI configuration accepts only shared `ai_providers`, independent `ai_provider_key_<id>` credentials, and capability-level `*_provider_ref` values. Legacy inline URL, key, API, and old AI environment fields are not converted; missing or invalid references leave a capability unconfigured or disabled. Select a valid provider and model in Settings if configuration is incomplete after upgrading.
- On the first upgrade to 3.0.0, existing text-generation limits below `16,384`, including custom lower values, are raised once to `16,384`; higher limits are preserved. Users may lower the value afterward without it being reset on later starts. Other capability budgets keep their existing settings; an explicit `TRPG_TEXT_GEN_MAX_TOKENS` environment override still takes precedence and is not replaced by this increase.
- TTS `browser` and `edge-tts`, and ASR `disabled`, need no provider reference. Other remote TTS, including `gpt-sovits`, and ASR require valid provider references.
- Managed Docker packages require compatible Python ABI, system runtime, and launcher. Base-image, system-library, CA, font, or launcher-protocol changes still require a new image. Both GHCR and Docker Hub `latest` move to `3.0.0`.
- Content packs, rulesets, and plugins must match their respective format and runtime contracts; unsupported data formats are rejected by their validators. Plugin minimum-application-version notices are not a universal installation gate. The minimum supported mobile client is `0.6.0`.
- **Regular Windows users**: `DiceFrame-v3.0.0-windows-portable.zip`
- **Source users**: `DiceFrame-v3.0.0-windows.zip`
- **Managed Docker update**: `DiceFrame-v3.0.0-docker-update-linux-amd64.zip`
- The Release provides exactly these three archives and one combined checksum file: `SHA256SUMS`.
