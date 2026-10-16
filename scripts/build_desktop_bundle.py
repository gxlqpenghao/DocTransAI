"""Build a source delivery ZIP using a strict allowlist, never private configuration."""
from pathlib import Path
import argparse,hashlib,json,subprocess,zipfile


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('dist'));p.add_argument('--allow-dirty',action='store_true');p.add_argument('--windows-bootstrap',type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    state=subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True)
    if state and not a.allow_dirty:raise SystemExit('Commit changes before building a release (or use --allow-dirty for validation).')
    import tomllib
    version=tomllib.loads((root/'pyproject.toml').read_text())['project']['version']
    files=[]
    for name in ('src','contracts'):
        files += [x for x in (root/name).rglob('*') if x.is_file() and '__pycache__' not in x.parts and x.suffix not in ('.pyc','.log')]
    for name in ('scripts/setup-windows.ps1','scripts/build_desktop_bundle.py','docs/local-test-ui.md','docs/downstream-integration.md','docs/development-workflow.md','docs/desktop-deployment.md','README.md','pyproject.toml','uv.lock','.env.example','.python-version','Dockerfile','setup-windows.cmd','start-windows.cmd','setup-macos.command','start-macos.command'):
        if (root/name).is_file():files.append(root/name)
    # Only tracked/explicit deliverable directories above; no outputs, experiments, .env or Git history.
    for f in files:
        if f.name=='.env' or f.name.endswith('.secret'):raise SystemExit('Private file in package')
    a.output.mkdir(parents=True,exist_ok=True)
    name=f'DocTransAI-{version}-'+('windows-x64' if a.windows_bootstrap else 'desktop');archive=a.output/(name+'.zip')
    manifest={'version':version,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'validation_build':bool(state),'files':{str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    pending=archive.with_suffix('.zip.pending')
    with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED) as z:
        for f in files:z.write(f,name+'/'+str(f.relative_to(root)))
        if a.windows_bootstrap:
            expected={'python-windows.tar.gz':'a814e8406b698ad491e1073717d644479e86abf34a3d5897b4d581381b4b8164','uv-wheel.zip':'dcbc531a96762569bbfe9639b4f45f00aabff51f427540711f63e7c23f225fdf'}
            for filename,digest in expected.items():
                source=a.windows_bootstrap/filename
                if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise SystemExit('Bootstrap checksum mismatch: '+filename)
                path='runtime/bootstrap/'+filename;z.write(source,name+'/'+path);manifest['files'][path]=digest
        z.writestr(name+'/delivery-manifest.json',json.dumps(manifest,indent=2))
    pending.replace(archive)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest();archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n')
    print(archive.resolve());print(digest)
if __name__=='__main__':main()
