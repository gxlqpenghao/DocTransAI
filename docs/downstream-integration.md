# DocTransAI 项目接入与运行

当前1.2版本的配置、模型选择与完整示例以[README](../README.md)为准。

DocTransAI安装在业务项目后端。DataProxy负责源文档解析、所属知识库入库及交付；DocTransAI调用业务后端配置的LLM填写DOCX/XLSX模板。选择工作区不会把模型或转换程序放到DataProxy服务器执行。

## 环境与交付

使用完整源码包，Python 3.12，执行 `uv sync --locked`。原有 `contracts/` 与 `src/` 必须同时保留。另需LibreOffice Writer/Calc、Poppler、中文字体、可工作的Codex `render_docx.py` 及其Python依赖 `pdf2image`。macOS遵循本机的中文字体修复与bundled renderer要求；Linux容器使用自身安装的办公运行库。保留 `kimi-k3/high` 默认配置。

仓库提供独立 `Dockerfile`，不依赖DataProxy镜像。构建 `docker build -t doctransai:1.2.0 .`，将可用的renderer目录只读挂载到 `/renderer`，工作目录挂载到 `/work`。配置通过受限权限的 `--env-file` 传入，不能写进镜像。

```bash
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp --env-file /secure/doctransai.env \
  -v /absolute/renderer-directory:/renderer:ro \
  -v /absolute/business-data:/work \
  doctransai:1.2.0 remote --mode zip \
  --source-file /work/source.docx --template /work/template.docx \
  --output-dir /work/runs/example \
  --instruction '依据源材料填写模板，缺少依据的内容留空。'
```

必要配置：

```dotenv
DOCTRANSAI_DATAPROXY_BASE_URL=https://dataproxy.example.com
DOCTRANSAI_DATAPROXY_API_KEY=<项目Key>
DOCTRANSAI_LLM_BASE_URL=<Chat Completions兼容接口基址>
DOCTRANSAI_LLM_API_KEY=<LLM凭证>
DOCTRANSAI_LLM_MODEL=kimi-k3
DOCTRANSAI_LLM_REASONING_EFFORT=auto
DOCTRANSAI_DOCX_RENDERER=/renderer/render_docx.py
DOCTRANSAI_RENDER_PYTHON=python
```

源码安装时显式导出环境变量；1.2起，`--env-file` 同时读取DataProxy、LLM与渲染设置，但不修改进程全局环境。Docker的 `--env-file` 会提供上述全部变量。项目Key不能放前端。运行自检包括 `doctransai --version`、`doctransai remote --help`，以及用真实中文模板运行renderer并检查PNG与PDF字体。

## ZIP方式

服务迁移时，在后端配置中更新 `DOCTRANSAI_DATAPROXY_BASE_URL` 和 `DOCTRANSAI_DATAPROXY_API_KEY`，不要把地址或凭证写进前端。Base URL使用管理员最新文档提供的完整HTTPS地址，不追加 `/api`。可先携带项目Key请求 `GET /api/v1/knowledge` 验证绑定与限额；上游的检索能力入口是 `GET /api/v1/retrieval/capabilities`，但模板转换不要求发起检索或问答。

实际源文件上限同时受本地测试页100 MiB限制及知识库返回的 `limits.upload_bytes` 约束，服务端超限返回413。新版解析交付manifest允许 `authorization`（过滤说明、遗漏项目、授权版本）和 `source[].available`；客户端兼容这些声明，继续严格验证字段、路径及文件哈希。若明确标记原件不可用，转换会停止，不会忽略授权标记后使用本地同名文件。旧版未带这些可选字段的交付包仍可读取。

```bash
doctransai remote --mode zip \
  --source-file /work/source.docx --request-id saved-upload-id \
  --template /work/template.docx --output-dir /work/runs/zip-001 \
  --instruction '依据源文档填写模板，无依据的信息留空并说明。'
```

上传、轮询、下载、路径/哈希/schema校验和真实模型转换在一个命令中完成。此方式不创建工作区、不上传成品。输入保存在 `input/package/`，成品和报告在 `conversion/`。

## 工作区方式

```bash
doctransai remote --mode workspace \
  --job-id <同一个成功解析任务ID> --run-id saved-business-run-id \
  --template /work/template.docx --output-dir /work/runs/workspace-001 \
  --instruction '依据源文档填写模板，无依据的信息留空并说明。'
```

也可传 `--source-file` 新建解析任务。`--source-file` 与 `--job-id` 二选一。客户端创建或复用工作区，通过分页目录和文件读取API取得只读资料快照，逐文件校验SHA-256，再交给原转换内核。为了保留现有严格校验与本地办公工具，当前会物化完整只读快照，不宣称按模型请求懒加载；模型仍通过既有材料选择机制使用资料。

转换成功后上传 `outputs/result.docx` 或 `outputs/result.xlsx` 与 `outputs/review.json`，读回核对哈希，更新 `state/doctransai.json`，导出 `workspace-export.zip` 并核对成品。转换失败不会把草稿上传为成功成品。对已存在且内容不同的成果拒绝覆盖，要求新业务run ID；更新状态携带ETag。

## 字段审计交付

每次转换同时保存 `audit.json`、`audit.html`，包含模板定位、修改前后内容、来源引用、操作结果及失败/回滚记录。原 `convert` 先输出保守审计台账，状态为pending；`remote` 继续用独立上下文模型进行字段语义审计，再发布成品与报告。审计不是再次编辑文档，也不是完整业务签发。

