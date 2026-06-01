from __future__ import annotations

from dataclasses import dataclass
import posixpath
from pathlib import Path
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET


_IMAGE_RELATIONSHIP_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DRAWING_TAG_PATTERN = re.compile(rb"<(?:[A-Za-z0-9_]+:)?drawing\b")


@dataclass(slots=True, frozen=True)
class DocxMediaUsage:
    media_parts: frozenset[str]
    referenced_media_parts: frozenset[str]
    orphan_media_parts: frozenset[str]
    drawing_count: int


def inspect_docx_media_usage(docx_path: str | Path) -> DocxMediaUsage:
    path = Path(docx_path).expanduser()
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        media_parts = frozenset(name for name in names if name.startswith("word/media/"))
        referenced_media_parts = frozenset(_referenced_media_parts(archive, names))
        drawing_count = _drawing_count(archive, names)

    return DocxMediaUsage(
        media_parts=media_parts,
        referenced_media_parts=referenced_media_parts,
        orphan_media_parts=frozenset(media_parts - referenced_media_parts),
        drawing_count=drawing_count,
    )


def prune_unreferenced_docx_media_parts(docx_path: str | Path) -> int:
    path = Path(docx_path).expanduser()
    usage = inspect_docx_media_usage(path)
    if not usage.orphan_media_parts:
        return 0

    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        contents = {
            name: _relationship_payload_without_orphan_media(
                rels_name=name,
                payload=archive.read(name),
                names=names,
                orphan_media_parts=usage.orphan_media_parts,
            )
            for name in names
            if name not in usage.orphan_media_parts
        }

    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx", dir=path.parent) as handle:
        temp_path = Path(handle.name)

    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in contents.items():
                archive.writestr(name, payload)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    return len(usage.orphan_media_parts)


def _referenced_media_parts(archive: zipfile.ZipFile, names: list[str]) -> set[str]:
    referenced: set[str] = set()
    name_set = set(names)
    for rels_name in names:
        if not rels_name.endswith(".rels") or "/_rels/" not in rels_name:
            continue
        source_part = _source_part_for_relationships_part(rels_name)
        if source_part is None or source_part not in name_set:
            continue
        source_xml = archive.read(source_part)
        rels_root = ET.fromstring(archive.read(rels_name))
        for relationship in rels_root:
            if _relationship_type(relationship) != _IMAGE_RELATIONSHIP_TYPE:
                continue
            rel_id = relationship.get("Id")
            target = relationship.get("Target")
            if not rel_id or not target or relationship.get("TargetMode") == "External":
                continue
            if rel_id.encode("utf-8") not in source_xml:
                continue
            media_part = _resolve_relationship_target(source_part, target)
            if media_part.startswith("word/media/"):
                referenced.add(media_part)
    return referenced


def _relationship_payload_without_orphan_media(
    *,
    rels_name: str,
    payload: bytes,
    names: list[str],
    orphan_media_parts: frozenset[str],
) -> bytes:
    if not orphan_media_parts or not rels_name.endswith(".rels") or "/_rels/" not in rels_name:
        return payload

    source_part = _source_part_for_relationships_part(rels_name)
    if source_part is None or source_part not in set(names):
        return payload

    root = ET.fromstring(payload)
    removed = False
    for relationship in list(root):
        if _relationship_type(relationship) != _IMAGE_RELATIONSHIP_TYPE:
            continue
        target = relationship.get("Target")
        if not target or relationship.get("TargetMode") == "External":
            continue
        media_part = _resolve_relationship_target(source_part, target)
        if media_part not in orphan_media_parts:
            continue
        root.remove(relationship)
        removed = True

    if not removed:
        return payload
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _source_part_for_relationships_part(rels_name: str) -> str | None:
    prefix, _, rel_file = rels_name.partition("/_rels/")
    if not prefix or not rel_file.endswith(".rels"):
        return None
    return f"{prefix}/{rel_file[:-5]}"


def _relationship_type(element: ET.Element) -> str | None:
    return element.get("Type")


def _resolve_relationship_target(source_part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    base_dir = posixpath.dirname(source_part)
    return posixpath.normpath(posixpath.join(base_dir, target))


def _drawing_count(archive: zipfile.ZipFile, names: list[str]) -> int:
    count = 0
    for name in names:
        if not name.startswith("word/") or not name.endswith(".xml") or "/_rels/" in name:
            continue
        count += len(_DRAWING_TAG_PATTERN.findall(archive.read(name)))
    return count


__all__ = [
    "DocxMediaUsage",
    "inspect_docx_media_usage",
    "prune_unreferenced_docx_media_parts",
]
