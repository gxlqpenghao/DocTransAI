from __future__ import annotations

from pathlib import Path

from doctransai.data_layer.models import ComponentFile, SourceCorpus
from doctransai.validation.bundle_gate import evaluate_bundle_gate


def _corpus_with_diagnostics(*diagnostics: dict[str, object]) -> SourceCorpus:
    return SourceCorpus(
        bundle_path=Path("/bundle/parsed_document_bundle.json"),
        contract_version="data_asset_pack_v0",
        capabilities={"diagnostics": True},
        summary={"diagnostic_count": len(diagnostics)},
        documents=[],
        parse_errors=[],
        components={
            "diagnostics": ComponentFile(
                name="diagnostics",
                path=Path("/bundle/diagnostics.jsonl"),
                count=len(diagnostics),
                records=list(diagnostics),
            )
        },
        reports={},
        raw_manifest={},
    )


def test_bundle_gate_warns_when_diagnostics_meet_threshold() -> None:
    corpus = _corpus_with_diagnostics(
        {
            "diagnostic_id": "diag-1",
            "severity": "error",
            "code": "missing_block_inventory",
            "message": "block inventory is incomplete",
            "phase": "fresh_validation",
            "producer": "fixture",
        }
    )

    result = evaluate_bundle_gate(corpus, minimum_severity="warning", on_trigger="warn")

    assert result.action == "warn"
    assert [finding.diagnostic_id for finding in result.findings] == ["diag-1"]


def test_bundle_gate_fails_when_diagnostics_meet_threshold() -> None:
    corpus = _corpus_with_diagnostics(
        {
            "diagnostic_id": "diag-2",
            "severity": "warning",
            "code": "paired_validation_gap",
            "message": "paired validation found a gap",
            "phase": "fresh_validation",
            "producer": "fixture",
        }
    )

    result = evaluate_bundle_gate(corpus, minimum_severity="warning", on_trigger="fail")

    assert result.action == "fail"
    assert result.blocked is True


def test_bundle_gate_ignores_diagnostics_below_threshold() -> None:
    corpus = _corpus_with_diagnostics(
        {
            "diagnostic_id": "diag-3",
            "severity": "info",
            "code": "parser_hint",
            "message": "minor parser hint",
            "phase": "fresh_validation",
            "producer": "fixture",
        },
        {
            "diagnostic_id": "diag-4",
            "severity": None,
            "code": "missing_severity",
            "message": "severity was not set",
            "phase": "fresh_validation",
            "producer": "fixture",
        },
    )

    result = evaluate_bundle_gate(corpus, minimum_severity="warning", on_trigger="fail")

    assert result.action == "allow"
    assert result.findings == []
