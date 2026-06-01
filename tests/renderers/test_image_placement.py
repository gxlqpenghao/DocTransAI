from __future__ import annotations

from pathlib import Path

from PIL import Image

from doctransai.models.render_plan import ImagePlacement, TargetRef
from doctransai.renderers import ImageSize, RenderDiagnostic, RenderResult, resolve_image_placement, resolve_image_size


def test_resolve_image_placement_uses_bundle_relative_source_ref(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    asset_path = bundle_dir / "final_images" / "photo-1.png"
    asset_path.parent.mkdir(parents=True)
    Image.new("RGB", (640, 480), color="red").save(asset_path)

    resolved = resolve_image_placement(
        ImagePlacement(
            slot_id="slot-photo",
            asset_id="asset-1",
            source_ref="final_images/photo-1.png",
            target=TargetRef(format_key="docx", target_kind="image_placeholder"),
            sizing_policy="contain",
        ),
        bundle_dir=bundle_dir,
        target_width=320,
        target_height=320,
    )

    assert resolved.asset_path == asset_path.resolve()
    assert resolved.intrinsic_size == ImageSize(width=640.0, height=480.0)
    assert resolved.render_size == ImageSize(width=320.0, height=240.0)
    assert resolved.diagnostics == []


def test_resolve_image_placement_uses_parsed_checksum_subdirectory_when_available(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    asset_path = bundle_dir / "parsed" / "abc123" / "final_images" / "photo-2.png"
    asset_path.parent.mkdir(parents=True)
    Image.new("RGB", (400, 200), color="blue").save(asset_path)

    resolved = resolve_image_placement(
        ImagePlacement(
            slot_id="slot-photo",
            asset_id="asset-2",
            source_ref="final_images/photo-2.png",
            target=TargetRef(format_key="xlsx", target_kind="image_placeholder"),
            sizing_policy="original",
        ),
        bundle_dir=bundle_dir,
        source_checksum="abc123",
    )

    assert resolved.asset_path == asset_path.resolve()
    assert resolved.render_size == ImageSize(width=400.0, height=200.0)
    assert resolved.diagnostics == []


def test_resolve_image_placement_globs_parsed_subdirectory_without_checksum(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    asset_path = bundle_dir / "parsed" / "abc123" / "final_images" / "photo-3.png"
    asset_path.parent.mkdir(parents=True)
    Image.new("RGB", (300, 150), color="purple").save(asset_path)

    resolved = resolve_image_placement(
        ImagePlacement(
            slot_id="slot-photo",
            asset_id="asset-3",
            source_ref="final_images/photo-3.png",
            target=TargetRef(format_key="docx", target_kind="image_placeholder"),
            sizing_policy="original",
        ),
        bundle_dir=bundle_dir,
    )

    assert resolved.asset_path == asset_path.resolve()
    assert resolved.render_size == ImageSize(width=300.0, height=150.0)
    assert resolved.diagnostics == []


def test_resolve_image_placement_accepts_absolute_paths(tmp_path: Path) -> None:
    asset_path = tmp_path / "absolute-photo.png"
    Image.new("RGB", (120, 60), color="green").save(asset_path)

    resolved = resolve_image_placement(
        ImagePlacement(
            slot_id="slot-photo",
            asset_id="asset-3",
            source_ref=str(asset_path),
            target=TargetRef(format_key="pdf", target_kind="image_placeholder"),
            sizing_policy="max_width",
        ),
        max_width=80,
    )

    assert resolved.asset_path == asset_path.resolve()
    assert resolved.render_size == ImageSize(width=80.0, height=40.0)


def test_resolve_image_placement_returns_clear_missing_asset_diagnostic(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()

    resolved = resolve_image_placement(
        ImagePlacement(
            slot_id="slot-photo",
            asset_id="asset-404",
            source_ref="final_images/missing.png",
            target=TargetRef(format_key="docx", target_kind="image_placeholder"),
            sizing_policy="contain",
        ),
        bundle_dir=bundle_dir,
        source_checksum="abc123",
    )

    assert resolved.asset_path is None
    assert resolved.render_size is None
    assert resolved.diagnostics == [
        RenderDiagnostic(
            severity="error",
            code="missing_asset",
            message=(
                "Image asset for slot slot-photo was not found at "
                "'final_images/missing.png' in bundle_dir/source_ref or bundle_dir/<checksum>/source_ref."
            ),
            slot_id="slot-photo",
            asset_id="asset-404",
            source_ref="final_images/missing.png",
        )
    ]


def test_resolve_image_size_supports_all_renderer_policies() -> None:
    intrinsic = ImageSize(width=1200.0, height=600.0)

    assert resolve_image_size(intrinsic, sizing_policy="fit_cell", target_width=300, target_height=150) == ImageSize(
        width=300.0,
        height=150.0,
    )
    assert resolve_image_size(intrinsic, sizing_policy="contain", target_width=300, target_height=300) == ImageSize(
        width=300.0,
        height=150.0,
    )
    assert resolve_image_size(intrinsic, sizing_policy="original") == intrinsic
    assert resolve_image_size(intrinsic, sizing_policy="max_width", max_width=500) == ImageSize(
        width=500.0,
        height=250.0,
    )


def test_render_result_is_successful_without_error_diagnostics() -> None:
    clean = RenderResult(output_path="/tmp/output.docx")
    failed = RenderResult(
        output_path="/tmp/output.docx",
        diagnostics=[
            RenderDiagnostic(
                severity="error",
                code="missing_asset",
                message="Asset missing",
            )
        ],
    )

    assert clean.is_successful is True
    assert failed.is_successful is False
