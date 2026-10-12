"""Consume the official parse_artifact package without rewriting source evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

from jsonschema import Draft202012Validator

from .bundle_reader import read_parsed_document_bundle


def package_path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or '\\' in name or re.match(r'^[A-Za-z]:', name):
        raise ValueError('Invalid package resource path')
    parts = PurePosixPath(name)
    if parts.is_absolute() or '..' in parts.parts:
        raise ValueError('Package resource escapes package root')
    path = root.joinpath(*parts.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Package resource escapes package root')
    return path


def unpack_artifact(archive: Path, destination: Path, *, max_bytes=1024**3, max_files=20000) -> Path:
    """Bounded extraction into a new directory; never overwrite a prior task."""
    if destination.exists():
        raise ValueError('Package destination already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        root = Path(tmp) / 'package'
        root.mkdir()
        with zipfile.ZipFile(archive) as z:
            entries = z.infolist()
            if len(entries) > max_files or sum(e.file_size for e in entries) > max_bytes:
                raise ValueError('Parse package exceeds extraction limits')
            seen = set()
            for e in entries:
                target = package_path(root, e.filename)
                key = str(target.relative_to(root)).casefold()
                mode = e.external_attr >> 16
                if key in seen or stat.S_ISLNK(mode):
                    raise ValueError('Duplicate path or symbolic link in parse package')
                seen.add(key)
                if e.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(e) as src, target.open('xb') as dst:
                        shutil.copyfileobj(src, dst)
        read_artifact(root / 'manifest.json')
        root.rename(destination)
    return destination / 'manifest.json'


def _hash(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read_artifact(manifest_path: Path):
    manifest_path = manifest_path.resolve()
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    schema = json.loads((Path(__file__).parent / 'contracts/parse_artifact_manifest.schema.json').read_text())
    Draft202012Validator(schema).validate(manifest)
    quality = manifest['quality']
    if quality['status'] == 'failed' or quality['parse_errors']:
        raise ValueError('DataProxy parse quality failed')
    if quality['status'] == 'complete' and (quality['missing_components'] or quality['warnings'] or not quality['complete']):
        raise ValueError('Inconsistent DataProxy quality status')
    checked = set()
    for entry in manifest['integrity']['files']:
        path = package_path(root, entry['path'])
        if path in checked or not path.is_file():
            raise ValueError('Missing or duplicate package integrity entry')
        checked.add(path)
        if path.stat().st_size != entry['size_bytes'] or _hash(path) != entry['sha256']:
            raise ValueError(f'Package integrity mismatch: {entry["path"]}')
    def required(name):
        p = package_path(root, name)
        if p not in checked:
            raise ValueError(f'Unverified package resource: {name}')
        return p
    for schema_path in manifest.get("schemas", {}).values():
        required(schema_path)
    for source in manifest['source']:
        p = required(source['path'])
        if source['sha256'] != _hash(p) or source['size_bytes'] != p.stat().st_size:
            raise ValueError('Source integrity mismatch')
    for component in manifest['components'].values():
        if component['delivered'] and component['path'] != 'manifest.json':
            required(component['path'])
    entry = manifest['entrypoints']['parsed_document_bundle']
    required(entry['schema_path'])
    bundle = required(entry['path'])
    raw = json.loads(bundle.read_text())
    if raw['contract_version'] != entry['contract_version']:
        raise ValueError('Inner contract does not match manifest')
    for descriptor in raw['components'].values():
        required(descriptor['path'])
    for path in raw.get('reports', {}).values():
        required(path)
    corpus = read_parsed_document_bundle(bundle, resource_root=root)
    for document in corpus.documents + corpus.source_manifest:
        if document.get("source_path"):
            required(document["source_path"])
    for asset in corpus.visual_assets:
        if asset.get("source_ref"):
            required(asset["source_ref"])
    corpus.artifact_manifest = manifest
    return corpus


def read_source_input(path: Path, work_dir: Path):
    if path.suffix.lower() == '.zip':
        path = unpack_artifact(path, work_dir / 'source-package')
    if path.is_dir():
        path = path / 'manifest.json'
    if path.name == 'manifest.json':
        return read_artifact(path)
    return read_parsed_document_bundle(path)
