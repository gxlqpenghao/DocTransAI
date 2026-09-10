# 原始流程上的四项工具加固

基点f07be29，分支codex/v1-tool-hardening，代码453f913。没有整套cherry-pick失败实验。

仅移植：同段多范围替换（replace_ranges）、明确原子回滚回执、提前显示书签/评论等编辑保护、失败草稿的最后预览信息。新工具可选，不强制模型使用。

保留原始prompt逐字不变，source view/XLSX view/config字节均与基点一致；agent的自动渲染与checkpoint原逻辑不变，只扩充edit_document回执。没有移植连续保留所有图像、按需预览新编排、结构视图重排、尺寸扩展或整篇提示词改写。

离线回归：tests/documents、tests/integration/test_document_tools.py、tests/integration/test_independent_review.py、tests/data_layer、tests/llm，135 passed。包含同段多区间顺序无关、非BMP文字、显式run样式快照、重叠失败整批回滚、书签保护摘要，以及原版自动预览回归。

一次固定K3/max代表验证（台账第6行→DOCX通知单），使用六案例冻结源/模板/历史包；没有Windows、没有重跑、没有修改测试条件：

- completed/needs_review，3次模型请求，总550.478秒，模型542.064秒；工具编辑一次成功，无失败恢复。
- 模型实际使用两次replace_ranges（两处填空、三处年/月/日）。原版自动预览后完成，未产生连续会话请求体超限问题。
- 两页最终PNG逐页目检，隐患照片与独立说明同页，整改期限保留20时，固定文字保留。ZIP/hash与报告一致，模板未变。
- 检查时间显示日期部分，落款日期仍按检查日期推定并列ambiguous。这属于原版模型语义边界，本次工具加固没有解决，不作为业务全通过。
- 原始基线435.529秒，同一案例本次550.478秒，约慢26.4%。单次结果不能证明因果，不能宣称本次改动提速。它验证的是工具功能与原流程兼容，不是整体性能优化。

产物：outputs/v1-tool-hardening-20260910/runs/xlsx_row6_to_docx_notice/，含task/input/trace/model-diagnostics/request-snapshots/review/result与previews。原始日志只本地。用户当前已填模板未覆盖，其他分支与六案例材料保留；未推送、未部署。
