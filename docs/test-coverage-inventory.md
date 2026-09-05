# 已有测试与样本覆盖清单

清点日期：2026-09-05；分支：codex/document-tools-refactor；代码基线：40164d5。

本轮执行pytest收集、静态读取、历史报告及文件存在性/哈希检查，没有执行完整测试，没有调用模型，没有重新渲染历史文件。历史成功状态是原报告记录，不代表新支线已通过。

## 1. 数量与口径

- 57个测试文件，386个test函数，参数化展开后实际收集392项。收集退出码0；不能把collected写成passed。
- 5份执行manifest共37条记录，按case ID去重29个：基础14＋扩展12＋已填样例模板3。v1_cases的8个ID均在扩展基础矩阵中重复，配置版本可能不同。
- 另有15条候选配对建议，均可找到文件内容相同的执行配对，不能再相加算成44个新用例；文件相同不保证bundle、范围或运行参数相同。
- 配对涉及12个源文件路径（10种文件内容）和10个模板路径（7种文件内容）。整个审核集有29个DOC/DOCX/XLSX/PDF文件路径，按SHA-256去重为22种内容。
- 3个新路径实验是上述29个case的子集，不是新增3个case。当前没有probe_document_tools的专用pytest文件，临时工具专项检查尚未固化为仓库回归测试。

机器可读明细（包括全部392个node ID、每个case的manifest版本、实际文件路径和哈希）：[test-coverage-inventory.json](</Users/paul/Coding/DocTransAI-document-tools/docs/test-coverage-inventory.json>)。

## 2. 测试分组与迁移决策

| 测试组 | 文件数 | 收集项 | 处置 | 主要覆盖/迁移边界 | 阶段 |
| --- | ---: | ---: | --- | --- | --- |
| agentic_mapping | 10 | 85 | 拆分迁移 | 保留缺失、证据、图文行为；退出逐槽决策、组装和修复协议 | 1/2/4 |
| contracts | 2 | 7 | 旧协议退出 | 这里测试的是旧full_agent_context/RenderPlan，不是DataProxy契约 | 5 |
| data_layer | 1 | 6 | 保留 | 原生bundle、组件路径和契约错误 | 1 |
| formats | 1 | 3 | 简化迁移 | 保留格式识别和不支持错误，避免旧注册机制成为依赖 | 2/3 |
| ingestion | 2 | 2 | 边界复核 | 新项目消费DataProxy产物，不再维护第二套生成交付物管线 | 5 |
| integration | 6 | 17 | 迁移场景 | 保留源/模板和结果断言，改接正式工具入口与替身客户端 | 1—4 |
| llm | 1 | 12 | 保留并扩展 | 模型配置、请求预算、响应处理；补工具流与新配置键 | 1 |
| mapping | 12 | 94 | 拆分迁移 | 提取对象一致性与保守填写案例；候选排序、planner/resolver契约退出 | 2/4/5 |
| models | 1 | 2 | 旧协议退出 | 旧RenderPlan序列化；新操作结果只建立必要类型 | 5 |
| renderers | 5 | 49 | 迁移行为 | 保留图片、文字、版式断言；替换RenderPlan输入 | 2/3 |
| reports | 2 | 9 | 简化迁移 | 保留来源与问题分类，退出旧报表字段形状 | 4/5 |
| scripts | 1 | 4 | 迁移口径 | 源缺不等于故障、条件项不误报；不强制保留旧归因脚本 | 4 |
| source_model | 2 | 18 | 拆分迁移 | 保留原生定位、图文归属和范围；退出SourceModel/实例索引形状 | 1/2 |
| templates | 4 | 32 | 拆分迁移 | 保留结构/样例净化/物化；退出语义槽位硬约束 | 2/3 |
| upstream | 3 | 8 | 边界复核 | 保留不修改DataProxy等边界；主动调上游不是默认转换入口 | 1/5 |
| validation | 2 | 20 | 拆分迁移 | 保留输出完整性和输入缺口；删除旧状态/领域句式绑定 | 1/4 |
| workflows | 2 | 24 | 迁移场景 | 改接单一转换入口；保留执行失败、作用域与报告状态检查 | 1/4 |

处置是后续迁移建议，本轮不删除任何旧测试。“迁移行为”意味着保留业务与文档结果要求、替换调用入口和旧协议fixture，不要求新方案继续产生RenderPlan或候选包。

必须主动改写的旧通过标准：默认发送所有源页面；按首末同名标签猜定位；用相似度或全库补引用代表语义支持；固定逐槽唯一决策；旧PDF编辑目标。它们不应约束新路径。

## 3. 执行manifest与历史证据

| 清单 | 条目数 | 角色 |
| --- | ---: | --- |
| [v1_cases.json](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/05_样本配对_Manifest/v1_cases.json>) | 8 | 旧基础子集，8个重复ID |
| [v1_expanded_matrix.json](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/05_样本配对_Manifest/v1_expanded_matrix.json>) | 14 | 基础完整14组 |
| [v1_candidate_agent_observe_matrix.json](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/05_样本配对_Manifest/v1_candidate_agent_observe_matrix.json>) | 5 | 扩展5组 |
| [v1_candidate_agent_remaining_matrix_after_xlsx_fix.json](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/05_样本配对_Manifest/v1_candidate_agent_remaining_matrix_after_xlsx_fix.json>) | 7 | 扩展剩余7组 |
| [v1_sample_template_cases.json](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/05_样本配对_Manifest/v1_sample_template_cases.json>) | 3 | 已填样例模板3组 |

以下选择代表性已存在的历史批次，不穷举每次调试运行，也不将目录名current当作最新结果证明：

- [physical_acceptance_matrix_current](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/physical_acceptance_summary.json>)：`{"case_count": 14, "passed": 0, "review": 14, "failed": 0, "channel_issue_case_count": 0, "review_flag_case_count": 14}`。
- [2026-05-26_candidate_agent_observe_expanded_r2](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_observe_expanded_r2/summary.json>)：`{"total_case_count": 5, "executed_case_count": 5, "failed_case_count": 0, "skipped_disabled_count": 0, "skipped_status_count": 0}`。
- [2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/summary.json>)：`{"total_case_count": 7, "executed_case_count": 7, "failed_case_count": 0, "skipped_disabled_count": 0, "skipped_status_count": 0}`。
- [2026-05-26_sample_template_observe_agent_rerun3](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_sample_template_observe_agent_rerun3/summary.json>)：`{"total_case_count": 3, "executed_case_count": 3, "failed_case_count": 0, "skipped_disabled_count": 0, "skipped_status_count": 0}`。

基础14组历史批次：14组execution_status=ok，但artifact_status全为review，不能表述为14组内容通过。其余15组代表批次均记载executed与render_successful=true，且输出文件存在，但仍有未填项/警告。

已有unresolved数量仅原样记录，不用它直接计算失败率：源缺、人工项、语义不支持、通道错误需要分别核对。manifest中的ready/observe也是运行分组，不是验收结论。

## 4. 全部29个执行用例

原始材料和模板链接指向新工作区；历史结果链接仍指向原工作区。每个编号对应一个case ID，便于下节安排回归。

### 基础14组

