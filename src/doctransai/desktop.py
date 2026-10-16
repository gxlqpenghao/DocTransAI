"""Double-click launcher target; owns only its local loopback server."""
import argparse
import json
from pathlib import Path
import threading
from urllib.request import urlopen
import webbrowser
from .doctor import checks
from .web import LocalApp,make_server


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--env-file',type=Path,default=Path('.env'));p.add_argument('--port',type=int,default=8765);p.add_argument('--runs-dir',type=Path,default=Path('outputs/web'));p.add_argument('--no-browser',action='store_true');a=p.parse_args(argv)
    url=f'http://127.0.0.1:{a.port}'
    # Do not create LocalApp before checking the existing server: it marks stale jobs interrupted.
    try:
        with urlopen(url+'/api/config',timeout=2) as r:data=json.load(r)
        if data.get('application')=='DocTransAI':
            if not a.no_browser:webbrowser.open(url)
            print('DocTransAI is already running: '+url);return 0
    except Exception:pass
    rows=checks(a.env_file,True)
    for row in rows:print(('OK  ' if row['ok'] else 'FAIL ')+row['name']+': '+row['detail'])
    if not all(r['ok'] for r in rows):return 1
    # Bind first, so a port conflict cannot mark another instance's jobs interrupted.
    import socket
    with socket.socket() as probe:
        try:probe.bind(('127.0.0.1',a.port))
        except OSError:print('Port is in use; close the other service or choose --port.');return 1
    app=LocalApp(a.runs_dir,a.env_file)
    server=make_server(app,a.port)
    if not a.no_browser:threading.Timer(.5,lambda:webbrowser.open(url)).start()
    print('DocTransAI: '+url+' — keep this window open; Ctrl+C stops the service.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();app.close()
    return 0
if __name__=='__main__':raise SystemExit(main())
