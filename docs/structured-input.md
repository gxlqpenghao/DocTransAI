# 结构化输入模式

结构化输入模式适用于已经把业务记录保存在数据库中的系统，例如智慧安全管理系统。它不上传原始文档到 DataProxy，而是接收业务后端整理好的字段和图片；转换、模板渲染和审计仍复用 DocTransAI 的现有实现。

## 输入

```json
{
  "document_id": "danger-check-batch-20261124",
  "records": [
    {
      "record_id": "hidden-001",
      "fields": {
        "项目名称": "桐金路一分部",
        "隐患描述": "示例业务数据"
      },
      "images": [
        {"asset_id": "photo-001", "path": "/secure/input/photo.jpg", "caption": "现场照片"}
      ]
    }
  ]
}
```

每条记录必须有唯一 `record_id`。字段值由业务系统负责查询和授权；DocTransAI 不直接连接业务系统数据库。图片可以使用部署机器可读的路径，或使用 base64（单张上限 20 MiB）。

## 本地验证

```bash
uv run doctransai structured \
  --input-json ./structured-input.json \
  --template ./template.docx \
  --output-dir ./outputs/structured-run \
  --env-file /secure/backend.env
```

默认只生成转换成品。需要单独验证字段审计时增加 `--audit`；审计是额外的模型阶段，不应阻塞首期导出链路。

结构化模式与 DataProxy 文件接入模式并存。原始文件解析仍使用 `remote`/Web 接入；结构化模式不会删除或绕过原有 DataProxy 代码，只在输入适配层生成稳定的 `structured:<record_id>:<field>` 来源引用。
