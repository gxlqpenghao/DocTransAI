from __future__ import annotations

from pathlib import Path

from PIL import Image

from doctransai.models.render_plan import ImagePlacement
from doctransai.renderers.models import ImageSize, RenderDiagnostic, ResolvedImagePlacement


def resolve_image_placement(
    placement: ImagePlacement,
    *,
    bundle_dir: str | Path | None = None,
    source_bundle_path: str | Path | None = None,
    source_checksum: str | None = None,
    target_width: float | None = None,
    target_height: float | None = None,
    max_width: float | None = None,
) -> ResolvedImagePlacement:
    asset_path = resolve_asset_path(
        placement.source_ref,
        bundle_dir=bundle_dir,
        source_bundle_path=source_bundle_path,
        source_checksum=source_checksum,
    )
    if asset_path is None:
        return ResolvedImagePlacement(
            slot_id=placement.slot_id,
            asset_id=placement.asset_id,
            source_ref=placement.source_ref,
            asset_path=None,
            diagnostics=[_missing_asset_diagnostic(placement)],
        )

    with Image.open(asset_path) as image:
        intrinsic_size = ImageSize(width=float(image.width), height=float(image.height))

    return ResolvedImagePlacement(
        slot_id=placement.slot_id,
        asset_id=placement.asset_id,
        source_ref=placement.source_ref,
        asset_path=asset_path,
        intrinsic_size=intrinsic_size,
        render_size=resolve_image_size(
            intrinsic_size,
            sizing_policy=placement.sizing_policy,
            target_width=target_width,
            target_height=target_height,
            max_width=max_width,
        ),
    )


def resolve_asset_path(
    source_ref: str | None,
    *,
    bundle_dir: str | Path | None = None,
    source_bundle_path: str | Path | None = None,
    source_checksum: str | None = None,
) -> Path | None:
    if not source_ref:
        return None

    ref_path = Path(source_ref).expanduser()
    if ref_path.is_absolute():
        return ref_path.resolve() if ref_path.exists() else None

    resolved_bundle_dir = _resolve_bundle_dir(bundle_dir=bundle_dir, source_bundle_path=source_bundle_path)
    if resolved_bundle_dir is None:
        return None

    parsed_checksum_candidate = resolved_bundle_dir / "parsed" / source_checksum / source_ref if source_checksum else None
    checksum_candidate = resolved_bundle_dir / source_checksum / source_ref if source_checksum else None
    direct_candidate = resolved_bundle_dir / source_ref

    if parsed_checksum_candidate is not None and parsed_checksum_candidate.exists():
        return parsed_checksum_candidate.resolve()
    if checksum_candidate is not None and checksum_candidate.exists():
        return checksum_candidate.resolve()
    if direct_candidate.exists():
        return direct_candidate.resolve()
    parsed_glob_candidates = list((resolved_bundle_dir / "parsed").glob(f"*/{source_ref}"))
    for parsed_candidate in parsed_glob_candidates:
        if parsed_candidate.exists():
            return parsed_candidate.resolve()
    return None


def resolve_image_size(
    intrinsic_size: ImageSize,
    *,
    sizing_policy: str,
    target_width: float | None = None,
    target_height: float | None = None,
    max_width: float | None = None,
) -> ImageSize:
    _validate_image_size(intrinsic_size)

    if sizing_policy == "fit_cell":
        return _fit_cell_size(intrinsic_size, target_width=target_width, target_height=target_height)
    if sizing_policy == "contain":
        return _contain_size(intrinsic_size, target_width=target_width, target_height=target_height)
    if sizing_policy == "original":
        return intrinsic_size
    if sizing_policy == "max_width":
        return _max_width_size(intrinsic_size, max_width=max_width, target_width=target_width)
    raise ValueError(f"Unsupported sizing_policy: {sizing_policy}")


def _resolve_bundle_dir(*, bundle_dir: str | Path | None, source_bundle_path: str | Path | None) -> Path | None:
    if bundle_dir is not None:
        return Path(bundle_dir).expanduser()
    if source_bundle_path is None:
        return None
    return Path(source_bundle_path).expanduser().resolve().parent


def _missing_asset_diagnostic(placement: ImagePlacement) -> RenderDiagnostic:
    if placement.source_ref:
        message = (
            f"Image asset for slot {placement.slot_id} was not found at "
            f"'{placement.source_ref}' in bundle_dir/source_ref or bundle_dir/<checksum>/source_ref."
        )
    else:
        message = f"Image placement for slot {placement.slot_id} does not include a source_ref."

    return RenderDiagnostic(
        severity="error",
        code="missing_asset",
        message=message,
        slot_id=placement.slot_id,
        asset_id=placement.asset_id,
        source_ref=placement.source_ref,
    )


def _validate_image_size(size: ImageSize) -> None:
    if size.width <= 0 or size.height <= 0:
        raise ValueError("Image dimensions must be positive.")


def _fit_cell_size(
    intrinsic_size: ImageSize,
    *,
    target_width: float | None,
    target_height: float | None,
) -> ImageSize:
    if target_width is not None and target_height is not None:
        return ImageSize(width=float(target_width), height=float(target_height))
    return _contain_size(intrinsic_size, target_width=target_width, target_height=target_height)


def _contain_size(
    intrinsic_size: ImageSize,
    *,
    target_width: float | None,
    target_height: float | None,
) -> ImageSize:
    if target_width is None and target_height is None:
        return intrinsic_size

    ratios: list[float] = []
    if target_width is not None:
        ratios.append(float(target_width) / intrinsic_size.width)
    if target_height is not None:
        ratios.append(float(target_height) / intrinsic_size.height)

    scale = min(ratios)
    return ImageSize(
        width=intrinsic_size.width * scale,
        height=intrinsic_size.height * scale,
    )


def _max_width_size(
    intrinsic_size: ImageSize,
    *,
    max_width: float | None,
    target_width: float | None,
) -> ImageSize:
    width_limit = float(max_width) if max_width is not None else float(target_width) if target_width is not None else None
    if width_limit is None or intrinsic_size.width <= width_limit:
        return intrinsic_size

    scale = width_limit / intrinsic_size.width
    return ImageSize(width=width_limit, height=intrinsic_size.height * scale)
