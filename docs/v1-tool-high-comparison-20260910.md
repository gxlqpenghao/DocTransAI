# 原流程工具加固版 high 与 max 单例对照

用户要求试中等思考。K3无独立medium档，本次明确按low/high/max中的中间档high测试。未修改默认max、业务代码、提示词、工具schema、输入材料和预算。

当前阿里云OpenAI兼容Chat参数文档已将kimi-k3（阿里云直供）列为max/high/low；kimi/kimi-k3（月之暗面直供）另列限制，不能混淆线路。参考：https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions 。Kimi原厂说明：https://www.kimi.ai/help/kimi-api/api-model-selection 。本项目调用模型名kimi-k3，实际传high请求成功；没有服务端独立档位回执，不把单次变化当严格因果。

同一台账第6行→通知单、冻结模板、原始DataProxy包。task.config差异仅reasoning_effort=max→high，prompt/tool指纹一致。各一次，无重跑。

| 指标 | max | high |
|---|---:|---:|
| 总秒数 | 550.478 | 172.615 |
| 模型秒数 | 542.064 | 165.809 |
| 模型请求数 | 3 | 3 |
| reasoning tokens | 12462 | 2908 |
| prompt tokens（含缓存） | 135160 | 127432 |
| image tokens | 36267 | 36267 |
| 页数 | 2 | 2 |

本次总耗时少68.6%，约3.19倍速度；推理token少76.7%。请求数和图片token相同，主要变化来自各轮模型生成长度与耗时，不是少检查一轮。但单次对照仍可能受缓存、服务波动和生成随机性影响，不保证其他文档同幅度提速。

两页成品已目检，ZIP/hash通过，模板不变。责任单位、隐患、整改要求、责任人及隐患图片对应正确；无编辑失败或恢复。质量退步：high把整改期限2026-05-17 20:00写成2026年5月17日前，丢失20时；max此项保留20时。high仍填写检查日期作为通知单落款，但没有像max那样报告该推定。故不能判定“速度和质量共同通过”，不自动改全局默认。

产物：outputs/v1-tool-high-20260910/runs/xlsx_row6_to_docx_notice/result.docx；对照max位于outputs/v1-tool-hardening-20260910。完整诊断均仅本地留存。未推送、未新增优化流程。