| 编号/Case ID | 源 → 模板 | 历史结果 | 新工具路径 | 首次纳入阶段 |
| --- | --- | --- | --- | --- |
| 01<br>`xlsx_row6_to_docx_record` | [01_结构化台账源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/01_结构化台账源/安全检查台账.xlsx>) → [01_DOCX整改记录单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/01_DOCX整改记录单/安全隐患整改记录单.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/xlsx_row6_to_docx_record.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/xlsx_row6_to_docx_record.agentic_report.json>)<br>ok / review；文字15, 图2, 未解决9 | [新实验](</Users/paul/Coding/DocTransAI/outputs/document_tools_probe_20260905/xlsx_row6_to_docx_record/result.docx>)；2页3图，已核对关键事实与锚点 | 1→2 |
| 02<br>`xlsx_row6_to_docx_notice` | [01_结构化台账源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/01_结构化台账源/安全检查台账.xlsx>) → [02_DOCX整改通知单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/02_DOCX整改通知单/安全隐患整改通单（项目）.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/xlsx_row6_to_docx_notice.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/xlsx_row6_to_docx_notice.agentic_report.json>)<br>ok / review；文字11, 图1, 未解决4 | 尚未在新路径验证 | 2 |
| 03<br>`xlsx_row6_to_docx_penalty` | [01_结构化台账源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/01_结构化台账源/安全检查台账.xlsx>) → [03_DOCX处罚通知单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/03_DOCX处罚通知单/质量安全检查处罚通知单（分公司）.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/xlsx_row6_to_docx_penalty.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/xlsx_row6_to_docx_penalty.agentic_report.json>)<br>ok / review；文字4, 图1, 未解决10 | 尚未在新路径验证 | 2 |
| 04<br>`xlsx_row6_to_xlsx_register` | [01_结构化台账源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/01_结构化台账源/安全检查台账.xlsx>) → [04_XLSX台账模板](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/04_XLSX台账模板/安全检查台账模版.xlsx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/xlsx_row6_to_xlsx_register.xlsx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/xlsx_row6_to_xlsx_register.agentic_report.json>)<br>ok / review；文字18, 图2, 未解决5 | 尚未在新路径验证 | 3 |
| 05<br>`word_table_to_docx_record` | [02_Word表格源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/02_Word表格源/环资公司安全检查记录表（2022.3.7 核心区纵二路东段、纵三路）.docx>) → [01_DOCX整改记录单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/01_DOCX整改记录单/安全隐患整改记录单.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/word_table_to_docx_record.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/word_table_to_docx_record.agentic_report.json>)<br>ok / review；文字12, 图0, 未解决14 | 尚未在新路径验证 | 2 |
| 06<br>`word_list_to_docx_notice` | [03_Word正文列表源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/03_Word正文列表源/关于3月份安全生产大检查情况的通报.doc>) → [02_DOCX整改通知单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/02_DOCX整改通知单/安全隐患整改通单（项目）.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/word_list_to_docx_notice.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/word_list_to_docx_notice.agentic_report.json>)<br>ok / review；文字11, 图0, 未解决5 | [新实验](</Users/paul/Coding/DocTransAI/outputs/document_tools_probe_20260905/word_list_to_docx_notice/result.docx>)；2页2图，外部语义复核后修正 | 1→2 |
| 07<br>`complex_docx_to_docx_record` | [04_复杂检查记录源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/04_复杂检查记录源/附件1：广西路桥工程集团有限公司市政分公司2022年第一季度安全标准化检查记录表.docx>) → [01_DOCX整改记录单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/01_DOCX整改记录单/安全隐患整改记录单.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/complex_docx_to_docx_record.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/complex_docx_to_docx_record.agentic_report.json>)<br>ok / review；文字2, 图0, 未解决24 | 尚未在新路径验证 | 2 |
| 08<br>`scitech_pdf_to_docx_innovation_form_agent` | [05_科技成果长文档PDF源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/05_科技成果长文档PDF源/工程建设科学技术进步奖提名书-AI-数理双驱动的隧道地质信息融合解译与风险评估关键技术.pdf>) → [05_DOC科技创新成果信息表](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/05_DOC科技创新成果信息表/附件 广西住房城乡建设领域科技创新成果信息表.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/scitech_pdf_to_docx_innovation_form_agent.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/scitech_pdf_to_docx_innovation_form_agent.agentic_report.json>)<br>ok / review；文字12, 图0, 未解决3 | [新实验](</Users/paul/Coding/DocTransAI/outputs/document_tools_probe_20260905/scitech_pdf_to_docx_innovation_form_agent/result.docx>)；4页，流式/分批后完成；仍有业务口径待确认 | 1→2 |
| 09<br>`word_table_to_docx_notice` | [02_Word表格源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/02_Word表格源/环资公司安全检查记录表（2022.3.7 核心区纵二路东段、纵三路）.docx>) → [02_DOCX整改通知单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/02_DOCX整改通知单/安全隐患整改通单（项目）.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/word_table_to_docx_notice.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/word_table_to_docx_notice.agentic_report.json>)<br>ok / review；文字10, 图0, 未解决4 | 尚未在新路径验证 | 2 |
| 10<br>`word_table_to_docx_penalty` | [02_Word表格源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/02_Word表格源/环资公司安全检查记录表（2022.3.7 核心区纵二路东段、纵三路）.docx>) → [03_DOCX处罚通知单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/03_DOCX处罚通知单/质量安全检查处罚通知单（分公司）.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/word_table_to_docx_penalty.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/word_table_to_docx_penalty.agentic_report.json>)<br>ok / review；文字6, 图0, 未解决10 | 尚未在新路径验证 | 2 |
| 11<br>`word_list_to_docx_record` | [03_Word正文列表源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/03_Word正文列表源/关于3月份安全生产大检查情况的通报.doc>) → [01_DOCX整改记录单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/01_DOCX整改记录单/安全隐患整改记录单.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/word_list_to_docx_record.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/word_list_to_docx_record.agentic_report.json>)<br>ok / review；文字12, 图0, 未解决14 | 尚未在新路径验证 | 2 |
| 12<br>`word_list_to_docx_penalty` | [03_Word正文列表源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/03_Word正文列表源/关于3月份安全生产大检查情况的通报.doc>) → [03_DOCX处罚通知单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/03_DOCX处罚通知单/质量安全检查处罚通知单（分公司）.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/word_list_to_docx_penalty.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/word_list_to_docx_penalty.agentic_report.json>)<br>ok / review；文字4, 图1, 未解决10 | 尚未在新路径验证 | 2 |
| 13<br>`complex_docx_to_docx_notice` | [04_复杂检查记录源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/04_复杂检查记录源/附件1：广西路桥工程集团有限公司市政分公司2022年第一季度安全标准化检查记录表.docx>) → [02_DOCX整改通知单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/02_DOCX整改通知单/安全隐患整改通单（项目）.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/complex_docx_to_docx_notice.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/complex_docx_to_docx_notice.agentic_report.json>)<br>ok / review；文字2, 图0, 未解决14 | 尚未在新路径验证 | 2 |
| 14<br>`complex_docx_to_docx_penalty` | [04_复杂检查记录源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/04_复杂检查记录源/附件1：广西路桥工程集团有限公司市政分公司2022年第一季度安全标准化检查记录表.docx>) → [03_DOCX处罚通知单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/03_DOCX处罚通知单/质量安全检查处罚通知单（分公司）.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/complex_docx_to_docx_penalty.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/agentic_skeleton/physical_acceptance_matrix_current/artifacts/complex_docx_to_docx_penalty.agentic_report.json>)<br>ok / review；文字0, 图0, 未解决15 | 尚未在新路径验证 | 2 |

### 扩展5组

