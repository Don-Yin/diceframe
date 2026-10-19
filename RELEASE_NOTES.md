# DiceFrame v3.0.0-beta.3

> 预览版本：DiceFrame 3.0 的模块化运行时、通用内容与冒险包、DF Agent、剧情计划和新的多人安全边界首次整合到同一条主线。它是公开测试版本，适合验证新功能与升级流程。

## 中文

### 相较 beta.2

- **CoC 资源恢复**：新增恢复/休整面板，支持申请过夜休整与治疗、GM 审批、SAN/Luck 剧情奖励领取和幕间 Luck 恢复检定。规则需显式启用恢复策略；服务端统一处理时钟、权限、一次性回执和重复提交，普通恢复不能解除永久疯狂。
- **旧数据升级**：启动时安全重绑定旧世界与资料册引用，修复旧世界标题被用作标识后无法开局的问题；保留展示名称、条目和角色数据。歧义、冲突及不支持的未来存档会在写入前拒绝迁移。
- **冒险面板**：入口移到场景标题栏的检定旁，点击后打开独立弹窗；修复长内容的滚轮滚动，不再挤占桌面或手机对话区。角色栏的地图移到角色感知上方，并移除重复的当前冒险条目。
- **冒险节点提醒**：AI 可根据已提交的对局记录提示 GM 检查当前节点是否完成。提醒不会挤占对话区，可从提示或面板徽标查看；GM 可忽略建议，节点仍由 GM 手动确认完成，AI 不会自动推进。
- **GM 与联机操作**：GM 工作台点击外部保持打开，保留连续操作和输入草稿；房间密码独立放在邀请玩家旁。补充普通邀请与已有角色认领链接的用途说明，修复专业角色卡未完成时的提交与错误提示。
- **更新入口**：检查、下载与安装更新仍位于设置的“关于”；只有上一版本回退入口放到“通用 → 系统维护”。创建模组冒险时，不使用额外内容包的选项也有明确说明。

### 主要更新

- **模块化运行时**：能力模块通过生命周期 hooks 接入回合、重置、回退和状态读写；规则、战斗、健康、世界书、媒体、席位与私聊等职责回到各自 owner，逐步移除肥大的 `GameInstance` facade，降低核心与扩展模块的耦合。
- **通用内容库**：World 与 Book（资料册）拥有分离的 canonical identity、来源和绑定投影；内容导入采用预览、确认和回执流程，支持内容同步、外部模块安全预览、内容包 profile 校验和语言回退。
- **通用冒险包**：冒险包不再绑定 D&D，支持通用故事冒险；新增冒险目标、run plan、自由冒险与模组冒险边界、数据包校验、创作者 starter，以及发布源所有权保护。
- **剧情计划与结团**：新增本局剧情计划、目标投影、幕间成长和不可变结团档案；结算结果绑定权威生命周期与一次性回执，公开日志只投影允许公开的字段。
- **DF Agent**：Agent 进入应用壳，支持只读查询、草稿、延迟审批和恢复；拥有独立 token 预算（默认 4096）、可折叠任务工作区、语音、版本匹配的帮助文档、内容创作与游戏操作工具。Agent 不绕过领域服务直接修改规则状态。
- **游玩与叙事体验**：重做移动端与响应式游玩布局，统一快捷行动、行动输入、队伍与角色状态入口；支持骰子揭示偏好持久化、优势骰展示、结构化旁白/对话、场景图与分镜流程、亮色模式可读性和吸顶二级导航。
- **规则与战斗边界**：规则运行时在创建时绑定并在权威写入时校验；D&D 2024 的战斗回合改为规则投影，遭遇预设与怪物数据保持 GM 可见；手动骰、检定揭示、资源和多人行动继续由服务端结算。
- **多人安全与凭据**：席位、分享链接、房间密码和撤销流程按游戏与设备隔离；只读 GM/KP 问答、公共日志、玩家投影和 Bot 流均在服务端先做权限过滤。
- **更新与数据恢复**：托管 Docker 使用版本化数据副本、健康检查、观察期和可验证回退；应用更新不会猜测旧 AI 直填配置，也不会把未知未来存档强行转换。
- **本地化**：系统语言与设置共用设备偏好；核心英文/简体中文保持完整，社区语言按维护状态提供并在缺失或过期时回退英文。

