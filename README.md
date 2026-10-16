# DocTransAI

DocTransAI将DataProxy解析的源材料，按业务要求填入DOCX或XLSX模板，并提供转换成品、字段审计和操作记录，供项目人员复核、修改与调试。

**当前版本：1.2.0。** 支持ZIP和任务工作区两种接入方式；LLM可配置，不再限定K3。默认模型仍为`kimi-k3`。本公开仓库提供源代码、合成测试和接入文档，不包含业务样本、内部验收材料或私有仓库历史。其他模型必须满足下述接口能力，并由接入项目用自己的材料验收。

## 1. 在业务项目中的位置

```text
业务前端：上传源材料、选择模板、填写要求、查看成品与审计
    ↓
业务后端：安装并调用DocTransAI，保存业务任务与用户权限
    ├─ 使用项目授权Key → 授权的DataProxy服务 → 解析、知识库入库、交付资料
    ├─ 使用LLM凭证 → 自选模型 → 模板填写与字段审计
    └─ 本地文档工具 → 编辑、渲染、核验 → 成品及报告
```

DataProxy统一管理源文档和解析资产，DocTransAI负责模板转换。DocTransAI运行在业务项目后端，无需在DataProxy服务器另建集中转换服务。业务项目负责登录、异步队列、业务任务状态、下载权限、成果保留和人工审批。

**两种凭证分别配置：**项目授权Key用于调用DataProxy；LLM API Key用于调用模型。两者仅保存在后端，不放在浏览器代码、URL、Git提交或公开日志中。

## 2. 安装与运行环境

使用Python **3.12**、`uv`和完整源码目录：

```bash
git clone https://github.com/gxlqpenghao/DocTransAI.git
cd DocTransAI
uv sync --locked
cp .env.example .env
uv run doctransai --version
```

当前交付以完整源码安装为准，保留`src/`和`contracts/`；不要只拷贝一个wheel或入口脚本。默认输出格式为DOCX/XLSX，旧DOC模板需先显式转换为DOCX。

文档预览还需要：

- 可运行的`render_docx.py`及其Python环境，包含`pdf2image`、Pillow等依赖。
- LibreOffice Writer/Calc、Poppler（`pdftoppm`、`pdfinfo`）和中文字体。
- 可用的模型网络连接；所选模型支持图片输入及函数工具调用。

用`DOCTRANSAI_DOCX_RENDERER`和`DOCTRANSAI_RENDER_PYTHON`指定renderer路径及解释器。可使用部署方提供的Codex bundled renderer；源码包不捆绑Codex运行时。应先拿一份中文模板实际渲染并检查PNG，不能只检查提取文本。macOS使用bundled renderer与可见的CJK字体；Linux容器需安装自己的办公运行库与字体。

独立运行镜像构建示例：

```bash
docker build -t doctransai:1.2.0 .
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  --env-file /secure/doctransai.env \
  -v /absolute/renderer-directory:/renderer:ro \
  -v /absolute/business-data:/work \
  doctransai:1.2.0 remote --mode zip \
  --source-file /work/source.docx --template /work/template.docx \
  --output-dir /work/runs/example \
  --instruction '依据源材料填写模板，缺少依据的内容留空并说明。'
```

Dockerfile安装办公工具、中文字体和renderer的`pdf2image`依赖。renderer目录需含`render_docx.py`；容器配置中的路径应使用容器路径，例如`/renderer/render_docx.py`和`python`。

## 3. 配置DataProxy授权与LLM

向服务管理员获取实际DataProxy地址与项目授权Key，下方域名为示例。公开仓库不提供服务访问权限。

开发人员取得分配给本业务项目的授权Key后，在后端`.env`中填写以下配置。仓库只提供占位符，不携带实际授权。

```dotenv
# DataProxy：管理员已将项目Key绑定到相应知识库
DOCTRANSAI_DATAPROXY_BASE_URL=https://dataproxy.example.com
DOCTRANSAI_DATAPROXY_API_KEY=<我们提供的项目授权Key>

# LLM：填写服务商的Chat Completions基址、Key和模型ID
DOCTRANSAI_LLM_BASE_URL=https://your-provider.example/v1
DOCTRANSAI_LLM_API_KEY=<你的LLM凭证>
DOCTRANSAI_LLM_MODEL=kimi-k3
DOCTRANSAI_LLM_MAX_TOKENS=16000
DOCTRANSAI_LLM_REASONING_EFFORT=auto
DOCTRANSAI_LLM_TIMEOUT_SECONDS=180
DOCTRANSAI_LLM_TOKEN_PARAMETER=max_tokens

# 本机的真实renderer路径和解释器
DOCTRANSAI_DOCX_RENDERER=/absolute/path/render_docx.py
DOCTRANSAI_RENDER_PYTHON=/absolute/path/python3
```

