# DocTransAI 1.0.0

正式版本入口：`codex/v1.0-release`，固定标签 `v1.0.0`。采用原可用流程与四项工具加固（基线 `453f913`），默认 `kimi-k3/high`；不包含后续三条候选提示词改写。下游请固定标签或提交，不再使用已结束的实验分支名。版本范围和验证说明见 [v1.0 定版说明](docs/v1.0-release.md)。

DocTransAI 是一个面向“文书成品”的模板驱动转换工具：读取 DataProxy 产出的结构化文档包，依据用户任务把有证据的事实写入 DOCX/XLSX 模板，并保留可追溯的运行报告、失败草稿和未决事项。

v1.0 的边界很明确：它是“可用、可核对、失败可恢复”的候选生成工具，不是无人值守的业务签发系统。模型自检、`model_passed` 或渲染成功都不等于业务事实已认证；日期、人员职责和文书角色仍必须由业务人员确认。

## 当前主流程

```text
DataProxy bundle + 源文件 + 模板 + 用户指令
              │
              ▼
程序准备材料：原生证据、主源引用、短源页面、相关图片、模板地址
              │
              ▼
固定 kimi-k3 集中提交 edit_document
              │
              ▼
程序自动真实渲染当前版本
              │
              ▼
kimi-k3 检查当前页：finish，或有限修正后再次自动渲染
              │
              ▼
result.docx / result.xlsx + review.json + trace.jsonl
```

独立语义复核默认关闭；需要时使用 `convert --review`、`review` 子命令或 `review_document()` API。普通路径的 2 次请求/修正 3 次是效率目标，不是强制上限，也不代表所有样本实绩。

## 代码结构

- `src/doctransai/conversion.py`：CLI/API 主入口、材料准备、输出状态和失败恢复。
- `src/doctransai/agent.py`：有界 K3 工具循环、自动预览和运行指标。
- `src/doctransai/data_layer/`：DataProxy bundle 读取与原生材料视图。
- `src/doctransai/documents/`：DOCX/XLSX 原子编辑、版本保护、图片/公式保护和预览。
- `src/doctransai/tools.py`：模型可见工具 schema 与确定性校验。
- `src/doctransai/review.py`：显式独立复核及有限、定位范围内修正。
- `src/doctransai/prompts/`：编辑与复核提示词。
- `scripts/`：仅保留仍有验证价值的辅助脚本；历史映射/渲染模块保留为兼容代码，不属于推荐主入口。

主路径不依赖旧 `SourceModel`、mapping planner、`RenderPlan` 或旧渲染流水线。它们仍保留，是为了不静默破坏历史测试和兼容调用；后续若要删除，需单独确认影响范围。

## 安装与配置

要求 Python 3.12、`uv` 和完整源码检出。当前不支持只安装 standalone wheel：`contracts/` 目录必须和 `src/` 一起存在。

```bash
uv sync --locked
cp .env.example .env
# 编辑 .env，填写 K3 endpoint 和本地渲染器路径
uv run doctransai --version
```

项目模型固定为 `kimi-k3`，不通过环境变量切换模型。K3 的思考强度支持 `low`、`high`、`max`，默认 `high`，不能关闭思考；可用 `--reasoning-effort high` 或 `DOCTRANSAI_LLM_REASONING_EFFORT=high` 调整。凭证只放在未跟踪的 `.env` 或外部环境变量中；不要把真实 key 写入命令、报告、trace 或 Git。

DOC/DOCX/PDF 源的页面预览需要可运行的 bundled `render_docx.py`；XLSX 源主要依赖 DataProxy 的 native range、sheet 和图片锚点。产品支持的输出是 DOCX 或 XLSX，不直接编辑 DOC/PDF 模板。

## 运行示例

普通转换：

```bash
uv run doctransai convert \
  --bundle /data/parsed_document_bundle.json \
  --source-file /data/source.docx \
  --template /data/template.docx \
  --output-dir /data/runs/example \
  --instruction '依据选定源材料填写模板；缺少依据的内容留空。' \
  --env-file /secure/path/provider.env
```

需要降低 K3 思考强度时，在上述命令中增加 `--reasoning-effort low` 或
`--reasoning-effort high`；降低档位可能减少延迟和 token 消耗，但复杂文档的
事实/版式判断可能退化。

选定主源对象时可重复使用 `--source-ref`：

```bash
uv run doctransai convert \
  --bundle /data/parsed_document_bundle.json \
  --source-file /data/source.xlsx \
  --template /data/ledger.xlsx \
  --source-ref record-or-range-ref \
  --output-dir /data/runs/ledger \
  --instruction '仅依据选定记录填写，未知内容保留并报告。' \
  --env-file /secure/path/provider.env
```

复核已有输出：

```bash
uv run doctransai review \
  --bundle /data/parsed_document_bundle.json \
  --source-file /data/source.docx \
  --template /data/original-template.docx \
  --document /data/existing-output.docx \
  --output-dir /data/runs/review \
  --instruction '检查当前输出；只有有明确依据的问题才修正。' \
  --env-file /secure/path/provider.env
```

每次使用新的 `--output-dir`。普通成功结果为 `result.docx`/`result.xlsx`；显式 review 的候选为 `candidate.docx`/`candidate.xlsx`。`review.json` 记录状态、哈希、页覆盖、指标和问题；`trace.jsonl` 记录模型和工具事件；编辑失败时保留 `working.*` 草稿并返回 `failed`，不会将失败标成成功。

## 工具边界