| 编号/Case ID | 源 → 模板 | 历史结果 | 新工具路径 | 首次纳入阶段 |
| --- | --- | --- | --- | --- |
| 15<br>`candidate_s01_winter_to_record_agent` | [S01_DOCX冬季专项检查通报](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S01_DOCX冬季专项检查通报/关于11月份冬季施工专项检查情况的通报.docx>) → [T01_DOCX安全隐患整改记录单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T01_DOCX安全隐患整改记录单/安全隐患整改记录单.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_observe_expanded_r2/cases/candidate_s01_winter_to_record_agent/安全隐患整改记录单.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_observe_expanded_r2/cases/candidate_s01_winter_to_record_agent/安全隐患整改记录单.conversion_report.json>)<br>executed / render=true；文字16, 图1, 未解决8 | 尚未在新路径验证 | 2 |
| 16<br>`candidate_s01_winter_to_notice_agent` | [S01_DOCX冬季专项检查通报](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S01_DOCX冬季专项检查通报/关于11月份冬季施工专项检查情况的通报.docx>) → [T02_DOCX安全隐患整改通知单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T02_DOCX安全隐患整改通知单/安全隐患整改通单（项目）.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_observe_expanded_r2/cases/candidate_s01_winter_to_notice_agent/安全隐患整改通单（项目）.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_observe_expanded_r2/cases/candidate_s01_winter_to_notice_agent/安全隐患整改通单（项目）.conversion_report.json>)<br>executed / render=true；文字7, 图1, 未解决5 | 尚未在新路径验证 | 2 |
| 17<br>`candidate_s03_long_report_to_record_agent` | [S03_DOCX第三方巡查长报告](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S03_DOCX第三方巡查长报告/第三方检查-柳东新区官塘片曙光大道（雒容段）工程第三方巡查评估报告 202205031.docx>) → [T01_DOCX安全隐患整改记录单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T01_DOCX安全隐患整改记录单/安全隐患整改记录单.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_observe_expanded_r2/cases/candidate_s03_long_report_to_record_agent/安全隐患整改记录单.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_observe_expanded_r2/cases/candidate_s03_long_report_to_record_agent/安全隐患整改记录单.conversion_report.json>)<br>executed / render=true；文字7, 图1, 未解决17 | 尚未在新路径验证 | 2 |
| 18<br>`candidate_s04_pdf_order_to_reply_doc_agent` | [S04_PDF集团年中整改单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S04_PDF集团年中整改单/整改单.pdf>) → [T05_DOC安全质量问题整改回复单模板](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T05_DOC安全质量问题整改回复单模板/安全质量问题整改回复单模板.doc>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_observe_expanded_r2/cases/candidate_s04_pdf_order_to_reply_doc_agent/安全质量问题整改回复单模板.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_observe_expanded_r2/cases/candidate_s04_pdf_order_to_reply_doc_agent/安全质量问题整改回复单模板.conversion_report.json>)<br>executed / render=true；文字5, 图13, 未解决6 | 尚未在新路径验证 | 2；先物化DOC并验证样例清理 |
| 19<br>`candidate_s07_check_record_to_notice_agent` | [S07_DOCX项目安全环保检查记录](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S07_DOCX项目安全环保检查记录/安全环保检查记录表.docx>) → [T02_DOCX安全隐患整改通知单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T02_DOCX安全隐患整改通知单/安全隐患整改通单（项目）.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_observe_expanded_r2/cases/candidate_s07_check_record_to_notice_agent/安全隐患整改通单（项目）.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_observe_expanded_r2/cases/candidate_s07_check_record_to_notice_agent/安全隐患整改通单（项目）.conversion_report.json>)<br>executed / render=true；文字6, 图0, 未解决7 | 尚未在新路径验证 | 2 |

### 扩展7组

| 编号/Case ID | 源 → 模板 | 历史结果 | 新工具路径 | 首次纳入阶段 |
| --- | --- | --- | --- | --- |
| 20<br>`candidate_s01_winter_to_penalty_agent` | [S01_DOCX冬季专项检查通报](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S01_DOCX冬季专项检查通报/关于11月份冬季施工专项检查情况的通报.docx>) → [T03_DOCX质量安全检查处罚通知单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T03_DOCX质量安全检查处罚通知单/质量安全检查处罚通知单（分公司）.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s01_winter_to_penalty_agent/质量安全检查处罚通知单（分公司）.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s01_winter_to_penalty_agent/质量安全检查处罚通知单（分公司）.conversion_report.json>)<br>executed / render=true；文字1, 图1, 未解决6 | 尚未在新路径验证 | 2 |
| 21<br>`candidate_s02_supervisor_to_record_agent` | [S02_DOC监理通知图文源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S02_DOC监理通知图文源/监理通知单010.doc>) → [T01_DOCX安全隐患整改记录单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T01_DOCX安全隐患整改记录单/安全隐患整改记录单.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s02_supervisor_to_record_agent/安全隐患整改记录单.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s02_supervisor_to_record_agent/安全隐患整改记录单.conversion_report.json>)<br>executed / render=true；文字9, 图1, 未解决15 | 尚未在新路径验证 | 2 |
| 22<br>`candidate_s02_supervisor_to_penalty_agent` | [S02_DOC监理通知图文源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S02_DOC监理通知图文源/监理通知单010.doc>) → [T03_DOCX质量安全检查处罚通知单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T03_DOCX质量安全检查处罚通知单/质量安全检查处罚通知单（分公司）.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s02_supervisor_to_penalty_agent/质量安全检查处罚通知单（分公司）.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s02_supervisor_to_penalty_agent/质量安全检查处罚通知单（分公司）.conversion_report.json>)<br>executed / render=true；文字3, 图1, 未解决4 | 尚未在新路径验证 | 2 |
| 23<br>`candidate_s03_long_report_to_ledger_agent` | [S03_DOCX第三方巡查长报告](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S03_DOCX第三方巡查长报告/第三方检查-柳东新区官塘片曙光大道（雒容段）工程第三方巡查评估报告 202205031.docx>) → [T04_XLSX安全检查台账模板](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T04_XLSX安全检查台账模板/安全检查台账模版.xlsx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s03_long_report_to_ledger_agent/安全检查台账模版.xlsx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s03_long_report_to_ledger_agent/安全检查台账模版.conversion_report.json>)<br>executed / render=true；文字8, 图1, 未解决16 | 尚未在新路径验证 | 3 |
| 24<br>`candidate_s04_pdf_order_to_record_agent` | [S04_PDF集团年中整改单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S04_PDF集团年中整改单/整改单.pdf>) → [T01_DOCX安全隐患整改记录单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T01_DOCX安全隐患整改记录单/安全隐患整改记录单.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s04_pdf_order_to_record_agent/安全隐患整改记录单.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s04_pdf_order_to_record_agent/安全隐患整改记录单.conversion_report.json>)<br>executed / render=true；文字14, 图3, 未解决8 | 尚未在新路径验证 | 2 |
| 25<br>`candidate_s05_table_to_record_agent` | [S05_DOCX东城安全检查表](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S05_DOCX东城安全检查表/环资公司安全检查记录表（2022.3.7 核心区纵二路东段、纵三路）.docx>) → [T01_DOCX安全隐患整改记录单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T01_DOCX安全隐患整改记录单/安全隐患整改记录单.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s05_table_to_record_agent/安全隐患整改记录单.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s05_table_to_record_agent/安全隐患整改记录单.conversion_report.json>)<br>executed / render=true；文字11, 图0, 未解决14 | 尚未在新路径验证 | 2 |
| 26<br>`candidate_s06_xlsx_to_record_agent` | [S06_XLSX安全检查台账](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S06_XLSX安全检查台账/安全检查台账.xlsx>) → [T01_DOCX安全隐患整改记录单](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T01_DOCX安全隐患整改记录单/安全隐患整改记录单.docx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s06_xlsx_to_record_agent/安全隐患整改记录单.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_candidate_agent_remaining_after_xlsx_fix_r1/cases/candidate_s06_xlsx_to_record_agent/安全隐患整改记录单.conversion_report.json>)<br>executed / render=true；文字8, 图0, 未解决17 | 尚未在新路径验证 | 2 |

### 已填样例模板3组