调用CLI时显式传`--env-file .env`，或设置`DOCTRANSAI_ENV_FILE`。**不会自动加载当前目录的`.env`。** Docker的`--env-file`会将配置注入环境，通常无需再给CLI传同名参数。

配置优先级：**显式CLI/Python参数 → 进程环境变量 → 指定配置文件 → 默认值**。配置文件按`KEY=value`读取，可有引号与`export`前缀，但不执行shell、不展开变量或命令。

DataProxy地址不含`/api`；知识库由授权Key决定，业务请求不传任意知识库ID。源文档上传到授权知识库后，管理员可按权限审阅解析任务和资产。

### 切换模型

设置`DOCTRANSAI_LLM_MODEL`或传`--model <服务商模型ID>`，无需修改代码。当前模型适配层使用`POST <基址>/chat/completions`、Bearer鉴权、SSE流式响应、图片消息和function tool calls。原生的其他API协议需要兼容网关或额外适配器。

- `reasoning-effort=auto`：K3使用`high`，其他模型不发送`reasoning_effort`。
- `reasoning-effort=omit`：不发送该字段，适用于不支持它的模型；它不表示服务端关闭思考。
- `none/low/medium/high/max`等值：按服务商支持情况显式配置，客户端原样发送。K3仍只接受`low/high/max`。
- 非K3模型默认不发送`temperature`；需要时设置数值。`temperature=omit`可显式省略。
- 服务商若要求`max_completion_tokens`，将`DOCTRANSAI_LLM_TOKEN_PARAMETER`或`--token-parameter`改为该值。
- 不支持流式usage选项的兼容网关，可设置`DOCTRANSAI_LLM_STREAM_USAGE=false`；缺失用量记录为未知，不当作零消耗。

模型可调用并不代表转换质量已验收。需要使用该模型检查真实模板的图片理解、工具调用、证据引用、分页及审计表现。当前真实公网业务验收基于K3；其他模型的本次验证是配置和请求契约测试。

## 4. 方式A：ZIP接入

如果希望通过本地网页上传文件和查看结果，可以直接运行：

```bash
uv run doctransai web --env-file .env
```

打开 `http://127.0.0.1:8765`，选择源文档和DOCX/XLSX模板后点击“开始转换”，无需填写提示词。页面采用一屏双面板；模型、token和思考开关直接显示在上传区下方，历史任务、诊断与审计在弹窗查看。固定填写规则维护在 `src/doctransai/prompts/document_editing_policy.md`，审计规则维护在 `src/doctransai/audit.py`。仅源文档提交给DataProxy，模板和密钥保留在本地后端。详见[本地测试页面说明](docs/local-test-ui.md)。

适合已有本地文件流水线或自有存储的业务后端。

```bash
uv run doctransai remote --env-file .env --mode zip \
  --source-file ./materials/source.docx \
  --request-id saved-upload-001 \
  --template ./templates/template.docx \
  --output-dir ./runs/zip-001 \
  --instruction '依据源文档填写模板，无依据的内容留空并在审计中说明。'
```

一次执行完成上传、轮询、ZIP下载与校验、真实模型转换和字段审计。ZIP方式不创建工作区，也不回传成品。每次使用新的输出目录；业务后端保存自己的业务任务ID和命令退出码。

同一个成功解析任务可直接复用，改用`--job-id <job_id>`代替`--source-file`，避免重复上传。`job_id`保存在输出目录的`integration.json`中。

## 5. 方式B：工作区接入

使用同一解析任务，无需再次解析：

```bash
uv run doctransai remote --env-file .env --mode workspace \
  --job-id <已有解析任务ID> --run-id saved-business-run-001 \
  --template ./templates/template.docx \
  --output-dir ./runs/workspace-001 \
  --instruction '依据源文档填写模板，无依据的内容留空并在审计中说明。'
```

也可以传`--source-file`新建解析任务。客户端通过HTTP分页与文件API读取工作区资料，在业务后端物化只读快照后执行转换。模型仍按现有材料选择机制消费资料；不把整个目录直接塞入模型。

成功后回写并读回核验：

```text
outputs/result.docx 或 result.xlsx
outputs/review.json
outputs/audit.json
outputs/audit.html
state/doctransai.json
```

随后导出`workspace-export.zip`并验证上述交付文件哈希。工作区不会代替业务后端执行模型或代码；工作区成果也不会自动进入知识库。

同一项目、job ID和run ID复用同一有效工作区。解析ZIP过期但已有工作区仍有效时，可以加`--workspace-id <ID>`直接读取快照。工作区有保留期与配额，默认7天保留期，以实际部署为准，应及时导出和备份。

