#!/usr/bin/env python3
"""Local HTTP viewer with an isolated Docker ROS worker over a pipe, no host ROS."""
import argparse
import gzip
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = 'gemini-isaac-ros-live'
LABEL = 'gemini-isaac-ros-workbench-v1'
MAX_PACKET = 64 * 1024 * 1024
ACTIVE = ROOT / 'runs/live-view-active.json'


def process_matches(record, proc=Path('/proc')):
    """PID and birth-time guard: never signal a reused PID or another project."""
    try:
        pid = int(record['pid'])
        base = proc / str(pid)
        ticks = (base / 'stat').read_text().rsplit(') ', 1)[1].split()[19]
        if ticks != str(record['start_ticks']):
            return False
        argv = (base / 'cmdline').read_bytes().split(b'\0')
        expected = str(ROOT / 'scripts/live_view.py').encode()
        relative_match = b'scripts/live_view.py' in argv and (base / 'cwd').resolve() == ROOT
        return expected in argv or relative_match
    except (OSError, KeyError, ValueError, IndexError):
        return False


def active_record():
    try:
        record=json.loads(ACTIVE.read_text())
        return record if isinstance(record,dict) else {}
    except (OSError,ValueError):
        return {}


def write_active(record):
    temporary=ACTIVE.with_suffix('.tmp')
    temporary.write_text(json.dumps(record,indent=2));os.replace(temporary,ACTIVE)


def stop_active():
    if not ACTIVE.exists():
        print('没有本项目的实时查看器记录。')
        return
    record = active_record()
    if not process_matches(record):
        print('实时查看器已停止或记录过期；未向任何进程发送信号。')
        return
    os.kill(int(record['pid']), signal.SIGINT)
    deadline = time.monotonic() + 45
    while process_matches(record) and time.monotonic() < deadline:
        time.sleep(.1)
    if process_matches(record):
        raise TimeoutError('查看器正在退出，请查看当次日志；未强制终止其他进程')
    print('实时查看器及其建图管线已停止；待命容器和地图记录保留。')


class Latest:
    def __init__(self):
        self.lock = threading.Lock()
        self.meta = dict(running=True, sequence=-1, error=None)
        self.received_at = time.monotonic()
        self.mesh = gzip.compress(b'{}', compresslevel=1)
        self.revision = -1
        self.layers = gzip.compress(b'{}', compresslevel=1)
        self.global_mesh = gzip.compress(b'{}', compresslevel=1)
        self.global_revision = -1

    def update(self, packet):
        meta = packet['meta']
        global_data = packet.get('global_mesh')
        global_compressed = gzip.compress(json.dumps(global_data, separators=(',', ':')).encode(), compresslevel=1) if global_data and global_data['revision'] != self.global_revision else None
        data = packet.get('mesh')
        compressed = gzip.compress(json.dumps(data, separators=(',', ':')).encode(), compresslevel=1) if data else None
        layer_data = packet.get('layers')
        layer_compressed = gzip.compress(json.dumps(layer_data, separators=(',', ':')).encode(), compresslevel=1) if layer_data is not None else None
        with self.lock:
            if global_compressed is not None:
                self.global_mesh = global_compressed
                self.global_revision = global_data['revision']
            if layer_compressed is not None:
                self.layers = layer_compressed
            self.meta = meta
            self.received_at = time.monotonic()
            if data and 'revision' in data:
                self.mesh = compressed
                self.revision = data['revision']

    def status(self):
        with self.lock:
            return dict(self.meta, relay_age_ms=(time.monotonic()-self.received_at)*1000,
                        available_mesh_revision=self.revision, available_global_revision=self.global_revision)


