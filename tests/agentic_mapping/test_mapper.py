from __future__ import annotations

import json
from pathlib import Path

from doctransai.agentic_mapping.mapper import AgentDecision, map_slots_with_agent


def test_map_slots_with_agent_sends_evidence_package_to_keyword_client() -> None:
    calls: list[dict[str, str]] = []

    def fake_client(*, system_prompt: str, user_prompt: str) -> str:
        calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        return json.dumps(
            {
                "decisions": [
                    {
                        "slot_id": "slot-project",
                        "decision": "text_fill",
                        "value": "智慧园区改造",
                        "source_refs": ["record/project-name"],
                        "target_ref": {"format_key": "docx", "target_kind": "placeholder", "paragraph_index": 2},
                        "confidence": 0.93,
                        "reason": "source structured record directly supports this fill",
                    }
                ]
            },
            ensure_ascii=False,
        )

    evidence_package = {
        "source_structured": {"records": [{"object_id": "record/project-name", "value": "智慧园区改造"}]},
        "source_page_images": [{"page_index": 0, "image_ref": "/pages/source-1.png"}],
        "template_structured": {"slots": [{"slot_id": "slot-project", "raw_name": "项目名称"}]},
        "template_page_images": [{"page_index": 0, "image_ref": "/pages/template-1.png"}],
    }

    decisions = map_slots_with_agent(evidence_package, decision_client=fake_client)

    assert len(calls) == 1
    assert "source structured content" in calls[0]["system_prompt"]
    assert "source page render images" in calls[0]["system_prompt"]
    assert "template structured content" in calls[0]["system_prompt"]
    assert "template page render images" in calls[0]["system_prompt"]
    assert "INPUT_JSON:" in calls[0]["user_prompt"]
    payload = json.loads(calls[0]["user_prompt"].split("INPUT_JSON:", 1)[1])
    assert payload == {"evidence_package": evidence_package}

    assert decisions == [
        AgentDecision(
            slot_id="slot-project",
            decision_type="text_fill",
            value="智慧园区改造",
            asset_ref=None,
            source_refs=["record/project-name"],
            target_ref={"format_key": "docx", "target_kind": "placeholder", "paragraph_index": 2},
            confidence=0.93,
            reason="source structured record directly supports this fill",
        )
    ]


def test_map_slots_with_agent_accepts_top_level_decision_list() -> None:
    decisions = map_slots_with_agent(
        {"template_structured": {"slots": []}},
        decision_client=lambda **_: [
            {
                "slot_id": "slot-missing",
                "decision": "unresolved",
                "reason_code": "missing_source_evidence",
                "message": "No source evidence.",
            }
        ],
    )

    assert decisions[0].slot_id == "slot-missing"
    assert decisions[0].decision_type == "unresolved"
    assert decisions[0].reason == "No source evidence."


def test_map_slots_with_agent_sends_existing_page_images_as_user_parts(tmp_path: Path) -> None:
    page_image = tmp_path / "page.png"
    page_image.write_bytes(b"image-bytes")
    calls: list[dict[str, object]] = []

    def fake_client(**kwargs):
        calls.append(kwargs)
        return [
            {
                "slot_id": "slot-missing",
                "decision": "unresolved",
                "reason": "No source evidence.",
            }
        ]

    map_slots_with_agent(
        {
            "source": {"page_images": [{"image_ref": str(page_image)}]},
            "template": {"page_images": [{"image_ref": "/missing/template-page.png"}]},
        },
        decision_client=fake_client,
    )

    user_parts = calls[0]["user_parts"]
    assert user_parts[0]["type"] == "text"
    assert user_parts[1]["type"] == "image_url"
    assert user_parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert len(user_parts) == 2