| 编号/Case ID | 源 → 模板 | 历史结果 | 新工具路径 | 首次纳入阶段 |
| --- | --- | --- | --- | --- |
| 27<br>`sample_s02_supervisor_doc_to_reply_doc_normalized_agent` | [S02_DOC监理通知图文源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S02_DOC监理通知图文源/监理通知单010.doc>) → [T05_DOC安全质量问题整改回复单模板](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T05_DOC安全质量问题整改回复单模板/安全质量问题整改回复单模板.doc>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_sample_template_observe_agent_rerun3/cases/sample_s02_supervisor_doc_to_reply_doc_normalized_agent/安全质量问题整改回复单模板.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_sample_template_observe_agent_rerun3/cases/sample_s02_supervisor_doc_to_reply_doc_normalized_agent/安全质量问题整改回复单模板.conversion_report.json>)<br>executed / render=true；文字4, 图1, 未解决8 | 尚未在新路径验证 | 2；先物化DOC并验证样例清理 |
| 28<br>`sample_s05_word_table_to_reply_doc_normalized_agent` | [S05_DOCX东城安全检查表](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S05_DOCX东城安全检查表/环资公司安全检查记录表（2022.3.7 核心区纵二路东段、纵三路）.docx>) → [T05_DOC安全质量问题整改回复单模板](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T05_DOC安全质量问题整改回复单模板/安全质量问题整改回复单模板.doc>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_sample_template_observe_agent_rerun3/cases/sample_s05_word_table_to_reply_doc_normalized_agent/安全质量问题整改回复单模板.docx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_sample_template_observe_agent_rerun3/cases/sample_s05_word_table_to_reply_doc_normalized_agent/安全质量问题整改回复单模板.conversion_report.json>)<br>executed / render=true；文字5, 图0, 未解决8 | 尚未在新路径验证 | 2；先物化DOC并验证样例清理 |
| 29<br>`sample_s06_xlsx_to_xlsx_ledger_normalized_agent` | [01_结构化台账源](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/01_结构化台账源/安全检查台账.xlsx>) → [T04_XLSX安全检查台账模板](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T04_XLSX安全检查台账模板/安全检查台账模版.xlsx>) | [旧输出](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_sample_template_observe_agent_rerun3/cases/sample_s06_xlsx_to_xlsx_ledger_normalized_agent/安全检查台账模版.xlsx>)；[报告](</Users/paul/Coding/DocTransAI/outputs/v1_audit_runs/2026-05-26_sample_template_observe_agent_rerun3/cases/sample_s06_xlsx_to_xlsx_ledger_normalized_agent/安全检查台账模版.conversion_report.json>)<br>executed / render=true；文字21, 图3, 未解决1 | 尚未在新路径验证 | 3 |

S01覆盖多队伍、多隐患和图文；S02覆盖DOC监理通知及质量/安全混合；S03覆盖长报告和多表多图；S04覆盖PDF图像源；S05覆盖Word表格及前后照片；S06覆盖Excel记录；S07覆盖无图源。媒体数量见候选清单历史描述，本轮未重新抽图核验。

三组样例净化测试覆盖原模板已含示例文字/图片的情形。新方案必须区分“固定内容”和“示例事实”，不能直接继承示例答案，也不能清空所有已有内容；这是阶段2/3需明确的行为要求。

## 5. 候选建议与执行配对关系

[candidate_pairs.json](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/03_配对建议_Manifest/candidate_pairs.json>)中的15条建议与执行case的文件SHA-256匹配如下。此表只表示文件对相同，不代表执行范围与配置相同。

| 建议 | Source/Template | 对应执行Case ID |
| --- | --- | --- |
| `candidate_s01_winter_to_record` | S01 / T01 | `candidate_s01_winter_to_record_agent` |
| `candidate_s01_winter_to_notice` | S01 / T02 | `candidate_s01_winter_to_notice_agent` |
| `candidate_s01_winter_to_penalty` | S01 / T03 | `candidate_s01_winter_to_penalty_agent` |
| `candidate_s02_supervisor_to_record` | S02 / T01 | `candidate_s02_supervisor_to_record_agent` |
| `candidate_s02_supervisor_to_penalty` | S02 / T03 | `candidate_s02_supervisor_to_penalty_agent` |
| `candidate_s02_supervisor_to_reply_doc` | S02 / T05 | `sample_s02_supervisor_doc_to_reply_doc_normalized_agent` |
| `candidate_s03_long_report_to_record` | S03 / T01 | `candidate_s03_long_report_to_record_agent` |
| `candidate_s03_long_report_to_ledger` | S03 / T04 | `candidate_s03_long_report_to_ledger_agent` |
| `candidate_s04_pdf_order_to_record` | S04 / T01 | `candidate_s04_pdf_order_to_record_agent` |
| `candidate_s04_pdf_order_to_reply_doc` | S04 / T05 | `candidate_s04_pdf_order_to_reply_doc_agent` |
| `candidate_s05_table_to_record` | S05 / T01 | `word_table_to_docx_record`<br>`candidate_s05_table_to_record_agent` |
| `candidate_s05_table_to_reply_doc` | S05 / T05 | `sample_s05_word_table_to_reply_doc_normalized_agent` |
| `candidate_s06_xlsx_to_record` | S06 / T01 | `xlsx_row6_to_docx_record`<br>`candidate_s06_xlsx_to_record_agent` |
| `candidate_s06_xlsx_to_ledger` | S06 / T04 | `sample_s06_xlsx_to_xlsx_ledger_normalized_agent` |
| `candidate_s07_check_record_to_notice` | S07 / T02 | `candidate_s07_check_record_to_notice_agent` |

## 6. 素材文件、参考成品与暂缓样本