def handler_for(latest):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Loopback binding plus a strict Host header prevents DNS rebinding.
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}',
                                                f'localhost:{self.server.server_port}'):
                self.send_error(403)
                return
            route = self.path.split('?', 1)[0]
            compressed = False
            if route == '/':
                body = (ROOT / 'viewer/live.html').read_bytes()
                mime = 'text/html; charset=utf-8'
            elif route == '/api/state':
                body = json.dumps(latest.status(), separators=(',', ':')).encode()
                mime = 'application/json'
            elif route == '/api/layers':
                with latest.lock:
                    body = latest.layers
                compressed = True
                mime = 'application/json'
            elif route == '/api/global':
                with latest.lock:
                    body = latest.global_mesh
                compressed = True
                mime = 'application/json'
            elif route == '/api/mesh':
                with latest.lock:
                    body = latest.mesh
                compressed = True
                mime = 'application/json'
            elif route == '/favicon.ico':
                body, mime = b'', 'image/x-icon'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            if compressed:
                self.send_header('Content-Encoding', 'gzip')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serial', default='')
    parser.add_argument('--profile', choices=['baseline', 'original', 'persistent'], default='baseline')
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--replay', type=Path, help='Read-only viewer for a stopped run directory')
    parser.add_argument('--port', type=int, default=8770)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--duration', type=float, help='Bounded validation run in seconds')
    args = parser.parse_args()
    if args.stop:
        stop_active()
        return 0
    (ROOT/'runs').mkdir(exist_ok=True)
    singleton=(ROOT/'runs/live-view.lock').open('a')
    try: fcntl.flock(singleton,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: parser.error('已有本项目查看器，请先执行 live.sh visualize-stop')
    if process_matches(active_record()):
        parser.error('已有本项目查看器，请先执行 live.sh visualize-stop')
    if args.replay:
        run=args.replay.resolve()
        try: run.relative_to(ROOT/'runs')
        except ValueError: parser.error('--replay must be inside project runs/')
        saved=run/'reports/viewer-snapshot.json'
        if saved.stat().st_size>2*MAX_PACKET: parser.error('Replay exceeds viewer packet limit')
        latest=Latest();packet=json.loads(saved.read_text());packet['meta']['running']=False
        latest.update(packet)
        server=ThreadingHTTPServer(('127.0.0.1',args.port),handler_for(latest))
        server.timeout=.25
        stopping=threading.Event()
        signal.signal(signal.SIGINT,lambda *_:stopping.set())
        signal.signal(signal.SIGTERM,lambda *_:stopping.set())
        ticks=Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(') ',1)[1].split()[19]
        write_active(dict(pid=os.getpid(),start_ticks=ticks,run=str(run),replay=True))
        print(f'已保存地图（不启动相机）：http://127.0.0.1:{args.port}/',flush=True)
        started=time.monotonic()
        try:
            while not stopping.is_set():
                server.handle_request()
                if args.duration and time.monotonic()-started>=args.duration: break
        finally:
            server.server_close()
            if ACTIVE.exists() and active_record().get('pid')==os.getpid(): ACTIVE.unlink()
        return 0
    if ACTIVE.exists() and process_matches(active_record()):
        parser.error('已有本项目实时查看器，请先运行 scripts/live.sh visualize-stop')
    info = json.loads(subprocess.check_output(['docker', 'inspect', CONTAINER], text=True))[0]
    if info['Config']['Labels'].get('io.isaac-orbbec.task') != LABEL or not info['State']['Running']:
        parser.error('Run scripts/live.sh start first; a project-owned running container is required')
    platform = subprocess.check_output(['docker', 'version', '--format', '{{.Server.Platform.Name}}'], text=True).strip()
    if platform != 'Docker Engine - Community':
        parser.error('Docker Engine - Community is required')
    run = (args.run or ROOT / 'runs' / time.strftime('%Y%m%d-%H%M%S-live-view')).resolve()
    try:
        relative = run.relative_to(ROOT / 'runs')
    except ValueError:
        parser.error('--run must be inside project runs/')
    if (run / 'reports/viewer.json').exists():
        parser.error('Choose a new --run directory for each viewer session')
    for child in ('logs', 'reports', 'screenshots'):
        (run / child).mkdir(parents=True, exist_ok=True)
    c_run = '/workspaces/isaac_ros-dev/runs/' + str(relative)
    latest = Latest()
    # Bind before starting the camera; a port conflict must not leave a pipeline behind.
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(latest))
    server.daemon_threads = True
    worker_log = (run / 'logs/bridge-stderr.log').open('w')
    worker = subprocess.Popen(['docker', 'exec', CONTAINER, '/opt/orbbec-entrypoint.sh',
                               'flock', '--nonblock', '/tmp/isaac-live-pipeline.lock',
                               'python3', '/workspaces/isaac_ros-dev/scripts/live_view_bridge.py',
                               '--run', c_run, '--serial', args.serial, '--profile', args.profile],
                              stdout=subprocess.PIPE, stderr=worker_log)
    stopping = threading.Event()

    def receive():
        try:
            while True:
                line = worker.stdout.readline(MAX_PACKET + 1)
                if not line:
                    break
                if len(line) > MAX_PACKET:
                    raise ValueError('Viewer packet exceeds limit')
                latest.update(json.loads(line))
        except Exception as error:
            with latest.lock:
                latest.meta['error'] = str(error)
        finally:
            with latest.lock:
                latest.meta['running'] = False
                if not stopping.is_set() and latest.meta.get('error') is None:
                    latest.meta['error'] = '采集进程已结束；检查相机、管线锁和日志'

    reader = threading.Thread(target=receive, daemon=True)
    reader.start()

    def request_stop(*_):
        stopping.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    server.timeout = .25
    started = time.monotonic()
    (run / 'reports/viewer-pid.txt').write_text(str(os.getpid()))
    ticks = Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(') ', 1)[1].split()[19]
    write_active(dict(pid=os.getpid(), start_ticks=ticks, run=str(run)))
    (run / 'reports/viewer.json').write_text(json.dumps(dict(url=f'http://127.0.0.1:{args.port}/',
                                                           run=str(run), container=CONTAINER), indent=2))
    print(f'实时查看器：http://127.0.0.1:{args.port}/\n记录：{run}\nCtrl+C 停止本次相机管线及查看器。', flush=True)
    try:
        while not stopping.is_set():
            server.handle_request()
            if args.duration and time.monotonic()-started >= args.duration:
                break
            # Keep read-only state available after a pipeline failure; clearly mark it stopped.
    finally:
        stopping.set()
        pid_file = run / 'reports/bridge-pid.txt'
        deadline = time.monotonic() + 5
        while worker.poll() is None and not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(.1)
        if worker.poll() is None and pid_file.exists():
            pid = pid_file.read_text().strip()
            if pid.isdigit():
                subprocess.run(['docker', 'exec', CONTAINER, 'kill', '-INT', pid],
                               stdout=subprocess.DEVNULL, stderr=worker_log, timeout=5)
        try:
            worker.wait(timeout=40)
        except subprocess.TimeoutExpired:
            worker.terminate()
            worker.wait(timeout=5)
        reader.join(timeout=2)
        server.server_close()
        if ACTIVE.exists() and active_record().get('pid') == os.getpid():
            ACTIVE.unlink()
        (run / 'reports/viewer-final.json').write_text(json.dumps(latest.status(), indent=2))
        with latest.lock:
            saved=dict(meta=latest.meta,mesh=json.loads(gzip.decompress(latest.mesh)),
                       global_mesh=json.loads(gzip.decompress(latest.global_mesh)),
                       layers=json.loads(gzip.decompress(latest.layers)))
        snapshot=run/'reports/viewer-snapshot.json'
        temporary=snapshot.with_suffix('.tmp');temporary.write_text(json.dumps(saved,separators=(',',':')))
        os.replace(temporary,snapshot)
        worker_log.close()
    return 1 if latest.status().get('error') else 0


if __name__ == '__main__':
    raise SystemExit(main())
