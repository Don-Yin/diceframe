# DiceFrame v3.0.2

## 中文

3.0.2 汇总 3.0.0 之后的稳定性、部署、Agent、D&D 2024 和 TTS 修复。

### 稳定性与部署

- 独立检定模型配置失效时返回明确的 409 业务错误，不再出现裸 HTTP 500 或伪成功。
- 增加检定模型失败后的恢复路径，并修复 Bot 席位认领边界。
- 修复托管 Docker 更新后运行日志不可见的问题，日志继续保存在共享数据目录。
- 改进自签 HTTPS 插件的设置提示，说明证书校验限制、插件连接方式和处理建议。

### Agent 与内容安全

- 合并 Agent 能力发现、整本资料册可见性、批量授权、暂停恢复和执行摘要能力。
- 修复公开内容中普通“secret / hidden / private”等词语被误判为私密标记的问题；仅显式的段落或行标记会触发私密内容检查。
- Agent 生成的世界、资料册和角色内容继续保持公开安全边界，冒险内容保留明确的 GM 标记规则。

### D&D 2024

- 接入起源专长“魔法学徒（Magic Initiate）”法术：背景戏法、一级法术、免费施法资源和角色中心展示。
- 增加并接入更多起源专长法术与戏法，包括 Shield、Chill Touch 等。
- Shield 反应在命中触发法术（例如 Divine Smite）之前结算；暴击仍保持暴击，AI 不会在无法改变结果时浪费 Shield。
- 修正 Chill Touch 的“无法恢复生命”持续到施法者下一回合结束。
- 修复 GM 复活角色后角色表与 D&D 战斗状态不同步的问题。

### TTS

- 将 `edge-tts` 最低版本提高到 7.3.1，并更新 Docker 与 Windows 便携版的 hash 锁定依赖。
- 修复微软接口要求 `Sec-MS-GEC` v2 后 Edge TTS 持续返回 HTTP 403 的问题。

### 文档

- 整理 README 中 Language maintenance 文档入口的位置。

### 升级说明

- 托管 Docker 用户会在更新后使用新的 Edge TTS 依赖。
- Windows 便携版会随本版本携带 `edge-tts` 7.3.1。
- 升级重要对局前仍建议备份完整的 `data/` 文件夹。

## English

DiceFrame 3.0.2 consolidates post-3.0.0 stability, deployment, Agent, D&D 2024, and TTS fixes.

### Stability and deployment

- Invalid independent check-model configuration now returns an actionable 409 business error instead of a raw HTTP 500 or false success.
- Add recovery paths for failed check-model operations and correct Bot-seat claiming boundaries.
- Restore runtime log visibility after managed Docker updates by keeping logs in the shared data directory.
- Improve self-signed HTTPS plugin guidance with a clearer settings dialog explaining certificate verification limits and recovery options.

### Agent and content safety

- Include Agent capability discovery, whole-book visibility controls, grouped authorization, paused execution recovery, and execution summaries.
- Fix false private-marker rejections when public content merely mentions words such as “secret”, “hidden”, or “private”; only explicit section or line markers trigger the private-content check.
- Keep public safety boundaries for Agent-generated worlds, lorebooks, and character content, while preserving explicit GM markers for adventures.

### D&D 2024

- Wire Origin Feat Magic Initiate spells into character and combat flows, including background cantrips, a level-one spell, free-cast resources, and character-center presentation.
- Add and connect more Origin Feat spells and cantrips, including Shield and Chill Touch.
- Resolve Shield reactions before hit-triggered spells such as Divine Smite; critical hits remain critical, and AI defenders do not waste Shield when it cannot change the result.
- Keep Chill Touch’s healing prevention until the end of the caster’s next turn.
- Synchronize the character sheet and D&D combat state after GM revival.

### TTS

- Raise the `edge-tts` minimum to 7.3.1 and update the hash-pinned Docker and Windows portable dependencies.
- Fix Edge TTS HTTP 403 failures after Microsoft’s endpoint began requiring `Sec-MS-GEC` v2 tokens.

### Documentation

- Reorganize the README entry for Language maintenance.

### Upgrade notes

- Managed Docker users receive the updated Edge TTS dependency with this update.
- The Windows portable build includes `edge-tts` 7.3.1.
- Back up the complete `data/` directory before upgrading important campaigns.

## Downloads

- **普通 Windows 用户**：`DiceFrame-v3.0.2-windows-portable.zip`
- **源码运行用户**：`DiceFrame-v3.0.2-windows.zip`
- **托管 Docker 更新**：`DiceFrame-v3.0.2-docker-update-linux-amd64.zip`
- Release 同时提供以上压缩包及 `SHA256SUMS` 校验文件。
