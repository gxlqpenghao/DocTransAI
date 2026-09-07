# v1 效率审计专项报告

日期：2026-09-07

## 审计范围

本专项基于 `high` 档，先核查当前服务线路，再验证已确认的图片输入冗余修正，并观察短 DOCX 的结果检查源页行为。没有跑大规模矩阵，没有改变全局默认档位。

当前 `.env` 的非敏感 endpoint 为 DashScope 兼容线路：

```text
https://dashscope.aliyuncs.com/compatible-mode/v1
model: kimi-k3
```

Kimi 原厂文档说明 K3 支持 `low/high/max`，但当前 DashScope 的 Kimi 托管线路文档注明 `kimi/kimi-k3` 的 `reasoning_effort` 只有 `max`。因此本项目收到并发送 `high`，不能仅凭请求成功或本地 `llm_settings` 证明服务端实际采用了 high；当前结论是“参数已发送、接口接受请求，但服务端生效状态未确认”。[Kimi 原厂模型选择](https://www.kimi.ai/help/kimi-api/api-model-selection) [阿里云 Kimi 托管线路说明](https://help.aliyun.com/en/model-studio/kimi-api-by-moonshot-ai)

## 已实施的确定性修正

`SourceView.initial_asset_refs()` 在存在主源引用时不再把其它图片补齐到上限；同范围图片匹配同时检查 `sheet_name`，而源文档本身已经限定了 `document_id`。未选图片仍留在 DataProxy 图片索引中，可通过 `view_source_asset` 按需读取。没有删除输出文件中的任何既有图片。

## 实际 high 对照

两次 XLSX 运行使用同一源、模板、source ref、指令和 `reasoning_effort=high`。第一行为图片修正前，第二行为图片范围修正后。

| 指标 | high 修正前 | high 图片范围修正后 | 变化 |
|---|---:|---:|---:|
| 总耗时 | 239.637 s | 207.680 s | -13.3% |
| 模型请求耗时 | 228.927 s | 196.721 s | -14.1% |
| 模型请求数 | 3 | 2 | -1 次 |
| 累计输入图片携带次数 | 45 | 12 | -73.3% |
| 图片 URL/Base64 字符数 | 14,941,415 | 3,117,100 | -79.1% |
| 总 prompt tokens | 248,096 | 124,034 | -50.0% |
| 其中 image tokens | 94,593 | 24,540 | -74.1% |
| thinking tokens | 4,228 | 5,007 | +18.4% |

这里的 45 和 12 是跨请求的图片携带次数，不是不同图片数量；图片字符数是请求中的 URL/Base64 字符量，也不是视觉 token。修正后总耗时和模型等待时间下降，同时 thinking tokens 反而上升，所以不能把收益归因为“思考强度下降”。更稳妥的解释是：输入体积减少、模型少做了一次 `inspect_document`，并叠加 K3 单次轨迹差异。

### 质量核对

修正后产物：[result.xlsx](/Users/paul/Coding/DocTransAI-document-tools/outputs/v1_efficiency_audit_20260907/xlsx_high_image_scoped/result.xlsx)。

- 输出保留模板既有第 1–3 条记录，并新增/填写第 4 条；没有因 source ref 清空既有内容。
- 3 张目标图片保留在第 4 条的 K6/T6/Y6；既有记录图片仍在原锚点。
- 当前工作表有 3 页输出，全部目检；无裁切、图片跨记录错配或中文丢失。
- ZIP 可打开，模板 SHA-256 未变；PDF 渲染嵌入 `MicrosoftYaHei`。
- 交付状态为 `completed / not_run`，本次模型未报告明确错误；数据保留仍以人工确认任务用途为准。

## DOCX 观察

当前 high DOCX 运行：[result.docx](/Users/paul/Coding/DocTransAI-document-tools/outputs/v1_efficiency_audit_20260907/docx_high_current/result.docx)。

- 4 次请求，总 227.441 s，模型 214.683 s；本地准备 4.940 s，自动渲染 4.976 s，工具 0.231 s。
- 初始请求直接提交编辑；自动预览后，结果检查只补读了若干原生块和第 4 页源页，随后做了一次图片/段落修正并再次自动预览。
- 最终 3 页全部目检，2 张隐患图片和说明保持对应，文件可打开，模板未变。
- 本轮没有做“检查阶段保留全部预准备源页”与“只保留文本/图片索引”的双跑 A/B；当前单次运行也没有再逐页读取 5 张源页，因此没有足够证据证明必须改变 DOCX 源页保留策略。该项暂不改生产默认。

## 效率结论

1. **已确认可简化：图片输入。** 主源明确时补齐无关图片是确定的代码冗余；收紧后在同一 high XLSX 任务上减少一次模型请求、约 13% 总耗时和约 74% image tokens，且本次质量未退步。
2. **尚未确认 high 的服务端生效。** 当前 DashScope 线路官方资料与 Kimi 原厂资料存在参数能力差异；本地客户端记录不能当作服务端回执。high 继续保持显式 opt-in，默认仍为 max。
3. **尚不能把耗时拆成“思考时间”。** 图片修正后总耗时下降，但 thinking tokens 上升；模型接口时间还包含排队、输入处理、网络和生成。需要同一线路下交错多次才可估计档位效果。
4. **DOCX 源页策略暂不改。** 本次 high 运行只触发单页补读，说明此前的逐页重复并非每次都会发生；增加源页图片可能减少工具调用，也可能扩大下一轮视觉输入，暂留 A/B 实验项。

## 后续建议

- 若要确认 `high` 是否被 DashScope 采用，应先查当前工作空间/模型参数文档或服务端请求日志，确认是否有明确的参数回显/能力字段；不能用单次速度反推。
- 下一轮只做小规模交错对照：相同输入交替运行 `max/high`，每档至少 3 次，记录中位数、范围、缓存命中、thinking tokens、输入/图片 tokens 和质量结果。
- 在得到 provider 能力确认前，不将 `high` 设为默认，不删除 `reasoning_content`，也不改 K3 工具消息协议。

## 本轮未做

没有重跑全量历史模型矩阵，没有修改默认档位，没有运行 DOCX 源页保留 A/B 双跑，没有进行新架构设计或独立语义复核。当前工作区代码改动待随本报告一起本地提交，不推送、不部署。