### 重要修复

- **前端依赖安全更新**：更新 Vue、DOMPurify 和相关依赖，修复当前 npm 审计报告中的已知漏洞。
- 修复公开结团档案对旧 action 数据的过滤，非字符串内部字段不会再进入公开投影。
- 修复冒险源所有权、只读页面发放房间凭据、Bot/KP 问答范围、撤销凭据后的 SSE 流和多人席位接管边界。
- 修复世界书绑定、内容来源、导入回执、资料册语言范围和数据包 profile 的一致性问题。
- 修复移动端覆盖层、角色状态入口、二级导航停靠、GM 段落缩进、骰子揭示状态和亮色存档标题对比度。

### 升级说明

- 这是 `3.0.0-beta.3` 预览版。升级重要对局前请备份完整的 `data/` 文件夹，并保留 `data/_updater/`、`data-bindings/` 和 `data-pending/`。
- 支持的 GameInstance 存档迁移到 schema `47`，资料册数据库迁移到 schema `12`。44→45 拆分本局配置与展示偏好，45→46 建立剧情、成长和结团写入的读者隔离边界，46→47 增加一次性资源恢复的权威记录边界；不会猜测历史计划、成长标记或恢复资格。beta.2 及更早版本不能直接读取升级后的存档；降级应使用对应版本的保留数据或升级前备份。未知未来版本和歧义格式会明确拒绝。
- AI 配置只接受服务商目录、独立凭据和能力级引用。旧直填地址/密钥不会自动猜测转换；升级后如能力显示未配置，请在设置中选择有效服务商引用。
- 支持托管更新的 Docker 在 Python ABI 和系统运行时兼容时可直接应用版本化更新包；基础镜像、Python ABI、系统库、CA、字体或 launcher 协议变化仍需重新拉取镜像。预览版不会移动 Docker `latest` 标签。
- 移动端最低支持版本为 `0.6.0`。插件和内容包应声明自己的 runtime、schema 与最低版本，未知或不兼容的包会在安装/运行边界拒绝。

### 下载与校验

- **普通 Windows 用户**：`DiceFrame-v3.0.0-beta.3-windows-portable.zip`
- **源码运行用户**：`DiceFrame-v3.0.0-beta.3-windows.zip`
- **托管 Docker 更新**：`DiceFrame-v3.0.0-beta.3-docker-update-linux-amd64.zip`
- Release 提供统一的 `SHA256SUMS` 文件校验以上三个压缩包。

## English

### Since beta.2

- **CoC resource recovery**: a Recovery / rest panel supports overnight and treatment requests, GM approval, SAN/Luck story rewards and intermission Luck checks. Rules explicitly opt in; the server owns time advancement, authorization, one-use receipts and retry safety. Ordinary recovery cannot reverse permanent madness.
- **Legacy data upgrades**: startup safely rebinds legacy world and Book references that used display titles as identifiers, preserving titles, entries and characters. Ambiguous, conflicting and unsupported future saves stop migration before writes.
- **Adventure panel**: the entry now sits beside Checks in the scene header and opens an independent dialog. Long content scrolls correctly without shrinking desktop or mobile chat. The character rail places the map above perception and removes the duplicate current-adventure section.
- **Adventure node reminders**: the AI can suggest that the GM review an active node based on committed game history. Notices stay out of the chat layout and are available from the notice or panel badge; the GM can ignore them, and node completion still requires GM confirmation.
- **GM and multiplayer controls**: outside clicks leave the GM workbench open and preserve unfinished inputs. Room password management sits beside Invite player. Join guidance distinguishes new-character invitations from existing-character claim links, and incomplete professional characters receive clearer submission handling and errors.
- **Update navigation**: version checks, download and installation remain in Settings → About; only previous-version rollback lives under General → System maintenance. Module-adventure creation also clearly labels the option to use no additional content pack.

### Highlights

