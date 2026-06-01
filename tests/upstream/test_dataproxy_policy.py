from __future__ import annotations

from doctransai.upstream.dataproxy import DATAPROXY_UPSTREAM_POLICY


def test_dataproxy_upstream_policy_allows_imports_but_forbids_source_edits() -> None:
    assert DATAPROXY_UPSTREAM_POLICY["mode"] == "upstream_dependency"
    assert DATAPROXY_UPSTREAM_POLICY["may_import_dataproxy"] is True
    assert DATAPROXY_UPSTREAM_POLICY["may_modify_dataproxy_source"] is False
    assert DATAPROXY_UPSTREAM_POLICY["issue_handling"] == "report_to_project_owner"
