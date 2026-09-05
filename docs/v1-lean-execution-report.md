# v1 精简流程真实 K3 对照报告

日期：2026-09-06  
分支：`codex/document-tools-refactor`  
代码基线：`ef78f21`  
模型：固定 `kimi-k3`，未启用独立语义复核  
最终提交：本报告随最终本地提交保存；用 `git -C /Users/paul/Coding/DocTransAI-document-tools rev-parse HEAD` 获取精确提交号。

## 结论

精简流程已经可用，但效率收益依赖模型轨迹，不能承诺固定低延迟。

- XLSX 任务达到了预期方向：从 5 次请求/703.231 秒降到修正版 2 次请求/320.731 秒，事实、图片归属和示例清理保持正确。
- DOCX 任务从 12 次请求降到 6 次，但总耗时从 507.065 秒升到 764.660 秒；K3 在两次结果检查中的思考耗时更长。请求数减少不等于端到端提速。
- 没有发现新的工程性重大阻塞。DOCX 的日期/人员角色仍有业务语义确认边界，XLSX 日期仍为字符串，这是已知 v1 限制。

## 实施内容

1. 程序准备初始上下文：短 DOC/DOCX/PDF 在文件大小和最多 6 页预算内预渲染源页；原生源图片按主源范围/锚点选择，其他图片保留按需读取；XLSX 模板首次上下文直接提供 used range 的准确地址视图。
2. 普通转换成功编辑后，程序自动真实渲染当前输出并把当前页交给下一次模型请求；finish 仍要求当前版本预览覆盖，超过自动附带页数时必须补读缺页。
3. 自动结果检查上下文保留源图片、当前文档版本、原模板结构和明确的缺页状态；提示词要求不重复请求已经附带的同一版本输出页。
4. 增加 prepare、auto_preview、模型输入图片/token、工具耗时等可观测字段；保留原子写入、失败草稿、模板保护和真实状态语义。
5. 针对已填 XLSX 模板增加通用契约：选定单条 source ref 时，模板已填记录默认为示例，不保留无来源示例值/图片；不按样本名、字段名或具体答案写规则。

## 真实固定 K3 结果

基线来自 `docs/v1-audit-evidence.json`；新结果来自 `outputs/v1_lean_20260906/`。所有命令均使用 `/Users/paul/Coding/DataProxy/.env`，凭证未打印。

| 任务 | 结果 | 总耗时 | 模型耗时 | 请求数 | 自动预览 | 定向回归后的质量结论 |
|---|---|---:|---:|---:|---:|---|
| DOC 通报 → DOCX 通知单 | `completed / not_run` | 764.660 s（基线 507.065 s） | 751.751 s | 6（基线 12） | 2 | 可读，2 条隐患/2 张照片保留；日期和角色仍需人工确认 |
| 已填 XLSX → 单条记录台账（首跑） | `completed / not_run` | 488.897 s | 479.010 s | 3 | 1 | 不接受：保留了 3 条模板示例记录及图片，证据保留在 `filled_xlsx/` |
| 已填 XLSX → 单条记录台账（契约修正版） | `completed / not_run` | 320.731 s（基线 703.231 s） | 311.472 s | 2 | 1 | 接受：仅序号 4，示例文字/图片清除，3 张图片锚定 K3/T3/Y3 |

### 可观测指标

| 任务 | prepare | auto render | tool | prompt tokens | thinking tokens | image tokens | 输入图片字符数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| DOCX 精简 | 4.821 s | 4.994 s | 0.427 s | 219,646 | 20,857 | 114,358 | 13,162,468 |
| XLSX 首跑 | 0.161 s | 4.902 s | 0.124 s | 256,077 | 11,987 | 94,593 | 15,042,871 |
| XLSX 修正版 | 0.161 s | 4.292 s | 0.074 s | 158,936 | 7,858 | 63,062 | 9,742,030 |

模型仍占主要耗时。XLSX 修正版由于编辑集中在首请求、自动预览后直接 finish，取得了真实端到端改善；DOCX 虽省掉逐页探索请求，但一次结果检查仍触发了源对象/源页补读，且 K3 思考更慢。

## 质量核对

### DOCX

产物：[outputs/v1_lean_20260906/notice_docx/result.docx](/Users/paul/Coding/DocTransAI-document-tools/outputs/v1_lean_20260906/notice_docx/result.docx)。

- 3 页最终输出全部目检；2 张隐患图片及说明保持图文对应，无裁切或中文消失。
- ZIP 校验通过，模板 SHA-256 未变，PDF 字体包含 `SimSun`/`NSimSun`/`FangSong_GB2312`。
- 业务语义边界未被精简流程掩盖：源通报日期被用于新通知单落款仍需人工确认；“落实整改管理人员/作业队负责人”与目标“整改监督人/整改负责人”的角色迁移仍需业务确认。没有将模型自检当作事实认证。

### XLSX 修正版

产物：[outputs/v1_lean_20260906/filled_xlsx_retry/result.xlsx](/Users/paul/Coding/DocTransAI-document-tools/outputs/v1_lean_20260906/filled_xlsx_retry/result.xlsx)。

- 3 页最终输出全部目检；只有目标序号 4 数据行，原示例行值与图片清除。
- 3 张图片锚定目标行的 K3/T3/Y3，数据、图片和跨页列可核对；ZIP 校验通过，模板 SHA-256 未变。
- N3/O3/R3/V3 仍是字符串日期，显示正确但不具备 Excel 日期运算语义；未按列名猜测改写。
- `result.xlsx` 的 21 个目标字段保持源记录内容，包括源文原样的“以整改”；抄送空值保持空白。

## 测试

```bash
.venv/bin/python -m pytest \
  tests/documents \
  tests/integration/test_document_tools.py \
  tests/integration/test_independent_review.py \
  tests/llm \
  tests/data_layer/test_bundle_reader.py -q
```

结果：`110 passed`。全库只做 collect-only：`484 tests collected`；未把 collect-only 当作通过，也没有重跑历史全量模型矩阵。`fix-libreoffice-cjk-fonts.py` 已执行，渲染使用 bundled `render_docx.py`。

## 运行与输出

普通命令仍为：

```bash
uv run doctransai convert \
  --bundle /data/parsed_document_bundle.json \
  --source-file /data/source.docx \
  --template /data/template.docx \
  --output-dir /data/runs/new-run \
  --instruction '依据该源材料填写模板；缺少依据的内容留空。' \
  --env-file /Users/paul/Coding/DataProxy/.env
```

每次使用新的 output directory。默认不启用独立复核；需要时使用 `--review` 或 `review` 命令。完整 trace、task、review 和页面缓存保留在 `outputs/v1_lean_20260906/`，未加入 Git。

## 剩余问题与结论

重大工程阻塞：未发现。模型语义误判风险仍然存在，尤其是新文书日期和人员职责角色；v1 不能无人值守签发。复杂格式、公式缓存计算、宏/透视表、进程重启恢复仍在既有支持边界外或有限支持。

本轮证明了“程序准备 + 自动预览”可以显著减少模型请求，且在 XLSX 主路径上实际提速；没有证明所有文档类型都端到端变快。当前版本可以作为可用、稳定且可审计的 v1 候选继续试用，业务人员仍须确认事实和职责角色。

仅回报执行结果，等待用户安排审计，不自动启动后续审计。
