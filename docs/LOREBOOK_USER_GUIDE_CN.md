# Lorebook v2 用户指南

世界书是提供给提示词的资料层：它描述可能相关的设定，不替代 WorldState 的当前事实。

导入流程是“选择文件 → 识别格式 → 预览 → 选择绑定范围 → 确认”。预览中的 warning 和
unsupported 字段不会被静默执行；未知扩展会作为数据保留。SillyTavern 的 timed 效果会提示
其 message-based 语义与 DiceFrame authoritative turn tick 的差异。

SillyTavern / Character Card 的条目正则是 JavaScript，而 DiceFrame 用 Python 正则执行，
因此只有安全子集会被执行：无法安全映射的 pattern 会在预览里给出 warning 并原样保留，
不会被改写，也不会被执行（表现为永不命中）。

导入角色卡时可选择是否一并导入内嵌的角色世界书。内嵌世界书走与其他导入完全相同的
canonical 路径，绑定优先使用 canonical 角色 uid，其次是当前世界；两者都没有时保持未绑定，
条目本身仍然完整导入。

Lorebook 页面左侧 Sidebar 可切换当前世界绑定的多本书；新增书、导入和编辑都会作用于
当前选中的 book，而不是强制写入 primary world book。导出使用 `lorebook_v3` 原生结构，
保留 book/entry 设置；后端也提供 `/api/lorebooks/{book_id}/entries` CRUD 与 export。

普通编辑只需填写名称、内容、关键词和可见范围；匹配、递归、概率、分组和 token budget
在高级设置中调整。新建条目默认 `priority` 100、`order` 100、`prompt_slot` 为
`world_background`、语义模式 `hybrid`；导入的条目保留其来源格式的默认值，不会被新默认值
覆盖。语义模式为 `off`、`hybrid`、`vector_only`，entry 覆盖 book 默认值。
玩家视角不会得到隐藏条目的名称、数量或诊断原因；GM 可通过 activation preview 查看
本轮 dry-run trace。