| 文件 | SHA-256前12位 | 在执行清单中的关联 |
| --- | --- | --- |
| [01_被转换文档_Source/01_结构化台账源/安全检查台账.xlsx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/01_结构化台账源/安全检查台账.xlsx>) | 8d6aaab22bd9 | 作为源内容关联6个case |
| [01_被转换文档_Source/02_Word表格源/环资公司安全检查记录表（2022.3.7 核心区纵二路东段、纵三路）.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/02_Word表格源/环资公司安全检查记录表（2022.3.7 核心区纵二路东段、纵三路）.docx>) | 8cc1262a1ea5 | 作为源内容关联5个case |
| [01_被转换文档_Source/03_Word正文列表源/关于3月份安全生产大检查情况的通报.doc](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/03_Word正文列表源/关于3月份安全生产大检查情况的通报.doc>) | 3e5cbbf94264 | 作为源内容关联3个case |
| [01_被转换文档_Source/04_复杂检查记录源/附件1：广西路桥工程集团有限公司市政分公司2022年第一季度安全标准化检查记录表.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/04_复杂检查记录源/附件1：广西路桥工程集团有限公司市政分公司2022年第一季度安全标准化检查记录表.docx>) | 291f04ca120d | 作为源内容关联3个case |
| [01_被转换文档_Source/05_科技成果长文档PDF源/工程建设科学技术进步奖提名书-AI-数理双驱动的隧道地质信息融合解译与风险评估关键技术.pdf](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/01_被转换文档_Source/05_科技成果长文档PDF源/工程建设科学技术进步奖提名书-AI-数理双驱动的隧道地质信息融合解译与风险评估关键技术.pdf>) | bb3a7e20f24d | 作为源内容关联1个case |
| [02_目标模板_Template/01_DOCX整改记录单/安全隐患整改记录单.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/01_DOCX整改记录单/安全隐患整改记录单.docx>) | 1f1b8e490212 | 作为模板内容关联10个case |
| [02_目标模板_Template/02_DOCX整改通知单/安全隐患整改通单（项目）.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/02_DOCX整改通知单/安全隐患整改通单（项目）.docx>) | 0e19eaffaa98 | 作为模板内容关联6个case |
| [02_目标模板_Template/03_DOCX处罚通知单/质量安全检查处罚通知单（分公司）.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/03_DOCX处罚通知单/质量安全检查处罚通知单（分公司）.docx>) | b3bb86b32ccf | 作为模板内容关联6个case |
| [02_目标模板_Template/04_XLSX台账模板/安全检查台账模版.xlsx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/04_XLSX台账模板/安全检查台账模版.xlsx>) | fbe3f191f902 | 作为模板内容关联1个case |
| [02_目标模板_Template/04_XLSX台账模板/安全检查台账模版_副本.xlsx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/04_XLSX台账模板/安全检查台账模版_副本.xlsx>) | 6001c817e3c5 | 作为模板内容关联2个case |
| [02_目标模板_Template/05_DOC科技创新成果信息表/附件 广西住房城乡建设领域科技创新成果信息表.doc](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/05_DOC科技创新成果信息表/附件 广西住房城乡建设领域科技创新成果信息表.doc>) | cdc8d621c835 | 未作为执行源/模板；参考、原格式或待补配对 |
| [02_目标模板_Template/05_DOC科技创新成果信息表/附件 广西住房城乡建设领域科技创新成果信息表.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/02_目标模板_Template/05_DOC科技创新成果信息表/附件 广西住房城乡建设领域科技创新成果信息表.docx>) | c5f04bf7cb75 | 作为模板内容关联1个case |
| [03_参考成品_Reference/01_分公司整改反馈/分公司质安隐患整改反馈单2022.3.21.doc](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/03_参考成品_Reference/01_分公司整改反馈/分公司质安隐患整改反馈单2022.3.21.doc>) | c2b38e1633ce | 未作为执行源/模板；参考、原格式或待补配对 |
| [03_参考成品_Reference/02_五定表/质安隐患整改五定表2022.3.21.doc](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/03_参考成品_Reference/02_五定表/质安隐患整改五定表2022.3.21.doc>) | feb0c83c6fb5 | 未作为执行源/模板；参考、原格式或待补配对 |
| [04_V1暂缓样本_Deferred/01_扫描手写PDF/核心区纵二路东段、纵三路、纵六路（3.7）.pdf](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/04_V1暂缓样本_Deferred/01_扫描手写PDF/核心区纵二路东段、纵三路、纵六路（3.7）.pdf>) | 5ec3451a9aa7 | 未作为执行源/模板；参考、原格式或待补配对 |
| [04_V1暂缓样本_Deferred/01_扫描手写PDF/检查反馈单.pdf](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/04_V1暂缓样本_Deferred/01_扫描手写PDF/检查反馈单.pdf>) | 65d16c724afa | 未作为执行源/模板；参考、原格式或待补配对 |
| [04_V1暂缓样本_Deferred/02_第三方长报告/第三方检查-柳东新区官塘片曙光大道（雒容段）工程第三方巡查评估报告 202205031.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/04_V1暂缓样本_Deferred/02_第三方长报告/第三方检查-柳东新区官塘片曙光大道（雒容段）工程第三方巡查评估报告 202205031.docx>) | 512bc59a1536 | 作为源内容关联2个case |
| [06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S01_DOCX冬季专项检查通报/关于11月份冬季施工专项检查情况的通报.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S01_DOCX冬季专项检查通报/关于11月份冬季施工专项检查情况的通报.docx>) | 6128bd639b1b | 作为源内容关联3个case |
| [06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S02_DOC监理通知图文源/监理通知单010.doc](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S02_DOC监理通知图文源/监理通知单010.doc>) | 2943b461b8d7 | 作为源内容关联3个case |
| [06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S03_DOCX第三方巡查长报告/第三方检查-柳东新区官塘片曙光大道（雒容段）工程第三方巡查评估报告 202205031.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S03_DOCX第三方巡查长报告/第三方检查-柳东新区官塘片曙光大道（雒容段）工程第三方巡查评估报告 202205031.docx>) | 512bc59a1536 | 作为源内容关联2个case |
| [06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S04_PDF集团年中整改单/整改单.pdf](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S04_PDF集团年中整改单/整改单.pdf>) | 10ef801c648b | 作为源内容关联2个case |
| [06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S05_DOCX东城安全检查表/环资公司安全检查记录表（2022.3.7 核心区纵二路东段、纵三路）.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S05_DOCX东城安全检查表/环资公司安全检查记录表（2022.3.7 核心区纵二路东段、纵三路）.docx>) | 8cc1262a1ea5 | 作为源内容关联5个case |
| [06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S06_XLSX安全检查台账/安全检查台账.xlsx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S06_XLSX安全检查台账/安全检查台账.xlsx>) | 8d6aaab22bd9 | 作为源内容关联6个case |
| [06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S07_DOCX项目安全环保检查记录/安全环保检查记录表.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/S07_DOCX项目安全环保检查记录/安全环保检查记录表.docx>) | caf3934c5f37 | 作为源内容关联1个case |
| [06_扩展样本候选_文件类型汇总/02_候选模板_Template/T01_DOCX安全隐患整改记录单/安全隐患整改记录单.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T01_DOCX安全隐患整改记录单/安全隐患整改记录单.docx>) | 1f1b8e490212 | 作为模板内容关联10个case |
| [06_扩展样本候选_文件类型汇总/02_候选模板_Template/T02_DOCX安全隐患整改通知单/安全隐患整改通单（项目）.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T02_DOCX安全隐患整改通知单/安全隐患整改通单（项目）.docx>) | 0e19eaffaa98 | 作为模板内容关联6个case |
| [06_扩展样本候选_文件类型汇总/02_候选模板_Template/T03_DOCX质量安全检查处罚通知单/质量安全检查处罚通知单（分公司）.docx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T03_DOCX质量安全检查处罚通知单/质量安全检查处罚通知单（分公司）.docx>) | b3bb86b32ccf | 作为模板内容关联6个case |
| [06_扩展样本候选_文件类型汇总/02_候选模板_Template/T04_XLSX安全检查台账模板/安全检查台账模版.xlsx](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T04_XLSX安全检查台账模板/安全检查台账模版.xlsx>) | 6001c817e3c5 | 作为模板内容关联2个case |
| [06_扩展样本候选_文件类型汇总/02_候选模板_Template/T05_DOC安全质量问题整改回复单模板/安全质量问题整改回复单模板.doc](</Users/paul/Coding/DocTransAI-document-tools/V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/T05_DOC安全质量问题整改回复单模板/安全质量问题整改回复单模板.doc>) | 2aa596197b1c | 作为模板内容关联3个case |

重要区别：暂缓目录中的第三方长报告与S03文件SHA-256相同，已经通过S03进入历史执行清单；不能因为目录名Deferred就说从未测试。两份扫描/手写PDF没有在本次清点的执行清单中找到对应源配对，仍需单独安排。参考成品不自动等于逐字段真值标注。

## 7. 新工作区的资料依赖与运行前置条件

6个被引用的DataProxy bundle在原工作区均存在，在新worktree均未复制。这是Git忽略产物后的预期状态，不是DataProxy解析失败。存在性核对仅针对manifest入口，重跑前仍须检查其组件与图片引用，不代表所有历史资产已完整验证。

| Bundle | 新worktree | 原工作区资料入口 |
| --- | --- | --- |
| dataproxy_fresh_probe_20260521 | 缺失 | [存在](</Users/paul/Coding/DocTransAI/artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json>) |
| dataproxy_fresh_probe_20260525_all_sources_latest | 缺失 | [存在](</Users/paul/Coding/DocTransAI/artifacts/dataproxy_fresh_probe_20260525_all_sources_latest/parsed_document_bundle.json>) |
| dataproxy_fresh_probe_20260525_scitech_pdf | 缺失 | [存在](</Users/paul/Coding/DocTransAI/artifacts/dataproxy_fresh_probe_20260525_scitech_pdf/parsed_document_bundle.json>) |
| dataproxy_fresh_probe_20260526_expanded_candidates_after_xlsx_fix | 缺失 | [存在](</Users/paul/Coding/DocTransAI/artifacts/dataproxy_fresh_probe_20260526_expanded_candidates_after_xlsx_fix/parsed_document_bundle.json>) |
| dataproxy_fresh_probe_20260526_expanded_candidates_latest | 缺失 | [存在](</Users/paul/Coding/DocTransAI/artifacts/dataproxy_fresh_probe_20260526_expanded_candidates_latest/parsed_document_bundle.json>) |
| dataproxy_fresh_probe_20260526_sample_template_matrix | 缺失 | [存在](</Users/paul/Coding/DocTransAI/artifacts/dataproxy_fresh_probe_20260526_sample_template_matrix/parsed_document_bundle.json>) |

下列9个测试文件包含artifacts路径字面量。它们的部分用例依赖本机历史资料；这不是说每个测试函数都会失败，需逐例区分真实读取和替身数据：

