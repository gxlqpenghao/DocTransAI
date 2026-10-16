"""Project-owned local renderer: LibreOffice layout + PDFium rasterization.

No Codex runtime, Office automation, shell expansion or Poppler dependency.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time


def resolve_soffice(explicit=None):
    selected = explicit or os.environ.get('DOCTRANSAI_SOFFICE')
    if selected:
        found = shutil.which(selected) or (str(Path(selected).expanduser().resolve()) if Path(selected).expanduser().is_file() else None)
        if not found:
            raise FileNotFoundError('DOCTRANSAI_SOFFICE does not point to a LibreOffice executable')
        return found
    candidates = []
    if sys.platform == 'win32':
        for key in ('ProgramFiles','ProgramFiles(x86)','LOCALAPPDATA'):
            if os.environ.get(key):
                candidates += [Path(os.environ[key])/'LibreOffice'/'program'/n for n in ('soffice.com','soffice.exe')]
    elif sys.platform == 'darwin':
        candidates += [Path('/Applications/LibreOffice.app/Contents/MacOS/soffice'),Path.home()/'Applications/LibreOffice.app/Contents/MacOS/soffice']
    for p in candidates:
        if p.is_file():return str(p)
    for name in ('soffice.com','soffice.exe') if sys.platform=='win32' else ('soffice','libreoffice'):
        found=shutil.which(name)
        if found:return found
    raise FileNotFoundError('Install LibreOffice Writer/Calc, or set DOCTRANSAI_SOFFICE to its executable')


def run_office(command, timeout, env):
    kwargs={'start_new_session':True} if os.name!='nt' else {'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP}
    with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,**kwargs) as process:
        try:
            out,err=process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10)
            else:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            process.kill();process.communicate()
            raise TimeoutError('LibreOffice conversion timed out; isolated process stopped')
        if process.returncode:
            raise RuntimeError('LibreOffice conversion failed: '+(err+out).decode('utf-8','replace')[-1000:])


def render_document(source, output_dir, *, soffice=None, timeout=110, emit_pdf=False, page_number=None, max_pixels=1800):
    import pypdfium2 as pdfium
    source=Path(source).resolve();target=Path(output_dir).resolve()
    if not source.is_file():raise FileNotFoundError(source)
    if source.suffix.lower() not in {'.docx','.xlsx','.doc','.xls','.pptx','.ppt','.pdf','.odt','.ods','.rtf'}:
        raise ValueError('Unsupported render input format')
    if timeout<=0 or max_pixels<128 or max_pixels>4096:raise ValueError('Invalid render limits')
    if page_number is not None and page_number<1:raise ValueError('Page numbers start at 1')
    target.mkdir(parents=True,exist_ok=True)
    if (target/(source.stem+'.pdf')).resolve()==source and emit_pdf:raise ValueError('Render output must not overwrite its input')
    if list(target.glob('page-*.png')):raise ValueError('Use an empty page output directory')
    deadline=time.monotonic()+timeout
    temp_base='/private/tmp' if sys.platform=='darwin' and Path('/private/tmp').is_dir() else None
    with tempfile.TemporaryDirectory(prefix='doctransai-render-',dir=temp_base) as tmp:
        work=Path(tmp);pdf=source
        if source.suffix.lower()!='.pdf':
            # Copy before conversion, never let an office process modify the caller's input.
            local=work/source.name;shutil.copy2(source,local)
            profile=work/'profile';env=os.environ.copy()
            if sys.platform=='darwin':
                env.update(TMPDIR='/private/tmp',TMP='/private/tmp',TEMP='/private/tmp')
                # Headless fontconfig must see macOS/user CJK fonts, including downloaded system fonts.
                import xml.etree.ElementTree as ET
                fontroot=ET.Element('fontconfig')
                dirs=[Path('/System/Library/Fonts'),Path('/Library/Fonts'),Path.home()/'Library/Fonts']
                for assets in (Path('/System/Library/Assets'),Path('/System/Library/AssetsV2')):
                    if assets.is_dir():dirs.extend(assets.glob('com_apple_MobileAsset_Font*'))
                for directory in dirs:
                    if directory.is_dir():ET.SubElement(fontroot,'dir').text=str(directory)
                cache=work/'font-cache';cache.mkdir();ET.SubElement(fontroot,'cachedir').text=str(cache)
                fontfile=work/'fonts.conf';ET.ElementTree(fontroot).write(fontfile,encoding='utf-8',xml_declaration=True)
                env['FONTCONFIG_FILE']=str(fontfile)
            command=[resolve_soffice(soffice),'-env:UserInstallation='+profile.as_uri(),'--headless','--nologo','--nodefault','--norestore','--convert-to','pdf','--outdir',str(work),str(local)]
            run_office(command,max(1,deadline-time.monotonic()),env)
            pdf=work/(source.stem+'.pdf')
            if not pdf.is_file() or not pdf.stat().st_size:raise RuntimeError('LibreOffice returned no PDF')
        staged=work/'pages';staged.mkdir()
        outputs=[]
        with pdfium.PdfDocument(str(pdf)) as document:
            count=len(document)
            if not 0<count<=500:raise ValueError('Rendered PDF page count must be 1..500')
            if page_number and page_number>count:raise ValueError('Requested page exceeds PDF page count')
            indexes=[page_number-1] if page_number else range(count)
            for index in indexes:
                if time.monotonic()>=deadline:raise TimeoutError('Page rendering deadline exceeded')
                page=document[index]
                try:
                    scale=max_pixels/max(page.get_size())
                    bitmap=page.render(scale=scale)
                    try:bitmap.to_pil().save(staged/f'page-{index+1}.png')
                    finally:bitmap.close()
                finally:page.close()
                outputs.append(f'page-{index+1}.png')
        # Publish only when all requested pages succeeded.
        for name in outputs:shutil.copy2(staged/name,target/name)
        if emit_pdf:shutil.copy2(pdf,target/(source.stem+'.pdf'))
        return {'page_count':count,'pages':[str(target/name) for name in outputs],'backend':'libreoffice-pdfium'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('--output_dir','--output-dir',type=Path,required=True)
    p.add_argument('--emit_pdf','--emit-pdf',action='store_true');p.add_argument('--soffice')
    p.add_argument('--timeout-seconds',type=float,default=110);p.add_argument('--page-number',type=int);p.add_argument('--max-pixels',type=int,default=1800)
    a=p.parse_args(argv)
    try:print(json.dumps(render_document(a.source,a.output_dir,soffice=a.soffice,timeout=a.timeout_seconds,emit_pdf=a.emit_pdf,page_number=a.page_number,max_pixels=a.max_pixels)));return 0
    except Exception as exc:print(f'{type(exc).__name__}: {exc}',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
