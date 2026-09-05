# DocTransAI

DocTransAI is a template-driven document transformation project. It ingests structured document bundles, maps source evidence into target templates, and renders traceable output documents.

The project keeps its runtime isolated from DataProxy. DataProxy v0 data-asset schemas are vendored as a local contract snapshot under `contracts/dataproxy/data_asset_pack_v0/`, and DocTransAI reads `parsed_document_bundle.json` through its own `doctransai.data_layer` package.

## Document tools path — phase 1

The new `convert` entrypoint uses native DataProxy evidence, a single model tool loop,
and a DOCX editor. It does not use the legacy source model, slot analyzer, mapping
planner, or RenderPlan. Legacy modules remain available for comparison.

```bash
uv sync --locked

# Configure a working render_docx.py and its Python interpreter.
export DOCTRANSAI_DOCX_RENDERER=/path/to/render_docx.py
export DOCTRANSAI_RENDER_PYTHON=/path/to/python3

uv run doctransai convert \
  --bundle /data/parsed_document_bundle.json \
  --source-file /data/source.docx \
  --template /data/template.docx \
  --output-dir /data/runs/new-run \
  --instruction '依据该源材料填写模板；缺少依据的内容留空。' \
  --env-file /path/to/provider.env
```

Use a new output directory for each run. Choose a source with `--source-file` or
`--document-id` when the bundle contains several documents. `--source-ref` can be
repeated to declare the primary source objects, for example a specific ledger row.
Copies of source files are matched by SHA-256 when their paths differ.

The default model is `kimi-k3`. Credentials and endpoint are read from
`DOCTRANSAI_LLM_API_KEY` / `DOCTRANSAI_LLM_BASE_URL`, or an explicitly selected
environment file (`--env-file` / `DOCTRANSAI_ENV_FILE`). Current DataProxy
`DATAPROXY_GENERATION_API_KEY` / `DATAPROXY_GENERATION_BASE_URL` and older QWEN keys
are supported as fallbacks. `DATAPROXY_GENERATION_MODEL` does not override this
project’s model. No personal DataProxy directory is assumed.

For K3, the unset temperature now follows the provider default of 1.0; explicit
configuration still takes precedence. K3 is thinking-only and does not support
`thinking_budget` ([provider documentation](https://help.aliyun.com/zh/model-studio/kimi-api)).
The text-output token setting must not be presented as a cap on thinking tokens;
the application separately bounds elapsed time and tool-loop steps.

The Python API is `doctransai.conversion.convert(TaskSpec(...), config=...)`.
The API permits injected clients and previewers for tests; ordinary tests need no
network access, credentials, or LibreOffice.

### Output and review meaning

- `result.docx` is published only after the model finishes and all pages of the
  current output version have been delivered in an earlier model round.
- `working.docx` is retained as a draft when execution fails or exceeds its budget;
  it is not labeled as a finished result.
- `review.json` records execution, actual page coverage, editor self-check,
  missing/ambiguous items, timings and available usage. `trace.jsonl` records tool
  calls, errors and model response metadata without request-image base64 or keys.
  Temporary network/server failures are retried once before tool execution; invalid
  responses, authentication/configuration failures and exhausted budgets are not
  blindly retried. Failed requests without usage remain marked unknown.
- Outputs of up to four pages use a compact result-check context after preview:
  source material, original template structure and current output replace the
  earlier image/tool conversation. Source pages or original template images can
  be requested again. This remains editor self-check, not independent review.
- Phase 1 provides deterministic checks and editor self-check only. Independent
  semantic review is **not implemented yet**. `review_status=not_run` refers to
  that independent review, not a missing output preview. `needs_review` reports
  unresolved issues; it is not a request for permission to run the task.
- CLI exit codes: 0 = execution completed (not proof of factual correctness),
  1 = conversion failed, 2 = invalid CLI/runtime configuration.

### Current capabilities and limits

Tools: `read_source`, `view_source_page`, `view_source_asset`, `inspect_document`,
`edit_document`, `preview_document`, `finish`. Tool schemas live in `tools.py`;
work principles live in `prompts/document_editing_policy.md`.

DOCX supports exact text ranges (including repeated blanks and cross-run spans),
real decimal/bullet lists, images, paragraph groups, and consecutive table-row
groups with complete vertical merges. Row height/splitting and paragraph formatting
are explicit operations. Body, cell, nested-table and header/footer paragraphs have
individual addresses. Whole nested-table replacement remains unsupported.
Batches are versioned and atomic. Repeating the same batch is
idempotent within a run. Source page viewing prefers an unambiguous native
`scanned_page` asset; otherwise it renders the selected source file and marks
correspondence with DataProxy page anchors as unverified. Source image checksums
are checked when present. Repeated upstream asset IDs retain their variants.

Not yet supported: XLSX editing, whole nested-table replacement,
floating textboxes, resume after process restart, or an independent semantic
reviewer. Existing run directories are refused; use a new run rather than replaying
an old transcript implicitly. Structure reads are compact by default; selecting node
IDs exposes run offsets/styles. Edits return only changed/new nodes and removed IDs.
Native material reads include explicit page/image navigation and paginated search.
Long-template input paging and general history compaction
remain later work; oversize requests fail explicitly instead of silently dropping images.

On this macOS workstation use the Codex bundled renderer, not the broken Homebrew
`soffice` entrypoint. Check the existing CJK font fix after runtime upgrades.
Preview caching includes document content and renderer configuration; bump
`DOCTRANSAI_RENDER_REVISION` after changing fonts or other external render settings
not represented by `FONTCONFIG_FILE`.

### Focused tests

```bash
uv run pytest tests/llm tests/data_layer/test_bundle_reader.py \
  tests/documents tests/integration/test_document_tools.py -q
```

Real model acceptance is separate and should use the cases relevant to the current
development phase. See `docs/document-tools-architecture.md` and
`docs/test-coverage-inventory.md`. Do not treat the historical 392-test collection
or old sample reports as proof that the new path passes.
