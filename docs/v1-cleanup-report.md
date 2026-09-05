# DocTransAI v1.0 清理与交付报告

日期：2026-09-06
基线：`0c19bb1`，分支：`codex/document-tools-refactor`
目标版本：`1.0.0`
最终提交：本报告随本轮本地提交保存；用 `git -C /Users/paul/Coding/DocTransAI-document-tools rev-parse HEAD` 获取精确提交号。

## 本轮结论

已完成 v1.0 清理交付，当前代码可安装、可运行、失败可识别，数据保留边界已修正。未 push、未创建远端仓库、未发布 release、未部署。

本轮没有继续做效率优化。上一轮的真实 K3 结果仍按历史事实保留：DOCX 请求数减少但端到端变慢；XLSX 修正版曾在“默认清理示例行”假设下提速。本轮已撤销该危险假设，因此上一轮 `filled_xlsx_retry` 不能被当作当前版本的通用清理保证。

## 数据保护修复

上一轮在 `conversion.py` 初始模板上下文和编辑提示词中加入了“有单条 `source_refs` 时，已填行默认为示例并清除”的假设。该条件不足以证明模板内容可以删除，已完成以下修复：

- 删除 `reference_snapshot["v1_template_contract"]` 的强制清理契约。
- 将提示词改为：仅当用户指令、模板契约或明确结构证据要求覆盖时才删除；无法判断时保留既有值/图片并报告歧义。
- 新增回归：主源 ref 存在时，若模型只显式填写新地址，其他既有 XLSX 内容仍保留。
- 用最终语义重新执行同一 XLSX 任务：输出保留原模板 1–3 行和图片，并新增序号 4 行；3 页全部目检。结果位于 `outputs/v1_cleanup_20260906/filled_xlsx_retention_retry/`。
- 一次错误 renderer 路径的验证被正确标记 `failed`、没有发布输出；修正为 bundled renderer 后才生成结果，失败证据保留在 `filled_xlsx_retention/`。

这意味着：当“示例记录”与“必须保留的既有业务记录”无法从任务和模板语义区分时，当前 v1 选择保留并要求人工确认，而不是追求单条输出的外观。

## 清理范围与依据

### 已删除

- `scripts/compare_k3_paths.py`：仅用于历史 K3 路径实验，无 CLI/package 入口，也没有生产代码导入；历史指标已保存在 `docs/k3-path-comparison.*` 和被忽略的本地输出目录。
- `scripts/probe_document_tools.py`：早期实验脚本，职责已迁入 `src/doctransai`，无当前支持入口或测试依赖。

### 保留

- `src/doctransai/agentic_mapping/`、`mapping/`、`source_model/`、旧 `renderers/`、旧 `templates/` 和旧 workflow：仍被历史测试或兼容工作流引用，直接删除会静默破坏现有支持面；本轮把它们明确视为 legacy，不作为 README 推荐主入口。
- `review.py` 和独立复核提示词：`review` CLI/API 仍是显式支持入口，不能静默删除。
- `contracts/`、DataProxy bundle 契约和 `V1文档审核集/`：保留原始材料和测试依据，不因清理方便销毁；公开许可和隐私范围留给 GitHub 上传前确认。
- `outputs/`、`artifacts/`、`tmp/`、`.env`：已由 `.gitignore` 排除；历史本地产物不进入提交。

### 配置与交付元数据

- `pyproject.toml`、`src/doctransai/__init__.py`、`uv.lock` 已统一为 `1.0.0`。
- 新增 `.env.example`，只含 K3 和本地 renderer 占位符，不含密钥或个人路径。
- `.gitignore` 已覆盖 `.env`、临时目录、输出、凭证命名文件和 `secrets/`。
- 上游兼容报告中的 DataProxy root/PYTHONPATH 提示已改为占位符，去除 `/Users/paul/...` 个人路径。
- 已扫描跟踪文件：未发现 `sk-`、私钥、Google key、GitHub token 等常见凭证模式；仍发现并处理了两处个人 DataProxy 路径，GitHub 上传前仍需人工确认样本与许可。

## 测试与安装

```bash
uv sync --locked --offline
.venv/bin/doctransai --version

.venv/bin/python -m pytest \
  tests/documents \
  tests/integration/test_document_tools.py \
  tests/integration/test_independent_review.py \
  tests/llm \
  tests/data_layer/test_bundle_reader.py -q

.venv/bin/python -m pytest --collect-only -q
```

结果：安装成功，CLI 输出 `doctransai 1.0.0`；定向回归 `111 passed`；全库仅 collect-only，`485 tests collected`。没有重跑全量历史 K3 矩阵。额外核对了失败状态、模板/图片/公式保护、数据保留回归、DOCX/XLSX ZIP 可打开和最终 XLSX retention 结果的 3 页视觉输出。

## 交付边界与待确认事项

- 推荐入口是 `uv sync --locked` + `uv run doctransai convert`；必须从完整源码检出运行，standalone wheel 尚不支持。
- 运行时固定 `kimi-k3`，DataProxy 是材料来源边界；不修改 DataProxy、不推送、不部署。
- `V1文档审核集/` 中包含真实/历史样本和模板，当前不声称具备公开许可；GitHub 上传前必须确认样本脱敏、版权、个人信息和报告公开范围。
- 历史兼容模块仍在仓库中，删除它们需要另行确认测试和用户调用影响；本轮不把“目录还存在”误称为主流程依赖。
- 语义日期、人员职责、复杂格式、公式缓存计算、宏/透视表和进程重启恢复仍是已知限制；不能无人值守签发。

本报告只回报清理与交付结果，等待用户安排审计，不自动启动下一轮审计或效率优化。