## 6. 交付物与人工审查

```text
runs/<本次运行>/
├── integration.json              # 任务身份、质量、阶段、发布状态；不含Key
├── input/package/               # 校验后的源材料、原生证据及图片
├── conversion/
│   ├── result.docx 或 result.xlsx
│   ├── audit.html               # 可筛选的人工审查报告
│   ├── audit.json               # 机器可读字段审计
│   ├── review.json              # 执行、自检、警告、哈希与用量
│   ├── trace.jsonl              # 模型/工具事件、拒绝与回滚结果
│   ├── input.json              # 模板识别快照和初始材料
│   ├── audit-final-snapshot.json
│   └── previews/               # 渲染页面，用于核查版式
└── workspace-export.zip         # 仅工作区方式
```

业务页面可提供“下载成品”和“查看审计”。推荐先查看低确信度与未填项，再打开对应成品修改。

| 审计类别 | 含义 | 人工处理 |
| --- | --- | --- |
| `filled_high` | 已填入，模型认为源证据直接支持；程序另外核验引用和摘录 | 根据业务要求抽查、确认 |
| `filled_low` | 已填入，但有推断、识别疑点、引用摘录未核验等情况 | 阅读具体理由，核对源材料并修正 |
| `unfilled` | 未填、占位符未落实或相关位置被删除 | 查看缺少依据、歧义、不适用或失败原因 |
| `not_field` | 标题、标签或版式，不是实际填报位置 | 不计入未填写项，可检查识别是否合理 |

`audit.json`使用`schema_version: doctransai.audit.v1`。`fields[]`包含`field_id`、`location`、`field_label`、`before`、`after`、`category`、`reason`、`review_action`、`evidence`和`operation_ids`。`operations`与`activity_log`保留成功、拒绝和回滚记录；源证据与操作日志引用区分存储。DOCX使用节点及表格位置，XLSX使用工作表/单元格地址；DOCX的table/row/column索引从0开始。

**确信度不是统计概率，也不等于人工认证。** 写入成功、原生引用存在与内容真实正确分别记录。报告绑定`document_sha256`，成品被修改后原审计不能继续作为该新版本的有效审计。当前不提供在线人工修改审批系统，业务项目可在此JSON之上实现自己的复核流程。

`remote`默认完成语义审计后才交付。原`convert`/`review`入口先生成保守的`pending`台账，需额外运行：

```bash
uv run doctransai audit --env-file .env --run-dir ./runs/workspace-001/conversion
```

该命令核对已有成品，不重跑填写。对于人工修改过的成品，应先通过`review`形成绑定新哈希的新运行目录，再审计；不能直接沿用旧报告哈希。审计失败会明确标记`needs_manual_audit`，不会把未审部分标为高确信度。

## 7. 开发时可调参数

以下模型参数在`remote`、`convert`、`review`、`audit`命令均可使用。

| 参数/配置 | 作用 | 未配置时 |
| --- | --- | --- |
| `--model` / `DOCTRANSAI_LLM_MODEL` | 服务商模型ID | `kimi-k3` |
| `--max-output-tokens` / `DOCTRANSAI_LLM_MAX_TOKENS` | 每次请求的输出预算；部分模型将思考计入其中 | remote/audit 16000；convert/review 5000 |
| `--reasoning-effort` / `DOCTRANSAI_LLM_REASONING_EFFORT` | 思考强度或省略策略 | auto：K3 high，其他模型省略 |
| `--temperature` / `DOCTRANSAI_LLM_TEMPERATURE` | 采样温度或`omit` | K3 1.0，其他模型省略 |
| `--token-parameter` / `DOCTRANSAI_LLM_TOKEN_PARAMETER` | 输出预算的请求字段名 | `max_tokens` |
| `--llm-timeout-seconds` / `DOCTRANSAI_LLM_TIMEOUT_SECONDS` | 单次网络I/O等待上限，同时受阶段截止时间限制 | 180秒 |
| `DOCTRANSAI_LLM_STREAM_USAGE` | 是否发送流式usage选项 | true |
| `DOCTRANSAI_LLM_MAX_REQUEST_BYTES` | 单次模型请求体大小预算 | 6000000字节 |
| `DOCTRANSAI_LLM_MAX_INPUT_CHARS` | 单次输入字符预算，0表示不另设此限制 | 0 |

流程参数：

