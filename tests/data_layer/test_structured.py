import base64
import json
from pathlib import Path

import pytest

from doctransai.data_layer.artifact import read_source_input
from doctransai.data_layer.structured import StructuredInputError, materialize_structured_bundle
from doctransai.data_layer.view import SourceView


def test_structured_payload_reuses_source_view_contract(tmp_path):
    image = tmp_path / "evidence.png"
    image.write_bytes(b"not-a-real-image-but-a-stable-test-asset")
    manifest = materialize_structured_bundle({
        "document_id": "danger-check-1",
        "records": [{
            "record_id": "hidden-1",
            "fields": {"项目名称": "桐金路一分部", "整改期限": "2026-11-24"},
            "images": [{"asset_id": "photo-1", "path": str(image), "caption": "围挡"}],
        }],
    }, tmp_path / "bundle")
    corpus = read_source_input(manifest, tmp_path / "run")
    source = SourceView(corpus, document_id="danger-check-1")
    assert source.read(refs=["structured:hidden-1:项目名称"])['objects'][0]['json_text']
    assert source.asset_path("photo-1").read_bytes() == image.read_bytes()
    initial = source.initial(10000)
    assert initial['document']['document_id'] == 'danger-check-1'
    assert initial['evidence_total'] == 2


def test_structured_payload_accepts_base64_and_rejects_duplicate_ids(tmp_path):
    manifest = materialize_structured_bundle({
        "records": [{"record_id": "r1", "fields": {"说明": "ok"},
                     "images": [{"asset_id": "p1", "base64": base64.b64encode(b"asset").decode()}]}]
    }, tmp_path / "bundle")
    assert manifest.is_file()
    assert (manifest.parent / 'assets').iterdir().__next__().read_bytes() == b'asset'
    with pytest.raises(StructuredInputError):
        materialize_structured_bundle({"records": [
            {"record_id": "r1", "fields": {}}, {"record_id": "r1", "fields": {}}
        ]}, tmp_path / "duplicate")
