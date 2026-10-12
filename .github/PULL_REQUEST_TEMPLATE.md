## Summary

<!-- 这次改动解决什么问题？描述行为，不需要复述所有文件。 -->

## Why

<!-- 为什么需要这样改？如果是明显 bug，可以很简短。 -->

## Impact

只勾选实际受影响的项目：

- [ ] API
- [ ] Persisted Data / Save / Database
- [ ] Migration
- [ ] Compatibility / Breaking Change
- [ ] Security / Permission / Privacy
- [ ] Multiplayer / Actor / Turn Authority
- [ ] Ruleset Mechanics
- [ ] Architecture / Dependency Boundary
- [ ] Plugin / Content / Extension Contract
- [ ] UI only

## Module / Boundary

<!--
这个变化主要属于哪个 feature / service / runtime / contract？
如果修改的是已知大型 orchestration / legacy hotspot：
- 这是原有职责内的小改动；
- 还是新增了一个独立职责？
- 如果暂时原地实现，原因是什么？
纯文档 / 样式小改可写 N/A。
-->

N/A

## Design / Migration Notes

<!--
普通 bug / 小功能可以写 N/A。

如果涉及架构变化，请简述 Current -> Proposed。
如果涉及 persisted data / breaking change，请说明 migration、compatibility、
version boundary 或明确的 rejection strategy。
-->

N/A

## Validation

<!-- 列出实际运行或新增的测试。不要写没有运行的测试。 -->

- [ ] Relevant backend tests
- [ ] Relevant frontend tests
- [ ] Build / typecheck where applicable
- [ ] Architecture / security checks where applicable
- [ ] Manual verification where meaningful

## Contract Check

- [ ] 用户数据不会被无意覆盖或丢失
- [ ] 权限 / private data 边界未退化
- [ ] 若改 persisted identity，已处理旧引用
- [ ] 若改关键产品契约，已更新对应测试（Critical testing areas 见 `docs/ENGINEERING_RULES.md` §15）
- [ ] 若架构事实发生变化，已更新 `docs/ARCHITECTURE_*.md`

<!-- 不适用的项可以保持未勾选；这个清单用于提示风险，不是要求每个 PR 全部勾满。 -->
