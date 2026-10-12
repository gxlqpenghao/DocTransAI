from __future__ import annotations

DATAPROXY_UPSTREAM_POLICY = {
    "mode": "upstream_dependency",
    "may_import_dataproxy": True,
    "may_modify_dataproxy_source": False,
    "issue_handling": "report_to_project_owner",
}
