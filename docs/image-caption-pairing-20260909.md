# 独立图文组修正与真实复测

问题：Windows DataProxy 正式包任务 3be7c524f62c4d38a8c346064225b95d 的消费测试中，K3 使用 set_images 一次写入两张图，并以 set_text 合并两个不同条目的说明。结果虽然完成，图文组织不符合一图一说明要求。此前 Mac 测试使用 repeat_paragraphs，正确创建两组。旧包四张图 caption 均 null，因此不要求 DataProxy 完美提取图注，也不将 weak_caption 本身视为阻塞。

修正仅涉及通用编辑提示词和 edit_document 工具描述：各自有独立说明的图片保留独立图文组，DOCX 用 repeat_paragraphs 复制完整原型；只有确实共用说明的同一条目才合放多图。结果检查明确逐组核对。没有新增编辑器或样本业务规则，没有手动修正上游包或成品。

相关回归：tests/documents 与 tests/integration/test_document_tools.py，64 passed。

复测使用相同正式包、模板、用户指令，kimi-k3 / max，默认不启用独立复核。结果位于 outputs/tunnel_integration_20260909/doc-convert-pairs/result.docx。

- completed / needs_review；4 次模型请求，总耗时 638.830 秒，模型请求 628.658 秒。
- 首次编辑因另一字段 replace_range 偏移不匹配整批被拒；下一轮模型自行恢复，第二次编辑成功。不可称首次编辑成功。
- 模型使用 repeat_paragraphs 创建两组图片及独立说明，keep_together=true。
- 最终三页 PNG 全部目检：围挡照片与“二工区围挡未及时封闭”同页、村民照片与“有村民进入施工现场”同页；未见错配或说明裁切。两条隐患与整改要求存在，未混入正面检查照片。
- 模板哈希未变，输出 ZIP testzip 无错误，文件哈希与报告一致。
- 仍有角色映射语义推定，模型已列为 ambiguous；落款日期仍从原文日期迁移，不能作为业务事实认证。提示词不能保证所有任务稳定正确。
- 本轮不是效率优化；相较上次 495.832 秒更慢，不宣称提速。无需为非规范图注再阻塞整个 DataProxy 接入。

原错误结果和 trace 保留在 doc-convert；新结果单独保存。未推送或修改上游部署。
