from pathlib import Path
import sys
import time
import pytest
from doctransai.config import RuntimeConfig
from doctransai.render_document import render_document,resolve_soffice,run_office


def test_default_renderer_is_project_owned():
    c=RuntimeConfig()
    assert c.render_script.name=='render_document.py' and c.render_script.is_file()
    assert c.render_python==sys.executable


def test_explicit_invalid_office_does_not_silently_fallback(tmp_path):
    with pytest.raises(FileNotFoundError):resolve_soffice(str(tmp_path/'missing-soffice'))


def test_native_windows_office_detection(tmp_path,monkeypatch):
    import doctransai.render_document as mod
    path=tmp_path/'LibreOffice/program/soffice.com';path.parent.mkdir(parents=True);path.write_bytes(b'test')
    monkeypatch.delenv('DOCTRANSAI_SOFFICE',raising=False);monkeypatch.setenv('ProgramFiles',str(tmp_path));monkeypatch.setattr(mod.sys,'platform','win32')
    assert resolve_soffice()==str(path)


def test_pdfium_page_selection_without_libreoffice(tmp_path):
    import pypdfium2 as pdfium
    source=tmp_path/'中文 路径.pdf'
    with pdfium.PdfDocument.new() as doc:
        p=doc.new_page(200,300);p.close();p=doc.new_page(300,200);p.close();doc.save(source)
    before=source.read_bytes()
    result=render_document(source,tmp_path/'png',page_number=2,soffice='/missing',emit_pdf=True)
    assert result['page_count']==2 and [Path(x).name for x in result['pages']]==['page-2.png']
    from PIL import Image
    with Image.open(result['pages'][0]) as im:assert max(im.size)<=1801
    assert source.read_bytes()==before
    with pytest.raises(ValueError,match='exceeds'):render_document(source,tmp_path/'bad',page_number=3)
    assert not list((tmp_path/'bad').glob('page-*.png'))


def test_office_timeout_is_bounded():
    import os
    start=time.monotonic()
    with pytest.raises(TimeoutError):run_office([sys.executable,'-c','import time;time.sleep(10)'],.1,os.environ.copy())
    assert time.monotonic()-start<5


def test_renderer_env_file_only_needs_optional_office_path(tmp_path):
    f=tmp_path/'backend.env';f.write_text('DOCTRANSAI_SOFFICE=C:/Program Files/LibreOffice/program/soffice.com\n')
    cfg=RuntimeConfig.from_environment(env_file=f)
    assert cfg.soffice.startswith('C:/Program Files/') and cfg.render_script.name=='render_document.py'


def test_previewer_uses_module_entrypoint_not_types_shadowing(tmp_path):
    import pypdfium2
    from doctransai.documents.preview import Previewer
    source=tmp_path/'input.pdf'
    with pypdfium2.PdfDocument.new() as pdf:
        page=pdf.new_page(200,300);page.close();pdf.save(source)
    pages=Previewer(tmp_path/'cache',RuntimeConfig()).render(source)
    assert len(pages)==1 and pages[0].is_file()
    assert Previewer(tmp_path/'cache',RuntimeConfig()).render(source)==pages


def test_desktop_reuses_running_server_without_touching_jobs(monkeypatch):
    import io
    from doctransai import desktop
    monkeypatch.setattr(desktop,'urlopen',lambda *a,**k:io.BytesIO(b'{"application":"DocTransAI"}'))
    monkeypatch.setattr(desktop,'LocalApp',lambda *a,**k:pytest.fail('must not rewrite active job state'))
    assert desktop.main(['--no-browser'])==0


def test_missing_env_is_actionable_without_traceback(tmp_path):
    from doctransai.doctor import checks
    result=checks(tmp_path/'missing.env',True)
    assert not result[0]['ok'] and 'Copy .env.example' in result[0]['detail']