| CLI参数 | 所在命令 | 默认值与含义 |
| --- | --- | --- |
| `--max-steps` | remote/convert/review | 12，填写工具循环步数上限 |
| `--conversion-timeout` | remote | 900秒；填写阶段及后续审计分别使用该预算，不是整条链路总时限 |
| `--timeout-seconds` | remote | 1800秒，DataProxy阶段预算；发布重新开始独立预算 |
| `--timeout-seconds` | convert/review/audit | 900秒，对应转换/复核或审计阶段预算 |
| `--allow-degraded` | remote | 兼容旧命令；现在默认接受degraded，警告留在运行诊断 |
| `--review` | convert | 显式启用额外独立语义复核与有限修正，默认关闭 |
| `--review-max-steps` / `--repair-max-steps` | convert/review | 6 / 4 |
| `--max-repair-rounds` | convert/review | 1，范围0–2 |
| `--render-script` / `--render-python` | remote/convert/review | 覆盖renderer及解释器配置 |

例如调试另一个兼容模型：

```bash
uv run doctransai remote --env-file .env --mode zip \
  --job-id <job_id> --template ./templates/template.docx \
  --output-dir ./runs/model-comparison-001 \
  --model <模型ID> --reasoning-effort omit --temperature omit \
  --max-output-tokens 24000 --token-parameter max_completion_tokens \
  --conversion-timeout 1200 \
  --instruction '依据源文档填写模板；缺少依据的内容留空。'
```

`max_completion_tokens`只是配置示例，必须按实际服务商协议选择。不要把提高预算视作质量保证，也不要为不支持思考参数的模型强行发送该参数。

## 8. 后端Python集成

```python
from pathlib import Path
from doctransai.config import RuntimeConfig
from doctransai.settings import env_values, setting
from doctransai.upstream.dataproxy.workflow import run_remote

config_file = Path('/secure/doctransai.env')
values = env_values(config_file)
config = RuntimeConfig.from_environment(env_file=config_file,
    max_output_tokens=16000, max_steps=12, max_seconds=1200)

receipt = run_remote(
    base_url=setting('DOCTRANSAI_DATAPROXY_BASE_URL', values),
    api_key=setting('DOCTRANSAI_DATAPROXY_API_KEY', values),
    source=Path('/data/source.docx'),
    template=Path('/data/template.docx'),
    output_dir=Path('/data/runs/business-001'),
    instruction='依据源材料填写模板，缺失内容留空并说明。',
    config=config, mode='zip', request_id='saved-upload-001',
)
if receipt['status'] != 'completed':
    # 保留任务ID和所有报告，进入业务项目的失败/待人工处理流程。
    raise RuntimeError(receipt['status'])
```

`run_remote`是阻塞调用，适合放入业务后端的任务队列/Worker。工作区方式将`mode`改为`workspace`并传稳定`run_id`；复用解析结果时传`job_id`而不传`source`。

## 9. 错误、重试和保留

- 上传响应丢失：在新输出目录复用原`request_id`和同名同内容文件。不要立即换ID重复解析。
- 已知job ID：用`--job-id`恢复；客户端超时不会取消服务端任务。
- 质量`failed`、文件哈希/路径/schema错误：停止转换。`degraded`默认停止，只有明确业务策略允许后才放行。
- `finish_reason=length`：截断模型输出不会执行为工具调用。检查失败报告，明确调整输出预算后在新目录重试。
- 审计失败：保留成品及保守台账，状态为`audit_failed`；可单独运行audit，不必重新填写。
- 回写失败：用`remote --env-file .env --publish-receipt <integration.json>`恢复，避免重复模型费用。
- 重做审计后需要更新工作区：显式增加`--replace-audit`，以ETag仅更新审计文件；不同内容的成品仍禁止覆盖。
- 401/403检查授权和知识库绑定；409检查幂等或资源状态；410表示资源过期；413检查大小/配额；429由业务后端有界退避。412是版本冲突，重新读取后处理，不盲目覆盖。

工作区的只读资料不会被下游修改；成果和状态仅写入可写区域。ZIP本地副本和业务成品的访问控制、备份及清理由业务项目负责。

## 10. 验证与能力边界

本项目保留模板、来源、修改与渲染记录，但不是无人值守的业务签发系统。复杂浮动文本框、复杂嵌套表、宏、透视表、外部链接等不在完整支持范围；日期语义、角色归属、图片对应和模糊材料仍需人工检查。

```bash
uv run pytest tests/test_audit.py tests/upstream/test_service.py \
  tests/upstream/test_remote_workflow.py tests/data_layer \
  tests/integration/test_document_tools.py \
  tests/integration/test_independent_review.py tests/llm -q
```

公开代码基于1.2.0版本，提供136项定向回归测试（使用合成资料和模拟接口，不依赖业务样本）。内部运行记录不随公开仓库发布；接入方应使用自己的资料、授权服务和模型进行业务验收。详细流程见[接入说明](docs/downstream-integration.md)。
