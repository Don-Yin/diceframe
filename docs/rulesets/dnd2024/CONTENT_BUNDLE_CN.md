# Ruleset Bundle v1 内容包格式

Ruleset Bundle 是为第一方高级规则运行时提供的版本化、离线内容快照。它与社区 Plugin Content V2 目的不同：Plugin Content V2 用于通用资源贡献，Ruleset Bundle 则绑定一个已安装的权威规则运行时。

## 目录

```text
templates/rulesets/<directory_id>/
├─ manifest.json
├─ content/
│  └─ <organization>/*.json
├─ presets/
│  └─ <organization>/*.json
├─ locales/
│  └─ <locale>/<organization>/*.json
└─ legal/
   └─ ATTRIBUTION.md
```

`<directory_id>` 是本机稳定目录键，只允许小写 ASCII 字母、数字、点、下划线和短横线。加载器不接受绝对路径、`..` 或任意 manifest 入口路径。

## Manifest

```json
{
  "schema_version": 1,
  "bundle_id": "core:dnd2024-srd",
  "runtime_id": "core:dnd2024",
  "ruleset_version": "0.1.0",
  "content_version": "srd-5.2.1+r5",
  "default_locale": "zh-CN",
  "supported_locales": ["zh-CN", "en"],
  "license": {
    "id": "CC-BY-4.0",
    "attribution": "legal/ATTRIBUTION.md"
  }
}
```

- `bundle_id`：内容包 canonical ID。
- `runtime_id`：可解释该包的内建运行时。
- `ruleset_version`：体验和契约版本。
- `content_version`：规则数据快照版本，会写入高级规则存档。
- `license.attribution`：必须指向 bundle 内部的真实文件。

## Canonical Entity

```json
{
  "schema_version": 1,
  "kind": "ability",
  "id": "str",
  "source_ref": "srd-5.2.1:playing-the-game/the-six-abilities",
  "automation_level": "deterministic",
  "ordinal": 1
}
```

必填字段：

- `schema_version = 1`
- `kind`
- `id`
- `source_ref`
- `automation_level = deterministic | guided | reference`

`kind:id` 是 bundle 内部引用格式，例如 `ability:str`。所有以 `_ref` 结尾的字段必须是一个可解析内部引用；以 `_refs` 结尾的字段必须是内部引用数组。`source_ref` 是来源证据，不是内部引用。

`presets/` 与 `content/` 使用相同的 canonical entity 契约、引用检查和代码执行禁令。它只用于第一方构筑、队伍与通用战斗参考等不可执行预设；预设不能绕过 runtime 的最终合法性验证。剧情、场景、NPC、地图位置与冒险专属遭遇属于独立 Adventure Bundle，不得复制进 Ruleset Bundle。

## Locale Overlay

```json
{
  "locale_schema_version": 1,
  "locale": "zh-CN",
  "target": {"kind": "ability", "id": "str"},
  "fields": {
    "name": "力量",
    "description": "衡量身体力量与肌肉爆发力。"
  }
}
```

允许的 locale 顶层字段只有：

```text
name
description
summary
hint
recommendation_reason
tutorial
labels
text
```

Locale 不能覆盖数值、效果、选择、前置条件、动作资源或任何 mechanics。加载顺序为 canonical core -> default locale -> requested locale。如请求 locale 不受支持，回退到 default locale。

## Effect DSL

Content 不能执行代码。当前白名单原语：

```text
grant_proficiency
grant_language
grant_item
modify_ability
modify_derived_stat
add_resource
consume_resource
restore_resource
apply_condition
remove_condition
deal_damage
heal
force_save
make_attack
set_concentration
grant_action
grant_reaction
```

任意层级出现 `python`、`javascript`、`script`、`code`、`eval`、`module` 或 `callable` 键都会使整个 bundle 加载失败。未知 `op` 同样失败，不进行忽略或降级猜测。

## 失败策略

以下任一情况会拒绝整个 bundle：

- manifest 缺失或版本不受支持。
- 归属文件不在 bundle 内或不存在。
- 实体缺少来源或自动化等级。
- `kind:id` 重复。
- 内部引用无法解析。
- locale target 不存在或尝试修改 mechanics。
- 包含任意代码执行键或未知效果原语。

加载器不会跳过损坏文件后继续运行，也不会让 locale 失败时静默回到未本地化权威数据。
