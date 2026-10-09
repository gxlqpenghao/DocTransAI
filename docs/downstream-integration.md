# DocTransAI 1.1 项目接入与运行

DocTransAI安装在业务项目后端。DataProxy负责源文档解析、所属知识库入库及交付；DocTransAI调用自己的K3配置填写DOCX/XLSX模板。选择工作区不会把模型或转换程序放到集团服务器执行。

## 环境与交付

使用完整源码包，Python 3.12，执行 `uv sync --locked`。原有 `contracts/` 与 `src/` 必须同时保留。另需LibreOffice Writer/Calc、Poppler、中文字体、可工作的Codex `render_docx.py` 及其Python依赖 `pdf2image`。macOS遵循本机的中文字体修复与bundled renderer要求；Linux容器使用自身安装的办公运行库。保留 `kimi-k3/high` 默认配置。

仓库提供独立 `Dockerfile`，不依赖DataProxy镜像。构建 `docker build -t doctransai:1.1.0 .`，将可用的renderer目录只读挂载到 `/renderer`，工作目录挂载到 `/work`。配置通过受限权限的 `--env-file` 传入，不能写进镜像。

```bash
docker run --rm --env-file /secure/doctransai.env \
  -v /absolute/renderer-directory:/renderer:ro \
  -v /absolute/business-data:/work \
  doctransai:1.1.0 remote --mode zip \
  --source-file /work/source.docx --template /work/template.docx \
  --output-dir /work/runs/example \
  --instruction '依据源材料填写模板，缺少依据的内容留空。'
```

必要配置：

```dotenv
DOCTRANSAI_DATAPROXY_BASE_URL=https://dataproxy.gxlq.com.cn
DOCTRANSAI_DATAPROXY_API_KEY=<项目Key>
DOCTRANSAI_LLM_BASE_URL=<K3兼容接口基址>
DOCTRANSAI_LLM_API_KEY=<K3凭证>
DOCTRANSAI_LLM_REASONING_EFFORT=high
DOCTRANSAI_DOCX_RENDERER=/renderer/render_docx.py
DOCTRANSAI_RENDER_PYTHON=python
```

源码安装时显式导出环境变量；`--env-file` 是既有K3客户端的配置文件参数，不负责将整个文件加载进进程环境。Docker的 `--env-file` 会提供上述全部变量。项目Key不能放前端。运行自检包括 `doctransai --version`、`doctransai remote --help`，以及用真实中文模板运行renderer并检查PNG与PDF字体。

## ZIP方式

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
