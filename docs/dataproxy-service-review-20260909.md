# DataProxy 解析服务交付复核（2026-09-09）

范围：只读代码审计、一个新建合成 TXT 任务的实际 API 调用、临时目录中的打包函数故障复现。未修改远端服务代码或配置，未运行真实 LLM 转换，未复测全部格式、并发、隔离、重启或公网 HTTPS。

远端：windows-remote → DataProxy-Ubuntu，/home/gxlq/projects/DataProxy；提交 4b2f476，检查时工作树干净。实际 API 为 WSL 回环地址 http://127.0.0.1:8001；通过 SSH 运维访问测试，不代表公网调用已验收。密钥在远端进程内读取，没有输出或复制密钥。

## 实际通过

合成任务 d6f459dbcd1e4d7c94c7d98816b6eb7e：上传返回 202，同键同文件重试返回相同 job_id，同键不同文件返回 409，无凭证查询返回 401。任务 succeeded，parse_quality=complete，ZIP 下载 200（13278 字节）。ZIP 在 Mac /tmp/doctransai-remote-package-audit 解压后，manifest 文件清单 SHA-256 全部匹配，组件路径按包根目录解析全部存在。原文、章节、证据、组件索引等交付齐全；TXT 本身没有图表，未将空图表组件判作缺失。

## 必须修复

### P1：迁移路径会改写正文事实

src/dataproxy/parse_jobs/artifacts.py:326 的 _portable_value 递归处理所有字符串，365 行的绝对路径判断未限定为路径字段。直接调用该函数传入 source_text='/opt/example/data'，得到 source_text='external/data'；Windows 路径正文同样被更改。对于 source_ref 指向包外资源，external/... 也可能只是虚构引用，没有相应复制文件。

建议只处理明确契约规定的资源路径字段；正文和表格原值不变。包外必要资源应复制并映射，无法获取则明确 missing/warning 或失败，不能制造看似可用的引用。验收增加正文以 Linux/Windows 路径开头、表格单元格含路径、真实缺失资产的不同结构样本。

### P1：缺失交付组件仍可标 complete

artifacts.py:196 只根据 parse_errors 和 warnings 计算 quality_status，235 行计算 missing_components 时不会反向影响状态。用临时目录直接调用 materialize_parse_artifact，summary.document_count=1、files={}、parse_errors=[]，生成 quality.status=complete、complete=true，同时 missing_components=[text, sections, tables, images, provenance]。

建议打包完成后校验必要文件与引用，再统一计算质量状态。缺失必需文件不得 complete；空但合法的无表格/无图片组件不应误判。无法消费的核心交付缺失应失败，其余明确降级。

## 契约协调与消费端适配

外层 parse_artifact.v1 与内层 data_asset_pack 是两个契约版本。当前 DocTransAI 只支持 data_asset_pack_v0；正常读取实际新包报 BundleValidationError（版本不符）。诊断性关闭 schema 验证后仍失败：bundle 位于 content/parsed_document_bundle.json，但内部路径为 content/block_inventory.jsonl，现有读取器按 bundle.parent 拼成 content/content/block_inventory.jsonl。

新包采用包根目录基准本身可以成立，不应简单视为资源不存在。必须书面固定 manifest、bundle、JSONL 中资源路径的基准，显式提供 bundle 入口和内层契约/schema（目前包内仅有外层 manifest schema）。DocTransAI 增加显式包根目录和新版字段适配，保留旧本地 bundle 入口；不得靠猜父目录或关闭验证兼容。

## 其他建议

- 示例轮询脚本增加总超时、curl HTTP 失败检查、状态解析错误处理；现有 while true 在服务异常或未知状态时可能无限等待。
- 外部 HTTPS/项目间隔离、保留期 410、并发限制、重启恢复本轮未验收，不把回环 API 成功等同服务全面上线。
- 无需为了 DocTransAI 额外输出 document.md；现有结构化 evidence/block/section 满足架构方向。图片密集 DOCX/PDF/XLSX 应在修复后至少选一个新包复验引用完整性。

结论：交付形态符合所需，可开始对接契约设计；尚不应冻结为无问题稳定契约。先修复两项 P1，再明确路径/schema 规则，随后实施 DocTransAI 接入和代表性端到端联调。
