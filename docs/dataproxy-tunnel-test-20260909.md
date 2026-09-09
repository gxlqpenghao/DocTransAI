# Mac 经 SSH 隧道接入 DataProxy 测试

日期：2026-09-09。按用户要求，发现上游问题后停止，未进入 K3 填写或更改上游配置。

## 连接与部署核实

SSH 别名 windows-remote 已指向 Windows 主机 WIN-EFL8GF6COFJ / Administrator，地址 100.110.63.71。DataProxy 实际进程位于 DataProxy-Ubuntu WSL，工作目录 /home/gxlq/projects/DataProxy，远端 HEAD 3ff3870，包含 ebc961b9，工作树干净。Windows 的 127.0.0.1:8001 可转达 WSL 服务。E 盘为部署存储背景，实际程序访问使用 WSL 路径，未猜测 E 盘下的源码位置。

Mac 本机 127.0.0.1:18081 经 SSH 转发至 Windows 127.0.0.1:8001。独立隧道禁用连接复用后 health 返回 ok；产品客户端仍仅调用 HTTP。项目密钥在进程内获取，不输出、不落盘。SSH 隧道仅用于联调，不代表公网 HTTPS 验收。

## 结果

- 新建 TXT：实际上传、查询、下载通过。本地旧 schema 首次拒绝新增 schemas 字段，同步远端正式 schema 后严格验证通过；/opt/example/data 和 Windows 路径原文保留。
- 新建 XLSX：整个上传/等待/下载/严格读取约 13.09 秒，25 张资产均可解析到存在的文件。仅验证交付消费，没有宣称模型填写和视觉排版通过。
- 新建 DOC：任务 83ed48432f3749739c6e2c9138ff8009，status=succeeded、parse_quality=failed、artifact_available=true。warnings.parse_error 显示：

```
WordPdfRendererUnavailable: Microsoft Word is not available as a native Linux automation target. Set DATAPROXY_WORD_RENDERER_URL to a macOS/Windows Word renderer endpoint.
```

输入为既有 DOC 源样本《关于3月份安全生产大检查情况的通报.doc》。客户端拒绝失败质量包，未进入 K3。status=succeeded 表示打包任务结束，不是错误成功判定；质量 failed 在本次被正确拦截。failure_reason=null，具体原因位于 warnings.detail.error。

## 上游待处理

DataProxy 需要在其部署侧恢复/配置可用的 Word 渲染端点，并保证 API 与 worker 的实际运行环境读取该设置，再用同一 DOC 样本复验。本轮没有调查端点是否安装、运行、网络可达或配置丢失，不能进一步断言；不能让下游绕过 DataProxy 自行解析 DOC。未更改任何远端服务/配置，也没有重复提交失败任务。

## 本项目适配

同步新增 schemas 映射与 schema/data_assets 路径；新增 schema 资源纳入完整性检查。SourceView 支持正式 visual_asset_refs（旧历史 asset_refs 保持兼容）；相关图片预选、导航和简要证据视图同步。测试 fixture 更新到正式 schema 结构。

定向回归：tests/data_layer、tests/documents、tests/integration/test_document_tools.py、tests/integration/test_independent_review.py、tests/llm：126 passed。未执行全量模型矩阵、PDF 解析、真实 K3 填写或输出渲染。

本次本地产物：outputs/tunnel_integration_20260909/；DOC 上游状态保存在 doc-parse/upstream-status.json。未推送或部署 DocTransAI。