- [tests/integration/test_agent_mapping_preview.py](</Users/paul/Coding/DocTransAI-document-tools/tests/integration/test_agent_mapping_preview.py>)
- [tests/integration/test_agent_mapping_resolution.py](</Users/paul/Coding/DocTransAI-document-tools/tests/integration/test_agent_mapping_resolution.py>)
- [tests/integration/test_agentic_image_fill_skeleton.py](</Users/paul/Coding/DocTransAI-document-tools/tests/integration/test_agentic_image_fill_skeleton.py>)
- [tests/integration/test_agentic_word_table_skeleton.py](</Users/paul/Coding/DocTransAI-document-tools/tests/integration/test_agentic_word_table_skeleton.py>)
- [tests/integration/test_mapping_render_plan_from_dataproxy_bundle.py](</Users/paul/Coding/DocTransAI-document-tools/tests/integration/test_mapping_render_plan_from_dataproxy_bundle.py>)
- [tests/integration/test_v1_conversion_workflow.py](</Users/paul/Coding/DocTransAI-document-tools/tests/integration/test_v1_conversion_workflow.py>)
- [tests/source_model/test_adapter.py](</Users/paul/Coding/DocTransAI-document-tools/tests/source_model/test_adapter.py>)
- [tests/workflows/test_agentic_conversion.py](</Users/paul/Coding/DocTransAI-document-tools/tests/workflows/test_agentic_conversion.py>)
- [tests/workflows/test_v1_batch_audit.py](</Users/paul/Coding/DocTransAI-document-tools/tests/workflows/test_v1_batch_audit.py>)

迁移措施：通过显式配置定位原工作区资料；为普通测试整理小型脱敏、自包含fixture；真实样本单独标记并显式运行；缺失资料要明确报缺或有理由skip，不能记为passed。不要把大批解析产物、渲染缓存或密钥提交到Git，也不要直接复制原.venv。历史manifest的绝对sidecar/源路径还需检查，不能只替换bundle入口就认定可移植。

当前可以确认的是392项收集成功，以及上一轮新环境12项客户端测试通过。本轮未运行392项测试，历史392 passed不能作为新worktree全绿证明。

## 8. 尚需补齐的覆盖

| 能力 | 已有依据 | 新路径缺口 / 新断言 | 阶段 |
| --- | --- | --- | --- |
| 原生材料及标题上下文 | data_layer；长稿section_title事实 | 避免仅text匹配；保持表头/单位/原生引用；图片哈希路径消歧 | 1 |
| 工具调用与流式 | llm12项主要为现客户端；实验手工运行 | SSE分片、完整参数再执行、截断JSON、超时、重复调用、usage未知；无真实API的替身测试 | 1 |
| 可靠编辑 | renderers已有大量行为；实验临时专项检查 | 一批失败无部分写入、原模板不变、包部件保留、节点ID过期、重复操作幂等 | 1/2 |
| 源页面查看 | 旧路径默认渲染；1项DOC预览测试 | view_source_page尚未正式接入；页码映射、源缺图、按需取页、真正传图及覆盖记录 | 2 |
| 图文组与多图 | 旧DOCX多图/重复区；新通知单2组图文 | 一条描述多图、跨页不分离、数量不一致、错图/邻行图、模板中既有图片保留 | 2 |
| 准确目标定位 | 跨run、表格、页眉页脚、隐式空白已有测试 | 同名多目标不猜首末位置、结构变更后地址失效、复杂结构明确不支持 | 2 |
| 已填样例模板 | 6项normalization测试＋3组执行case | 固定内容/示例事实区分，清理旧图和旧值，同时保留真正模板元素 | 2/3 |
| XLSX编辑 | 3项旧renderer测试＋3组XLSX目标case | 新工具后端未实现；多行、公式相对引用、合并单元格、锚点/行高及打印页 | 3 |
| 一对象一文档 | 旧source_instances/cluster覆盖部分概念 | 新入口确认对象集合、逐对象输出、避免混对象；现3个实验都不是批量一对多验收 | 2—4 |
| 独立复核 | 旧output_checker/报告；新实验Codex人工式复核 | 新上下文只读复核未形成自动回归；执行成功≠内容通过，正确留空≠失败 | 4 |
| 性能与预算 | 部分旧批次有performance；新实验续跑统计 | 全任务连续计时、失败请求耗时、未知用量、缓存token、同模型同参数对比 | 4 |
| 扫描/手写及复杂格式 | S04扫描型候选历史执行；2份手写PDF未入矩阵 | 固定解析交付版本，区分上游缺失与下游失误；PDF编辑仍不纳入 | 专项 |

## 9. 分阶段回归安排

- 阶段1：先固化新工具测试，复现3个小样；同时保留DataProxy读取和客户端测试。3个样本是快速回归，不是最终清单。
- 阶段2：按本次变更选择DOCX相关子集，结束前覆盖29个case中26组DOC/DOCX模板路径（包括3组需先物化的DOC目标）。以真实文件检查为准；遗留产物本身不足以证明新路径通过。
- 阶段3：补齐3组XLSX目标：xlsx_row6_to_xlsx_register、candidate_s03_long_report_to_ledger_agent、sample_s06_xlsx_to_xlsx_ledger_normalized_agent，并补公式/多行专项。
- 阶段4：在同样kimi-k3、源bundle、对象范围、模板及内容约束下做新旧对照。记录首轮和外部反馈后结果；不把修正后的成绩当自主首轮成绩。
- 阶段5：29个case均有新路径结论或明确不支持/源缺说明后，才切换默认入口和清理旧测试。相同文件且相同配置可合并执行并记录覆盖映射；仅文件哈希相同但bundle或范围不同不能合并。
- 日常只跑相关单元/集成测试和少量对应真实case；阶段关口才进行范围明确的回归，不默认每次全量调用模型。

真实结果的真值应从源材料与目标要求独立标注：该填什么、允许什么归纳、应选哪张图、哪些应留空。禁止用模型自己发现的槽位或accepted数量定义完整性分母。

## 10. 逐文件测试清单