- **Modular runtime**: capability modules now join round, reset, rewind, and state boundaries through lifecycle hooks. Rules, combat, health, lore, media, seats, and private channels own their data instead of extending a broad `GameInstance` facade.
- **Unified content library**: Worlds and Books (lorebooks) have separate canonical identities, sources, and binding projections. Imports use preview, confirmation, and receipt boundaries, with content sync, safe external-module previews, package-profile validation, and locale fallback.
- **Universal adventure bundles**: adventure packages are no longer tied to D&D. Story adventures now have objectives, run plans, free-play and module-play boundaries, data-only package validation, creator starters, and source-ownership checks.
- **Story plans and finales**: per-run plans, objective projection, intermission growth, and immutable finale archives are persisted through authoritative lifecycle boundaries. Public logs expose only an explicit allowlist.
- **DF Agent**: the Agent is integrated into the application shell with read-only queries, drafts, delayed approvals, and recovery. It has an independent token budget (4096 by default), a collapsible task workspace, speech, version-matched help, content-authoring tools, and game tools. It cannot bypass domain services to mutate rules state.
- **Play and narrative UX**: responsive desktop/mobile play surfaces were reorganized around compact action entry, party and character controls. Dice reveal preferences persist, advantage dice are visible, structured narration/dialogue and storyboard flows are supported, light-mode contrast is improved, and secondary navigation follows the visible header.
- **Rules and combat boundaries**: ruleset runtimes bind at game creation and are checked at authoritative writes. D&D 2024 combat turns are derived from the ruleset projection, while encounter presets and monster data remain GM-only. Manual rolls, check reveals, resources, and multiplayer actions remain server-authoritative.
- **Multiplayer security**: seats, share links, room passwords, and revocation are scoped per game and device. Read-only GM/KP questions, public logs, player projections, and Bot streams are filtered before delivery.
- **Updates and recovery**: managed Docker uses versioned data copies, health checks, probation, and verifiable rollback. Updates do not guess old inline AI configuration or force unknown future saves through a migration.
- **Localization**: the header and General settings share one device language preference. English and Simplified Chinese are maintained as core locales; community locales fall back to English when missing or stale.

### Notable fixes

- **Frontend dependency security**: update Vue, DOMPurify, and related packages to address the known issues reported by npm audit.
- Public finale archives now reject non-string legacy action values, preventing internal fields from entering public projections.
- Adventure source ownership, read-only room-credential issuance, Bot/KP scope, revoked SSE streams, and multiplayer seat takeover boundaries are enforced server-side.
- World/Book binding, content provenance, import receipts, locale-scoped lore, and data-only package profiles now fail closed on ambiguous inputs.
- Mobile overlays, character-state access, sticky secondary navigation, GM paragraph indentation, dice reveal persistence, and light-mode archive contrast were corrected.

### Upgrade notes

- This is the `3.0.0-beta.3` preview release. Back up the complete `data/` directory before upgrading an important campaign, including `data/_updater/`, `data-bindings/`, and `data-pending/`.
- Supported GameInstance saves migrate to schema `47` and Lorebook databases to schema `12`. Migration 44→45 separates table configuration and presentation preferences; 45→46 fences story, growth and finale writes; 46→47 adds the one-use recovery authority boundary without inventing historical plans, growth marks or recovery qualifications. Beta.2 and older readers cannot read upgraded saves; use the matching retained dataset or pre-upgrade backup when downgrading. Unknown future versions and ambiguous layouts are rejected.
- AI configuration accepts only the provider directory, independent credentials, and capability-level references. Legacy inline URLs and keys are not guessed into providers; configure valid references if a capability is unconfigured after upgrade.
- Managed Docker can apply the versioned update package when the Python ABI and system runtime are compatible. Base-image, Python ABI, system-library, CA, font, or launcher-protocol changes still require a new image. A preview release does not move the Docker `latest` tag.
- The minimum supported mobile client version is `0.6.0`. Plugins and content packages should declare their runtime, schema, and minimum-version contracts; unknown or incompatible packages are rejected at the install/run boundary.

### Downloads and verification

- **Regular Windows users**: `DiceFrame-v3.0.0-beta.3-windows-portable.zip`
- **Source users**: `DiceFrame-v3.0.0-beta.3-windows.zip`
- **Managed Docker update**: `DiceFrame-v3.0.0-beta.3-docker-update-linux-amd64.zip`
- The Release includes one combined `SHA256SUMS` file for these three archives.
