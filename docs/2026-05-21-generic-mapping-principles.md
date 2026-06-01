# Generic Mapping Principles

> **For agentic workers:** The target DocTransAI architecture must not depend on domain field packs. Do not turn business-specific field dictionaries, aliases, or slot-name heuristics into core control flow.

**Goal:** Define the long-term mapping architecture for arbitrary templates while keeping LLM usage narrow, efficient, and optional.

**Architecture:** `SourceModel` and `TemplateModel` are generic structures. Non-LLM mapping must remain generic and structural: type inference, structural candidate preparation, generic constraint checks, and deterministic narrowing. LLM is used only for unresolved or ambiguous slots after deterministic narrowing.

**Tech Stack:** Python 3.12, structured models, generic value-shape checks, optional LLM batch resolver with strict JSON output.

---

## 1. Hard Rules

- No domain field packs in the core mapping path.
- No business-specific alias dictionaries in the core resolver.
- No template-specific hardcoded slot names in renderer or planner.
- No one-slot-per-LLM-call architecture.
- No LLM access to raw source documents when `ParsedDocumentBundle v0` already exists.

## 2. Allowed Non-LLM Inputs

Generic non-LLM mapping may use only:

- `TemplateSlot.raw_name`, `canonical_name`, `slot_kind`, and local context.
- `SlotAddress` and repeat/header region structure.
- `SourceRecord` structure: same row, same table, same section, same page, same sheet.
- Generic value-shape signals: date-like, phone-like, person-like, org-like, identifier-like, image-like.
- Generic proximity signals: adjacent header, same row, same cell range family, related evidence link, image anchor.

## 3. Target Mapping Pipeline

```text
SourceModel
-> type_inference
-> structural_candidate_preparation
-> generic_constraint_checks
-> high_confidence_rule_resolution
-> ambiguous_batch_to_agent
-> RenderPlan
```

## 4. Role Of The LLM

The LLM is not the extractor and not the renderer.

It should receive only:

- one batch of unresolved/ambiguous slots,
- top-k candidates per slot,
- compact structural/context features,
- strict JSON schema for the decision.

In the common case of one source bundle and one template, this does not mean “retrieval” in the RAG sense. The whole typed context can stay in memory; the deterministic stage only reduces noise before the LLM sees it.

It should return only:

- chosen candidate id,
- optional generated text,
- confidence,
- rationale,
- unresolved when uncertain.

## 5. Transitional Status

Current repository still contains V1 transitional helpers such as:

- parts of `src/doctransai/mapping/planner.py`
- parts of `src/doctransai/mapping/image_mapper.py`

These are acceptable for short-cycle validation only. They must not be treated as the target architecture.

## 6. Reserved Next-Step Modules

These modules are the intended landing zone for the generic architecture:

- `src/doctransai/mapping/type_inference.py`
- `src/doctransai/mapping/structural_candidates.py`
- `src/doctransai/mapping/constraint_checks.py`
- `src/doctransai/mapping/agent_resolver.py`
- `src/doctransai/mapping/orchestrator.py`

## 7. Success Criterion

The architecture is on the right track when:

- a new template can be analyzed and partially matched without adding business-specific field code,
- deterministic mapping resolves obvious slots from structure and value shape,
- LLM is called rarely and in batches,
- unresolved slots remain explicit instead of being guessed.
