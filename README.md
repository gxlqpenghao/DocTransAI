# DocTransAI

DocTransAI is a template-driven document transformation project. It ingests structured document bundles, maps source evidence into target templates, and renders traceable output documents.

The project keeps its runtime isolated from DataProxy. DataProxy v0 data-asset schemas are vendored as a local contract snapshot under `contracts/dataproxy/data_asset_pack_v0/`, and DocTransAI reads `parsed_document_bundle.json` through its own `doctransai.data_layer` package.

## Document tools path — DOCX and XLSX (v1.0.0rc1 candidate)

The new `convert` entrypoint uses native DataProxy evidence, a single model tool loop,
and DOCX/XLSX editors. It does not use the legacy source model, slot analyzer, mapping
planner, or RenderPlan. Legacy modules remain available for comparison.

v1 currently supports installation from a complete source checkout with `uv sync`.
Keep the `contracts/` directory alongside `src/`; standalone wheel distribution is
not supported yet. A missing known contract now fails explicitly instead of skipping validation.

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

Ordinary conversion is the bounded editor flow: it prepares DataProxy
materials and short-source visual context, submits edits, then automatically
renders the real current output before the next model check. Independent semantic review is explicit: add `--review` to
`convert`, or use the `review` command/API for an existing output. The
compatibility flag `--skip-review` remains accepted and has the same baseline
meaning as the default.

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

### Independent review and limited repair

When explicitly requested, `convert` runs independent review. The reviewer receives a fresh
context containing source materials, original template, current output and shared
application requirements; it receives no editor assurance or previous review verdict.
It has only read tools and `submit_review`. Findings include source/target roles and
explicit grounding assessments. The same configured model is used in a new context;
this is not independent human or ground-truth verification.

Default limits: 6 review steps, at most 1 repair round, 4 repair steps, and one shared
900-second wall-clock budget across editing, review, repair and re-review. Use
`--max-repair-rounds 0` for read-only review. Repairs are restricted to located findings
and allowed operations; unresolved ambiguity is not auto-repaired. Every successful
repair requires another fresh review. Pre-repair documents are retained in `revisions/`.

Review an existing output against its **original** template without regenerating it:

```bash
uv run doctransai review \
  --bundle /data/parsed_document_bundle.json \
  --source-file /data/source.docx \
  --template /data/original-template.docx \
  --document /data/existing-output.docx \
  --output-dir outputs/new-review \
  --instruction 'Complete the selected task using supported facts only' \
  --env-file /path/to/credentials.env
```

The Python equivalent is `review_document(task, document, config=...)` in
`doctransai.conversion`. Existing inputs are copied, not overwritten.

### Output and review meaning

- Reviewed outputs are `candidate.docx` / `candidate.xlsx`, including when the model
  reports no issues. `review_status=model_passed` means only the independent model
  reported a pass. Real testing found false negatives, so this is not an automatic
  release/acceptance signal.
- `needs_review` means findings or uncertainty remain. `incomplete` means a phase
  did not complete, including budget exhaustion after a repair; it never inherits
  the previous editor or reviewer success.
- `working.*` remains after an editing failure. Ordinary conversion and
  `convert --skip-review` produce `result.*` and `not_run`/`needs_review`; those
  outputs are not independently reviewed. `--review` and `review` produce
  `candidate.*` and a review status.
- `review.json` records all phases, coverage, findings, hashes, times and usage.
  `review-N.jsonl` and `repair-N.jsonl` retain separate tool traces without API keys
  or request-image base64. Unknown usage stays unknown. Acceptance metadata is
  bound to the exact reviewed output hash/version.
- CLI exit codes: 0 = completed with model-only pass (or explicit skip-review baseline),
  1 = execution failed, 2 = invalid configuration, 3 = review needs attention or is
  incomplete. None proves factual correctness.

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

XLSX uses the same entrypoint and seven tools, with format-specific edit schemas.
Supported operations: typed cell matrices, explicit formula edits, copying complete
row blocks into empty destinations, anchored image replacement/removal, formatting,
and print areas/repeated rows or columns. `s0!A3:Y8` addresses the first worksheet.
Formula cells are protected from ordinary writes; copied relative references are
translated without inserting rows or shifting other formulas. Formula caches are
recalculated on open, not independently evaluated by the Python editor.

XLSX edits retain custom XML package metadata. Macros, pivots, external links,
complex drawing shapes and unsupported extensions are rejected. Copying rows with
Excel tables, conditional formatting, data validation, links/comments or source
images requires additional adapters; the editor does not silently drop them.
Copy empty prototypes before attaching record-specific images. Existing validations,
other sheets and images are retained by ordinary cell edits.

Not yet supported: whole nested-table replacement,
floating textboxes or resume after process restart. Existing run directories are refused; use a new run rather than replaying
an old transcript implicitly. Structure reads are compact by default; selecting node
IDs exposes run offsets/styles. XLSX's default structure read lists used-range
metadata and non-empty cells; an exact range is required when blank cells or
their formatting matter. Edits return only changed/new nodes and removed IDs.
Native material reads include explicit page/image navigation and paginated search.
Long-template input paging and general history compaction
remain later work; oversize requests fail explicitly instead of silently dropping images.

For short DOC/DOCX/PDF sources, the initial context includes up to six rendered
source pages and up to twelve relevant native source images. Larger sources keep
on-demand page reads. After a successful edit, the program renders the current
output automatically; the model only needs `preview_document` for missing pages,
template inspection, or a deliberate follow-up check.

On this macOS workstation use the Codex bundled renderer, not the broken Homebrew
`soffice` entrypoint. Check the existing CJK font fix after runtime upgrades.
Preview caching includes document content and renderer configuration; bump
`DOCTRANSAI_RENDER_REVISION` after changing fonts or other external render settings
not represented by `FONTCONFIG_FILE`.

### Focused tests

```bash
uv run pytest tests/llm tests/data_layer/test_bundle_reader.py \
  tests/documents tests/integration/test_document_tools.py \
  tests/integration/test_independent_review.py -q
```

Real model acceptance is separate and should use the cases relevant to the current
development phase. See `docs/document-tools-architecture.md` and
`docs/test-coverage-inventory.md`. Do not treat the historical 392-test collection
or old sample reports as proof that the new path passes.