| 文件 | 收集项 | 处置 | 迁移注意事项 |
| --- | ---: | --- | --- |
| [tests/agentic_mapping/test_assembler.py](</Users/paul/Coding/DocTransAI-document-tools/tests/agentic_mapping/test_assembler.py>) | 11 | 拆分迁移 | 保留缺失、证据、图文行为；退出逐槽决策、组装和修复协议 |
| [tests/agentic_mapping/test_context_channel.py](</Users/paul/Coding/DocTransAI-document-tools/tests/agentic_mapping/test_context_channel.py>) | 4 | 拆分迁移 | 保留缺失、证据、图文行为；退出逐槽决策、组装和修复协议 |
| [tests/agentic_mapping/test_decision_repair.py](</Users/paul/Coding/DocTransAI-document-tools/tests/agentic_mapping/test_decision_repair.py>) | 3 | 拆分迁移 | 保留缺失、证据、图文行为；退出逐槽决策、组装和修复协议 |
| [tests/agentic_mapping/test_decisions.py](</Users/paul/Coding/DocTransAI-document-tools/tests/agentic_mapping/test_decisions.py>) | 13 | 拆分迁移 | 保留缺失、证据、图文行为；退出逐槽决策、组装和修复协议 |
| [tests/agentic_mapping/test_mapper.py](</Users/paul/Coding/DocTransAI-document-tools/tests/agentic_mapping/test_mapper.py>) | 12 | 拆分迁移 | 保留图像实际传递、去重和错误反馈；默认发送所有源页等策略断言须替换 |
| [tests/agentic_mapping/test_target_ledger.py](</Users/paul/Coding/DocTransAI-document-tools/tests/agentic_mapping/test_target_ledger.py>) | 1 | 拆分迁移 | 保留缺失、证据、图文行为；退出逐槽决策、组装和修复协议 |
| [tests/agentic_mapping/test_template_targets.py](</Users/paul/Coding/DocTransAI-document-tools/tests/agentic_mapping/test_template_targets.py>) | 3 | 拆分迁移 | 保留缺失、证据、图文行为；退出逐槽决策、组装和修复协议 |
| [tests/agentic_mapping/test_validator.py](</Users/paul/Coding/DocTransAI-document-tools/tests/agentic_mapping/test_validator.py>) | 35 | 拆分迁移 | 保留无效引用/缺值错误；文本相似度、全库补引用等不能继续作为语义正确证明 |
| [tests/agentic_mapping/test_visual_discovery.py](</Users/paul/Coding/DocTransAI-document-tools/tests/agentic_mapping/test_visual_discovery.py>) | 2 | 拆分迁移 | 保留缺失、证据、图文行为；退出逐槽决策、组装和修复协议 |
| [tests/agentic_mapping/test_visual_targets.py](</Users/paul/Coding/DocTransAI-document-tools/tests/agentic_mapping/test_visual_targets.py>) | 1 | 替换 | 现测试以页码提示选择后一个同名标签；新方案要求准确地址，不能沿用该通过标准 |
| [tests/contracts/test_full_agent_context_schema.py](</Users/paul/Coding/DocTransAI-document-tools/tests/contracts/test_full_agent_context_schema.py>) | 3 | 旧协议退出 | 这里测试的是旧full_agent_context/RenderPlan，不是DataProxy契约 |
| [tests/contracts/test_render_plan_schema.py](</Users/paul/Coding/DocTransAI-document-tools/tests/contracts/test_render_plan_schema.py>) | 4 | 旧协议退出 | 这里测试的是旧full_agent_context/RenderPlan，不是DataProxy契约 |
| [tests/data_layer/test_bundle_reader.py](</Users/paul/Coding/DocTransAI-document-tools/tests/data_layer/test_bundle_reader.py>) | 6 | 保留 | 原生bundle、组件路径和契约错误 |
| [tests/formats/test_registry.py](</Users/paul/Coding/DocTransAI-document-tools/tests/formats/test_registry.py>) | 3 | 简化迁移 | 保留格式识别和不支持错误，避免旧注册机制成为依赖 |
| [tests/ingestion/test_asset_pack_writer.py](</Users/paul/Coding/DocTransAI-document-tools/tests/ingestion/test_asset_pack_writer.py>) | 1 | 边界复核 | 新项目消费DataProxy产物，不再维护第二套生成交付物管线 |
| [tests/ingestion/test_pipeline_contract.py](</Users/paul/Coding/DocTransAI-document-tools/tests/ingestion/test_pipeline_contract.py>) | 1 | 边界复核 | 新项目消费DataProxy产物，不再维护第二套生成交付物管线 |
| [tests/integration/test_agent_mapping_preview.py](</Users/paul/Coding/DocTransAI-document-tools/tests/integration/test_agent_mapping_preview.py>) | 2 | 迁移场景 | 保留源/模板和结果断言，改接正式工具入口与替身客户端 |
| [tests/integration/test_agent_mapping_resolution.py](</Users/paul/Coding/DocTransAI-document-tools/tests/integration/test_agent_mapping_resolution.py>) | 3 | 迁移场景 | 保留源/模板和结果断言，改接正式工具入口与替身客户端 |
| [tests/integration/test_agentic_image_fill_skeleton.py](</Users/paul/Coding/DocTransAI-document-tools/tests/integration/test_agentic_image_fill_skeleton.py>) | 1 | 迁移场景 | 保留源/模板和结果断言，改接正式工具入口与替身客户端 |
| [tests/integration/test_agentic_word_table_skeleton.py](</Users/paul/Coding/DocTransAI-document-tools/tests/integration/test_agentic_word_table_skeleton.py>) | 1 | 迁移场景 | 保留源/模板和结果断言，改接正式工具入口与替身客户端 |
| [tests/integration/test_mapping_render_plan_from_dataproxy_bundle.py](</Users/paul/Coding/DocTransAI-document-tools/tests/integration/test_mapping_render_plan_from_dataproxy_bundle.py>) | 1 | 迁移场景 | 保留源/模板和结果断言，改接正式工具入口与替身客户端 |
| [tests/integration/test_v1_conversion_workflow.py](</Users/paul/Coding/DocTransAI-document-tools/tests/integration/test_v1_conversion_workflow.py>) | 9 | 迁移场景 | 保留源/模板和结果断言，改接正式工具入口与替身客户端 |
| [tests/llm/test_client.py](</Users/paul/Coding/DocTransAI-document-tools/tests/llm/test_client.py>) | 12 | 保留并扩展 | 模型配置、请求预算、响应处理；补工具流与新配置键 |
| [tests/mapping/test_agent_resolver.py](</Users/paul/Coding/DocTransAI-document-tools/tests/mapping/test_agent_resolver.py>) | 41 | 拆分迁移 | 提取对象一致性与保守填写案例；候选排序、planner/resolver契约退出 |
| [tests/mapping/test_candidate_builder.py](</Users/paul/Coding/DocTransAI-document-tools/tests/mapping/test_candidate_builder.py>) | 2 | 拆分迁移 | 提取对象一致性与保守填写案例；候选排序、planner/resolver契约退出 |
| [tests/mapping/test_cluster_planning.py](</Users/paul/Coding/DocTransAI-document-tools/tests/mapping/test_cluster_planning.py>) | 4 | 拆分迁移 | 提取对象一致性与保守填写案例；候选排序、planner/resolver契约退出 |
| [tests/mapping/test_full_agent_context.py](</Users/paul/Coding/DocTransAI-document-tools/tests/mapping/test_full_agent_context.py>) | 2 | 拆分迁移 | 提取对象一致性与保守填写案例；候选排序、planner/resolver契约退出 |
| [tests/mapping/test_image_mapper.py](</Users/paul/Coding/DocTransAI-document-tools/tests/mapping/test_image_mapper.py>) | 2 | 拆分迁移 | 提取对象一致性与保守填写案例；候选排序、planner/resolver契约退出 |
| [tests/mapping/test_orchestrator.py](</Users/paul/Coding/DocTransAI-document-tools/tests/mapping/test_orchestrator.py>) | 15 | 拆分迁移 | 提取对象一致性与保守填写案例；候选排序、planner/resolver契约退出 |
| [tests/mapping/test_planner.py](</Users/paul/Coding/DocTransAI-document-tools/tests/mapping/test_planner.py>) | 16 | 拆分迁移 | 提取对象一致性与保守填写案例；候选排序、planner/resolver契约退出 |
| [tests/mapping/test_resolver.py](</Users/paul/Coding/DocTransAI-document-tools/tests/mapping/test_resolver.py>) | 5 | 拆分迁移 | 提取对象一致性与保守填写案例；候选排序、planner/resolver契约退出 |
| [tests/mapping/test_review_policy.py](</Users/paul/Coding/DocTransAI-document-tools/tests/mapping/test_review_policy.py>) | 1 | 拆分迁移 | 提取对象一致性与保守填写案例；候选排序、planner/resolver契约退出 |
| [tests/mapping/test_slot_decisions.py](</Users/paul/Coding/DocTransAI-document-tools/tests/mapping/test_slot_decisions.py>) | 2 | 拆分迁移 | 提取对象一致性与保守填写案例；候选排序、planner/resolver契约退出 |
| [tests/mapping/test_structural_candidates.py](</Users/paul/Coding/DocTransAI-document-tools/tests/mapping/test_structural_candidates.py>) | 2 | 拆分迁移 | 提取对象一致性与保守填写案例；候选排序、planner/resolver契约退出 |
| [tests/mapping/test_type_inference.py](</Users/paul/Coding/DocTransAI-document-tools/tests/mapping/test_type_inference.py>) | 2 | 拆分迁移 | 提取对象一致性与保守填写案例；候选排序、planner/resolver契约退出 |
| [tests/models/test_render_plan.py](</Users/paul/Coding/DocTransAI-document-tools/tests/models/test_render_plan.py>) | 2 | 旧协议退出 | 旧RenderPlan序列化；新操作结果只建立必要类型 |
| [tests/renderers/test_docx_renderer.py](</Users/paul/Coding/DocTransAI-document-tools/tests/renderers/test_docx_renderer.py>) | 34 | 迁移行为 | 保留图片、文字、版式断言；替换RenderPlan输入 |
| [tests/renderers/test_image_placement.py](</Users/paul/Coding/DocTransAI-document-tools/tests/renderers/test_image_placement.py>) | 7 | 迁移行为 | 保留图片、文字、版式断言；替换RenderPlan输入 |
| [tests/renderers/test_pdf_renderer.py](</Users/paul/Coding/DocTransAI-document-tools/tests/renderers/test_pdf_renderer.py>) | 3 | 暂缓 | 3项PDF编辑测试留历史基线；PDF源/预览仍在范围内 |
| [tests/renderers/test_pipeline.py](</Users/paul/Coding/DocTransAI-document-tools/tests/renderers/test_pipeline.py>) | 2 | 迁移行为 | 保留图片、文字、版式断言；替换RenderPlan输入 |
| [tests/renderers/test_xlsx_renderer.py](</Users/paul/Coding/DocTransAI-document-tools/tests/renderers/test_xlsx_renderer.py>) | 3 | 迁移行为 | 保留图片、文字、版式断言；替换RenderPlan输入 |
| [tests/reports/test_conversion_report.py](</Users/paul/Coding/DocTransAI-document-tools/tests/reports/test_conversion_report.py>) | 7 | 简化迁移 | 保留来源与问题分类，退出旧报表字段形状 |
| [tests/reports/test_provenance_report.py](</Users/paul/Coding/DocTransAI-document-tools/tests/reports/test_provenance_report.py>) | 2 | 简化迁移 | 保留来源与问题分类，退出旧报表字段形状 |
| [tests/scripts/test_attribute_unresolved_targets.py](</Users/paul/Coding/DocTransAI-document-tools/tests/scripts/test_attribute_unresolved_targets.py>) | 4 | 迁移口径 | 源缺不等于故障、条件项不误报；不强制保留旧归因脚本 |
| [tests/source_model/test_adapter.py](</Users/paul/Coding/DocTransAI-document-tools/tests/source_model/test_adapter.py>) | 12 | 拆分迁移 | 保留原生定位、图文归属和范围；退出SourceModel/实例索引形状 |
| [tests/source_model/test_source_instances.py](</Users/paul/Coding/DocTransAI-document-tools/tests/source_model/test_source_instances.py>) | 6 | 拆分迁移 | 保留原生定位、图文归属和范围；退出SourceModel/实例索引形状 |
| [tests/templates/test_sample_normalization.py](</Users/paul/Coding/DocTransAI-document-tools/tests/templates/test_sample_normalization.py>) | 6 | 迁移行为 | 6项测试涉及已填样例清理、固定内容/图片保留和孤立媒体；不必保留占位符化实现 |
| [tests/templates/test_template_analyzer.py](</Users/paul/Coding/DocTransAI-document-tools/tests/templates/test_template_analyzer.py>) | 23 | 拆分迁移 | 保留结构/样例净化/物化；退出语义槽位硬约束 |
| [tests/templates/test_template_materialization.py](</Users/paul/Coding/DocTransAI-document-tools/tests/templates/test_template_materialization.py>) | 2 | 拆分迁移 | 保留结构/样例净化/物化；退出语义槽位硬约束 |
| [tests/templates/test_visual_preview.py](</Users/paul/Coding/DocTransAI-document-tools/tests/templates/test_visual_preview.py>) | 1 | 拆分迁移 | 保留结构/样例净化/物化；退出语义槽位硬约束 |
| [tests/upstream/test_dataproxy_policy.py](</Users/paul/Coding/DocTransAI-document-tools/tests/upstream/test_dataproxy_policy.py>) | 1 | 边界复核 | 保留不修改DataProxy等边界；主动调上游不是默认转换入口 |
| [tests/upstream/test_dataproxy_runner.py](</Users/paul/Coding/DocTransAI-document-tools/tests/upstream/test_dataproxy_runner.py>) | 5 | 边界复核 | 保留不修改DataProxy等边界；主动调上游不是默认转换入口 |
| [tests/upstream/test_issue_report.py](</Users/paul/Coding/DocTransAI-document-tools/tests/upstream/test_issue_report.py>) | 2 | 边界复核 | 保留不修改DataProxy等边界；主动调上游不是默认转换入口 |
| [tests/validation/test_bundle_gate.py](</Users/paul/Coding/DocTransAI-document-tools/tests/validation/test_bundle_gate.py>) | 3 | 拆分迁移 | 保留输出完整性和输入缺口；删除旧状态/领域句式绑定 |
| [tests/validation/test_output_checker.py](</Users/paul/Coding/DocTransAI-document-tools/tests/validation/test_output_checker.py>) | 17 | 拆分迁移 | 保留输出完整性和输入缺口；删除旧状态/领域句式绑定 |
| [tests/workflows/test_agentic_conversion.py](</Users/paul/Coding/DocTransAI-document-tools/tests/workflows/test_agentic_conversion.py>) | 16 | 迁移场景 | 改接单一转换入口；保留执行失败、作用域与报告状态检查 |
| [tests/workflows/test_v1_batch_audit.py](</Users/paul/Coding/DocTransAI-document-tools/tests/workflows/test_v1_batch_audit.py>) | 8 | 迁移场景 | 改接单一转换入口；保留执行失败、作用域与报告状态检查 |