实际填报位置按 `filled_high`（已填且高确信度）、`filled_low`（已填且低确信度）、`unfilled`（未填）分类；标题、标签、空白版式归 `not_field` 单独计数。模型必须覆盖全部候选位置，并给出字段名、理由、证据及人工核对建议。高确信度还需有可核验的原生引用和直接原文摘录；引用存在本身不能提升确信度。确信度是模型判断，不提供伪精确百分比。

审计JSON绑定成品SHA-256，成品修改后旧审计不再适用。审计失败时保留保守结果并标记 `needs_manual_audit`，remote返回 `audit_failed`，不会将其发布为完整交付。工作区额外保存 `outputs/audit.json`、`outputs/audit.html`；JSON保留完整识别快照和事件，HTML可筛选三类填报位置及非填报位置，方便定位审查。

已有成品可单独补审计，不重跑解析或填写：

```bash
doctransai audit --run-dir /work/runs/workspace-001/conversion
doctransai remote --publish-receipt /work/runs/workspace-001/integration.json
```

若重新生成的审计与工作区已有审计不同，显式增加 `--replace-audit`，仅允许以ETag更新两份审计文件，成品DOCX/XLSX仍禁止覆盖。文件读取请求identity编码，避免网关gzip将ETag弱化后导致If-Match更新失败。旧导出包保留为previous版本，新导出包重新校验全部交付文件。

语义审计有独立的模型调用与时间/输出预算。多页文档最多向审计模型提供前8页图片，所有候选字段仍须覆盖；超出单次审计文本预算时明确转人工，不把未审部分标为高确信度。XLSX审计以单元格地址定位、DOCX以稳定节点与表格位置定位。改行/增行等操作的完整原始记录始终保留。

## 质量、预算与恢复

默认只接受 `complete`；若业务允许，显式 `--allow-degraded` 接受降级解析。警告保存于 `integration.json`、原manifest和转换报告；`failed` 无法放行。接受degraded不代表图片或来源缺失已被修复。

`--timeout-seconds` 默认1800秒，是一次DataProxy阶段的客户端预算；`--conversion-timeout` 默认900秒，独立限制模型转换。客户端超时不取消服务端任务。单次HTTP I/O最多120秒，读取/下载时继续检查总预算。下载或只读快照最多1 GiB/20000文件；服务端可有更低的工作区限额（默认单文件64 MiB、工作区512 MiB），以实际部署为准。

新 `remote` 命令的 `--max-output-tokens` 默认16000，供K3思考与工具调用共享。原v1转换配置的5000上限在本轮真实表格文档中出现 `finish_reason=length`；此时程序拒绝执行截断调用，保留失败记录。业务项目可明确配置预算，预算增加不保证模型一定成功，客户端不自动无限重试。既有 `convert` 默认预算保持兼容；Python调用需通过 `RuntimeConfig(max_output_tokens=16000)` 显式选择。

`integration.json` 在上传前持久化request ID和业务run ID，取得响应后保存job ID、workspace ID、知识库文档ID、状态及质量。文件不保存API Key。每次使用新的本地输出目录：

- 上传响应丢失：同一文件、文件名、新输出目录、原 `--request-id` 重试。
- 已知job ID：使用 `--job-id` 继续等待/取得资料，无需重新上传。
- 工作区响应丢失：复用job ID及run ID；也可使用服务端列表接口恢复ID。
- 原解析ZIP已经过期但工作区仍有效：使用 `--mode workspace --job-id <ID> --workspace-id <已有工作区ID>`，不重新创建工作区。
- 模型已完成、回写失败：`doctransai remote --publish-receipt /work/runs/workspace-001/integration.json`，无需重复调用模型。该命令从本地成品恢复，不适用于修改过的成品。
- 429/临时服务错误：业务后端进行有界退避；本客户端不自动重放上传或写入。409表示身份、并发写入或资源状态冲突；410表示过期，应恢复自有备份或明确创建新任务。

原 `parse`、`convert`、`review` 命令保持兼容。Python接入使用 `doctransai.upstream.dataproxy.workflow.run_remote`；独立文件操作使用 `DataProxyClient`。

## 归属与保留

源文件、解析任务和知识库资产由DataProxy管理。ZIP模式的本地成果由业务项目管理。工作区成果是项目私有文件，不会自动成为知识库资产，也没有新增后台成果浏览页。默认解析ZIP和工作区均保留7天，应及时导出与备份。本地副本不受远程TTL影响。

模型完成、确定性工具验证、视觉检查与业务语义核对需分别记录；成品需要业务方签发确认。生产部署和接口兼容以实际验收记录为准。


## HTTP部署与上传响应恢复

默认要求HTTPS，仅本机HTTP免配置。部署方明确指定非本机HTTP时，在后端设置 `DOCTRANSAI_DATAPROXY_ALLOWED_HTTP_ORIGIN` 为与 Base URL 完全相同的origin（协议、主机、端口），不会放开其他地址，也不跟随重定向。HTTP会明文传输Key与文件，必须在已接受该条件的网络边界使用；配置值不放入前端。

上传发生网络超时/断开后，客户端保持原 `Idempotency-Key`，调用 `GET /api/v1/parse-jobs/by-idempotency-key` 找回任务。暂时404或短暂网络错误会进行有限次只读查询；找到编号立即保存回执，进入正常轮询。查询未找到时报告“上传结果尚未确认”，保留原键，不自动生成新键或重新上传。后续人工重试须使用同一文件与原键，或用已找回job_id继续。

找回任务不绕过解析质量检查：degraded仍需显式允许，默认停止转换，界面给出中文说明。审计和工作区发布使用同一后端HTTP允许配置。
