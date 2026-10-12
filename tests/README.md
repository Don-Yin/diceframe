# DiceFrame tests

测试保护用户可观察的契约和高风险边界，不是当前的类名、helper 或文件布局。

## 本地运行

后端测试不访问真实模型、Hub 或用户数据目录：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m pytest -q --cov=src --cov-report=term-missing
```

常用范围：

```bash
python -m pytest -q tests/integration/
python -m pytest -q tests/rulesets/
python -m pytest -q -k "permission or migration"
```

前端测试位于 `frontend-v2/tests`：

```bash
cd frontend-v2
npm ci
npm test
npm run typecheck
npm run lint
npm run build
```

Playwright 冒烟测试需要 Chromium，并由仓库脚本启动干净的临时数据环境：

```bash
npm run test:e2e:smoke
```

## 测试边界

必须持续覆盖：权限和私密数据隔离、存档迁移与回滚、多人并发隔离、余额和支付幂等、LLM authority 边界、插件和路径安全、token 泄露防护，以及升级完整性。

普通纯函数、低风险展示逻辑和已经由更高层契约覆盖的内部 helper 不需要单独堆测试。重构时可以移动、合并或删除重复测试，但不能用删除测试来隐藏行为回归。

测试应使用 `tmp_path`、fixture 和 fake 外部依赖。不得读取本机 `data/`、真实配置、真实凭据或联网服务。只有依赖本地未发布资源的测试才使用 `optional` 标记，并写明跳过原因。