| 工具 | 作用 | 普通路径 |
|---|---|---|
| `read_source` | 读取 DataProxy 原生对象或搜索 | 按需调用；初始材料已先准备 |
| `view_source_page` | 查看源页并标记页码对应边界 | 长源文档或歧义时按需调用 |
| `view_source_asset` | 查看原生图片及归属上下文 | 未预附或需要复核图片时调用 |
| `inspect_document` | 查看模板/当前文档地址、范围、格式 | 初始结构已准备；复杂修改时调用 |
| `edit_document` | 版本化、原子批量编辑 | 由 K3 提交，程序校验地址、引用和格式 |
| `preview_document` | 查看模板或缺失输出页 | 普通编辑后由程序自动渲染；仅按需调用 |
| `finish` | 提交交付摘要和未决事项 | 只能在当前版本页面覆盖后成功 |

DOCX 支持文本范围/匹配替换、列表、段落组、表格行组和图片；XLSX 支持明确矩阵、公式保护、行复制、图片锚定、格式和打印范围。复杂浮动文本框、复杂嵌套表、宏、透视表、外部链接、复杂绘图、完整公式计算和进程重启恢复不在 v1 支持边界内。

当已填模板是否为示例、既有记录还是必须保留的业务数据无法从用户指令和模板语义确定时，系统应保留已有内容并报告歧义；不能仅凭 `source_refs` 自动清空。

## 测试

定向回归：

```bash
.venv/bin/python -m pytest \
  tests/documents \
  tests/integration/test_document_tools.py \
  tests/integration/test_independent_review.py \
  tests/llm \
  tests/data_layer/test_bundle_reader.py -q
```

本轮清理后的定向回归结果和本轮实际测试命令写入 `docs/v1-cleanup-report.md`。历史 K3 对照不等同于本轮新跑；最新效率证据在 `docs/v1-lean-execution-report.md`。

## 已知限制与 GitHub 上传前确认

- 固定 K3 的思考耗时有明显波动；DOC 实际请求数减少但端到端变慢，不能承诺稳定低延迟。
- XLSX 明确日期对象可以写成 Excel 日期；模型若提交普通字符串，v1 不按列名猜测改写。
- 源文书日期不能自动继承为新文书落款；人员角色相近也不能视为已证明对应。
- DataProxy 是输入边界；本项目不修改上游、不主动生成第二套材料模型。
- 完整源码目录安装已支持；standalone wheel 暂不支持。
- `V1文档审核集/`、历史报告和部分旧兼容代码仍在仓库中。它们是否可以公开到 GitHub 需要用户确认，当前不宣称样本、素材或报告具有公开许可。
- 上传前应重新检查跟踪文件中的样本、个人信息、许可和外部路径；本轮不会替用户改变许可或删除原始材料。

## DataProxy 正式解析包接入

支持外层 `parse_artifact`、内层 `data_asset_pack`，所有资源以 ZIP 根目录
`package_root` 为基准。旧 `data_asset_pack_v0` 本地 bundle 入口保留供历史任务使用；
这不代表 DataProxy 提供两套正式服务契约。

通过服务取得包（当前 DataProxy 对外 HTTPS 尚待部署验收）：

```bash
export DOCTRANSAI_DATAPROXY_BASE_URL='https://your-dataproxy-host'
export DOCTRANSAI_DATAPROXY_API_KEY='<项目密钥>'
uv run doctransai parse --source-file ./source.pdf --output-dir ./runs/parse-001
```

客户端仅允许 HTTPS 或本机回环 HTTP；不依赖 SSH。`parse-request.json` 在上传前保存
幂等键，并在取得任务后保存 job_id，不保存 API Key。失败后如需重新提交同一逻辑请求，
在新输出目录中用 `--idempotency-key` 复用原值；客户端不会自动重放上传。默认等待预算
900 秒，单次网络 I/O 超时最多 30 秒；下载最多 1 GiB，解压总大小最多 1 GiB、文件数最多 20000。
HTTP 错误、未知状态、任务失败、质量 failed 或哈希不符均停止。

消费已下载 ZIP、解压目录或 manifest：

```bash
uv run doctransai convert \
  --bundle ./runs/parse-001/package/manifest.json \
  --template ./template.docx \
  --output-dir ./runs/convert-001 \
  --instruction '依据材料填写模板，无依据内容留空，保留既有有效内容。' \
  --env-file ./provider.env
```

源文件可直接取包内副本，无需服务器路径。质量 degraded 的警告会进入模型材料及
转换报告；质量 failed 不进入填写流程。转换输出不代表上游解析或业务事实认证。

**2026-09-09 联调边界**：远端 `9ee3749` 的新 TXT 包通过外层、路径和哈希验证，
但 evidence_units 实际包含其正式 schema 禁止的字段，严格消费因此失败。
需 DataProxy 修正 schema/产物一致性后再做真实转换验收；没有为通过测试静默删字段或放宽校验。

### 原流程上的工具加固

保留原有会话、自动预览和完成检查流程，新增可选 DOCX `replace_ranges`：同段多个非重叠区间的坐标和样式索引取自该操作开始时的同一快照，避免前一处替换长度改变后续位置。旧批内操作仍按顺序执行，失败整批回滚。编辑回执包含输入/输出版本与回滚标记；段落视图提前说明整段替换保护；失败报告的 `last_preview` 保存最后预览版本、文件路径、页数及是否对应当前草稿。未知页数为 null。

这些是通用工具与可追溯性改进，不是已证实的速度优化。代表验证和保留范围见 `docs/v1-tool-hardening-20260910.md`。


### 默认模型档位与填写原则

普通编辑及其自检默认全程使用 `high`，不自动升级到 `max`，不增加复核调用。显式参数或环境配置仍可覆盖默认值；运行报告记录客户端实际配置。正式版恢复经前一轮六案例验证的原有编辑提示词，三条质量强化候选未采用。日期、角色、字段遗漏及图片说明等仍可能需要人工确认；客户端 high 不证明托管服务端内部采用了对应档位。
