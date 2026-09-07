# Kimi K3 `reasoning_effort=high` 试跑记录

日期：2026-09-07

## 调整内容

DocTransAI 已在 `DoctransaiLLMConfig`、`RuntimeConfig`、CLI 和 `/chat/completions` 请求中接入 K3 顶层参数 `reasoning_effort`。支持 `low`、`high`、`max`；默认仍为 `max`。本次使用：

```bash
uv run doctransai convert \
  --reasoning-effort high \
  --bundle /data/parsed_document_bundle.json \
  --source-file /data/source.xlsx \
  --template /data/template.xlsx \
  --output-dir /data/runs/reasoning-high \
  --instruction '依据选定源材料填写模板，未知内容保留并报告。' \
  --env-file /secure/path/provider.env
```

## 实际结果

使用与前次 max 语义验证相同的已填 XLSX 任务、源记录、模板和指令，未启用独立 review。

| 指标 | max 语义验证 | high 试跑 | 变化 |
|---|---:|---:|---:|
| 总耗时 | 343.027 s | 239.637 s | -30.1% |
| 模型请求耗时 | 333.399 s | 228.927 s | -31.3% |
| 模型请求数 | 3 | 3 | 不变 |
| thinking tokens | 8,556 | 4,228 | -50.6% |
| 输出结果 | 保留既有行并存在歧义 | 保留既有行并存在歧义 | 无数据误删 |

high 输出：[result.xlsx](/Users/paul/Coding/DocTransAI-document-tools/outputs/v1_reasoning_high_20260907/filled_xlsx/result.xlsx)。实际报告的 `llm_settings.reasoning_effort` 为 `high`。结果状态为 `completed / needs_review`，原因是既有模板第 1–3 条记录是否应保留存在歧义；这符合数据保护策略。输出保留第 1–3 条和新增第 4 条，图片锚点为 K3/T3/Y3，3 页均已目检，文件可打开。

## 解释与限制

这次在同一任务上 high 比 max 快约 30%，并且思考 token 减少；但只有一组任务、一次试跑，不能区分 K3 服务波动与档位效果，也不能推导所有 DOCX/XLSX 任务都会按相同比例提速。此前对照已经显示相同或近似首请求的 K3 思考耗时可能有较大波动。

high 可能降低复杂文档的事实、角色或版式判断质量；需要最高复杂任务质量时仍可使用 max。当前项目默认不改变，继续使用 max；只在 CLI/API/环境配置中显式选择 high 才生效。

定向回归和完整实现状态见：[v1-cleanup-report.md](/Users/paul/Coding/DocTransAI-document-tools/docs/v1-cleanup-report.md)。
