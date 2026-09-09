# 正式解析包接入记录

基于 DataProxy 消费说明、parse_artifact_manifest.schema.json 和 data_assets schema 实现；正式契约快照来自本机 DataProxy release-prep/contracts，远端部署 9ee3749。新服务只有 parse_artifact/data_asset_pack 一套正式契约；本项目仍读取历史本地 v0 bundle。

## 已实现

- `doctransai parse`：项目密钥通过环境变量提供，HTTP 上传/有界轮询/下载，持久化幂等键与任务 ID，HTTP 或未知状态明确失败；保留上传重试控制，不自动重试产生不确定副作用的 POST。
- `convert --bundle` 支持 ZIP、解压目录、外层 manifest；安全解压、路径边界、文件大小/数量预算、SHA-256、外层及内层 schema、源文件和图片资源校验。
- 包内源文件和图片按 package_root 解析，不改写正文；质量 failed 拒绝，degraded 的完整警告进入报告和编辑模型上下文。
- 新 schema 作为 Python 包资源提供。原 v0 契约仍按原完整源码目录安装边界工作。

## 验证

定向命令：`.venv/bin/python -m pytest tests/data_layer tests/documents tests/integration/test_document_tools.py tests/integration/test_independent_review.py tests/llm -q`，125 passed。

覆盖正式包迁移读取、源文件保留、哈希破坏、ZIP/资源路径越界、失败质量、HTTP 模拟上传查询下载、幂等键和凭证不落盘、失败/未知状态，以及已有文档保护/复核回归。HTTP 客户端使用 MockTransport 验证，没有把 Mock 当公网验收。

## 真实上游阻塞

在 5080 回环服务实际上传合成 TXT，任务 b3515d05c1ec4df18bea3cf162a130d1，下载到 Mac `/tmp/doctransai-formal-package.zip`。验证外层契约/路径/哈希成功后，evidence_units[0] 被正式 schema 拒绝：

```
Additional properties are not allowed ('asset_refs', 'visual_quality_flags' were unexpected)
```

远端 `/home/gxlq/projects/DataProxy/contracts/data_assets/evidence_units.schema.json` 确认未定义这两个字段，且 additionalProperties=false；与本机用于适配的 schema 一致。服务却将该包标为 complete。包内只提供外层 manifest 和内层 bundle 索引 schema，没有组件行 schema；仅校验这两份 schema 不能发现组件行不一致。

应由 DataProxy 统一实际投影字段与规范 schema（字段确属公开契约则补足正确类型约束，否则修正生产侧输出），并在打包前验证实际交付的组件行。不要由下游删字段或关闭校验。此问题阻断严格正式消费；尚未进行真实 K3 输出生成，因此本报告不宣称全链路接通。

HTTPS/跨机器服务入口仍待上游部署。本次 SSH 仅用于运维验证和取样，不进入产品代码。未修改上游代码、未推送/部署。本地审计临时文件不作为公共样本提交。
