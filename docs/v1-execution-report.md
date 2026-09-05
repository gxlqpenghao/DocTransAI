# DocTransAI v1.0 候选执行报告

日期：2026-09-05  
版本：`1.0.0rc1`  
分支：`codex/document-tools-refactor`  
基线：`e3680db`  
最终提交：本文件随最终提交保存；用 `git -C /Users/paul/Coding/DocTransAI-document-tools rev-parse HEAD` 获取精确提交号。

## 结论

已形成可用、可审计的 v1.0 候选。普通转换默认采用 DataProxy 材料准备 → 一次有界编辑 → 真实输出预览/finish；独立语义复核保留为显式 `convert --review`、`review` 命令或 `review_document()` API。模型固定为 `kimi-k3`，DataProxy 仍是材料来源边界。

这不是业务事实的自动认证。模型自检和独立复核都只代表模型在有限材料/预算下的判断；候选输出仍需要业务确认。

## 本轮完成

- 默认 API/CLI 不再自动运行完整独立复核；`review` 和 `--review` 明确启用复核，`--skip-review` 保留兼容。
- finish 工具改为只要求摘要；未决问题和缺失事实可直接提交，旧 `checks` 字段可选且兼容字符串/数组，不作为证明。
- XLSX 默认结构视图改为 used-range 元数据和非空单元格/公式索引；显式 `s0!A1:D5` 检查仍返回完整空白地址、值和格式，且只读检查不扩展 used range。
- primary source refs 进入初始原生材料上下文并优先展示；其他材料仍可通过目录和 `read_source` 读取。
- XLSX 工具 schema 统一要求明确的 `sN!A1`/`sN!A1:D5` 地址；日期对象由工具写入并按日期/日期时间选择默认显示格式；打印区域不得隐藏既有内容或图片。
- 版本元数据、README、锁文件、运行报告和 CLI 帮助已收口；版本为 `1.0.0rc1`。
- 保留原子写入、版本检查、公式保护、模板哈希保护、失败草稿和真实页面覆盖检查；未删除旧链，遗留项作为技术债。

## 测试与样本证据

安装/版本：

```bash
cd /Users/paul/Coding/DocTransAI-document-tools
uv sync --locked --offline
.venv/bin/doctransai --version
```

结果：安装成功，输出 `doctransai 1.0.0rc1`。

定向回归：

```bash
.venv/bin/python -m pytest \
  tests/documents \
  tests/integration/test_document_tools.py \
  tests/integration/test_independent_review.py \
  tests/llm \
  tests/data_layer/test_bundle_reader.py -q
```

结果：`106 passed`。全库仅做 collect-only：`480 tests collected`；没有把 collect-only 当作通过，也没有重跑历史 29-case 模型矩阵。

真实候选文件核对：

- DOCX：`/Users/paul/Coding/DocTransAI-document-tools/outputs/k3_comparison_20260905/notice_compact/result.docx`。固定 K3 既有结果，3 页，2 张图；ZIP 可打开，问题文字和两条整改要求存在。
- XLSX：`/Users/paul/Coding/DocTransAI-document-tools/outputs/k3_comparison_20260905/ledger_compact/result.xlsx`。固定 K3 既有结果，3 页，1 条目标记录，3 张图；ZIP 可打开，公式数为 0，图片数为 3。
- 上述两个文件均用 bundled `render_docx.py` 重新渲染并目检全部 6 页。渲染页暂存于 `/tmp/doctransai-v1-qa.hKDiID/`；页面内容可读，图片未跨记录错配或丢失。
- 渲染 PDF 的 `pdffonts` 检查确认嵌入 `SimSun`/`NSimSun`/`MicrosoftYaHei` 等中文字体。
- 原模板未被覆盖；输出包 `ZipFile.testzip()` 均返回无错误。

样本结果边界：上述是真实固定 K3 结果的结构/视觉回归，不是本轮重新调用模型生成的新成功率结论。台账历史候选中的四个日期仍保存为字符串，显示正确但类型化不足，已作为 v1 已知限制记录；不通过列名猜测或全表复核强行改写。

## 运行命令

普通候选转换：

```bash
uv run doctransai convert \
  --bundle /data/parsed_document_bundle.json \
  --source-file /data/source.docx \
  --template /data/template.docx \
  --output-dir /data/runs/new-run \
  --instruction '依据该源材料填写模板；缺少依据的内容留空。' \
  --env-file /Users/paul/Coding/DataProxy/.env
```

显式独立复核：在 `convert` 后增加 `--review`，或运行：

```bash
uv run doctransai review \
  --bundle /data/parsed_document_bundle.json \
  --source-file /data/source.docx \
  --template /data/original-template.docx \
  --document /data/existing-output.docx \
  --output-dir /data/runs/review-run \
  --instruction '检查输出并只修正有明确依据的问题' \
  --env-file /Users/paul/Coding/DataProxy/.env
```

每次使用新的 output directory。凭证只通过 `--env-file` 或环境变量提供，不写入仓库；不推送、不部署、不公开发布。

## 已知限制

重大工程阻塞：本轮未发现。输出仍受模型语义波动影响，模型把源文书日期/角色迁移为新文书事实的风险不能由同模型复核完全消除；因此 `model_passed` 不是业务验收。

可跳过或已声明限制：

- XLSX 明确日期型输入可以写入 Excel 日期；模型若把日期作为普通字符串提交，v1 不按列名猜测并全表复核。
- 公式只做保护、相对引用平移和打开时重算，不提供完整 Excel 计算引擎或独立缓存值认证。
- 复杂 XLSX Table/条件格式/验证联动、宏、透视表、外部链接、复杂绘图形状会拒绝或需要额外适配。
- DOCX 浮动文本框、复杂嵌套表整体替换和进程重启恢复未纳入本轮；复杂排版可控失败并保留草稿。
- 暂未合并按页指纹复用、完整常规可观测性扩展、所有历史样本全通过等 P1 工作。

## 后续审计重点

请重点审计默认流程是否确实不启动独立复核、XLSX 空结构输入是否保持地址可读性、打印区域/公式/图片保护、失败状态与草稿路径，以及真实样本中的事实和角色歧义。结论仅为“达到可用稳定 v1 候选”，不等同于已通过后续业务审计。

本报告只回报本轮执行结果；等待用户安排审计，不自动启动审计。