全部test函数/node ID及case原始配置见机器可读明细。本文不删除、不迁移任何测试，也不修改运行配置。

## 第二阶段增量（2026-09-05）

新增 `tests/documents/test_docx_structures.py`，并扩充 `tests/integration/test_document_tools.py`。新增范围包括重复空白与 Unicode 精确范围、正文/单元格真实列表、横向/完整纵向合并行组、旧节点失效与编号回滚、嵌套/页眉表格地址、固定行高、节边界、普通/零宽书签、源页导航、搜索翻页及编辑增量返回。

定向测试 68 项通过；全库仅收集 442 项（阶段一为 423）。真实模型在原三个代表 case 外增加 `word_table_to_docx_penalty`，扩展首次运行因书签保护过宽耗尽步数，修复后单独重跑。详细执行结果与业务限制见 [第二阶段记录](phase2-development.md)。历史 29 个 distinct case 未全量重跑，也不因此标记为新路径通过。

## 第三阶段增量（2026-09-05）

增加 `tests/documents/test_xlsx_tools.py`，并补充统一转换入口的 XLSX 集成验证。覆盖类型化写入、公式覆盖保护、复制时混合/跨表引用、完整合并复制、图片连续保存与局部删除、隐藏页和验证范围保留、自定义 XML、默认列宽只读保护、Excel 文本长度限制和横向重复标识列。

另有独立计算引擎验证公式结果，以及单条台账、DOCX 六条记录、已填示例模板清理三个真实验收场景。失败及修复重跑分开记录，详见 [第三阶段记录](phase3-development.md)。此增量不表示历史 29 个 case 已全量通过。

第三阶段最终定向结果为 81 passed，全库仅收集 455 项；新增 13 项。多条记录另行版式复核后完成，保留此前步数耗尽与超时记录，不计为主流程首次自主成功。

## 第四阶段增量（2026-09-05）

新增 `tests/integration/test_independent_review.py`，覆盖只读复核、上下文隔离、缺页与不确定性、结构化 grounding、修正范围/次数、检查点、哈希绑定、超时与 CLI 状态。定向 101 passed，全库仅收集 475 项（增加 20 项）。真实验收包含有问题的 DOCX/XLSX、正常对照及明确标记的合成角色反例；通知单仍存在漏检，不能标为语义验收通过。详见 [第四阶段记录](phase4-development.md)。
