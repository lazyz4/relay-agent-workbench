"""Standalone supervisor: separate app and demo-service processes, owned cleanup."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parent


def busy(port):
    with socket.socket() as sock:
        sock.settimeout(.3)
        return sock.connect_ex(('127.0.0.1',port))==0


def main():
    if busy(8875):
        try:
            data=json.load(urllib.request.urlopen('http://127.0.0.1:8875/api/status',timeout=2))
            if data.get('app')=='relay' and data.get('preview') and '--preview' not in sys.argv:
                print('Replacing development preview with your Windows session...',flush=True)
                req=urllib.request.Request('http://127.0.0.1:8875/api/preview/stop',data=b'{}',headers={'Content-Type':'application/json'})
                urllib.request.urlopen(req,timeout=3).close()
                for _ in range(40):
                    if not any(busy(p) for p in (8875,8876,8877)):
                        break
                    time.sleep(.25)
            elif data.get('app')=='relay':
                print('Relay is already running. Opening workbench.',flush=True)
                if '--no-browser' not in sys.argv:
                    webbrowser.open('http://127.0.0.1:8875/')
                return
        except Exception:
            pass
        if busy(8875):
            raise RuntimeError('Port 8875 is occupied by another service. Do not start a second instance.')
    for port in (8876,8877):
        if busy(port):
            raise RuntimeError(f'Port {port} is occupied. Stop the previous demo service first.')
    (ROOT/'data').mkdir(exist_ok=True)
    children=[]
    files=[]
    env=os.environ.copy()
    env['PYTHONUTF8']='1'
    if '--preview' in sys.argv:
        env['RELAY_MANAGED_PREVIEW']='1'
    else:
        env.pop('RELAY_MANAGED_PREVIEW',None)
    try:
        for service in ('rd','docs','ui'):
            output=(ROOT/'data'/f'{service}.log').open('a',encoding='utf-8')
            files.append(output)
            child_env=env.copy()
            if service!='ui':
                for name in ('ANTHROPIC_API_KEY','DEEPSEEK_API_KEY'):
                    child_env.pop(name,None)
            child=subprocess.Popen([sys.executable,'-X','utf8',str(ROOT/'app.py'),'--service',service],cwd=ROOT,env=child_env,stdout=output,stderr=output,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            children.append(child)
        ready=False
        for _ in range(40):
            if any(p.poll() is not None for p in children):
                raise RuntimeError('A service exited. Check data/ui.log, rd.log, docs.log.')
            try:
                status=json.load(urllib.request.urlopen('http://127.0.0.1:8875/api/status',timeout=1))
                if status.get('app')=='relay' and busy(8876) and busy(8877):
                    ready=True
                    break
            except Exception:
                time.sleep(.25)
        if not ready:
            raise RuntimeError('Services did not become ready. Check data/*.log.')
        print('Relay ready: http://127.0.0.1:8875/\nKeep this window open. Ctrl+C stops all three services.',flush=True)
        if '--no-browser' not in sys.argv:
            webbrowser.open('http://127.0.0.1:8875/')
        while all(p.poll() is None for p in children):
            time.sleep(1)
        raise RuntimeError('A service exited unexpectedly. Check data/*.log.')
    except KeyboardInterrupt:
        print('Stopping Relay...',flush=True)
    finally:
        for p in children:
            if p.poll() is None:
                p.terminate()
        for p in children:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        for f in files:
            f.close()


if __name__=='__main__':
    try:
        main()
    except Exception as e:
        print(str(e),flush=True)
        sys.exit(1)
