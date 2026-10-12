"""Loopback dashboard; every migration write requires an explicit confirmation."""
import difflib
import fcntl
import hashlib
import json
import os
import secrets
import sqlite3
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..scan import scan
from ..store import SKIP_CONTENT, apply, backups, guard, preview, restore, target_home
from .. import operations, updates, usage, cleanup, labels
from ..sources import github

STATIC = Path(__file__).parent / "static"
HEARTBEAT_TIMEOUT = 30


class Dashboard(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, inventory):
        self.token = secrets.token_urlsafe(32)
        self.inventory = inventory
        self.home = Path(inventory.get("home", target_home()))
        self.install_reviews = {}
        self.update_reviews = {}
        self.update_lock = threading.Lock()
        self.update_thread = None
        self.labels_lock = threading.Lock()
        self.labels_thread = None
        self.labels_progress = {'running': False, 'done': 0, 'total': 0, 'message': '', 'error': ''}
        self.usage_lock = threading.Lock()
        self.usage_progress = {'running':False,'done':0,'total':0}
        self.usage_temporary = tempfile.TemporaryDirectory(prefix='skill-pilot-dashboard-usage-')
        self.usage_database = (self.home / '.skill-pilot/usage.sqlite' if preview_allowed(self.home) else
                               Path(self.usage_temporary.name) / 'usage.sqlite')
        self.last_heartbeat = time.monotonic()
        super().__init__(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.url = f"{self.origin}/?token={self.token}"

    def server_close(self):
        super().server_close()
        if self.update_thread: self.update_thread.join()
        if self.labels_thread: self.labels_thread.join()
        self.usage_temporary.cleanup()

    def watch(self):
        while time.monotonic() - self.last_heartbeat < HEARTBEAT_TIMEOUT or self.labels_progress['running'] or any(r['running'] for r in list(self.update_reviews.values())):
            time.sleep(0.1)
        self.shutdown()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        # URLs contain a session secret; never put them in access logs.
        pass

    def authorized(self):
        if self.headers.get("Host") != self.server.origin.removeprefix("http://"):
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != self.server.origin:
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return False
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        token = self.headers.get("X-Skill-Pilot-Token") or query.get("token", [""])[0]
        return secrets.compare_digest(token, self.server.token)

    def reply(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.authorized():
            self.reply(403, {"error": "此页面只允许本机本次打开的浏览器访问。"})
            return
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/scan":
            self.reply(200, self.server.inventory)
        elif path == '/api/settings':
            self.reply(200, labels.public_settings(self.server.home))
        elif path == '/api/labels/progress':
            self.reply(200, self.server.labels_progress.copy())
        elif path == '/api/usage-progress':
            self.reply(200,self.server.usage_progress.copy())
        elif path == '/api/updates/progress':
            with self.server.update_lock:
                review = next(reversed(self.server.update_reviews.values()), None)
                self.reply(200, updates.public(review) if review else None)
        elif path in ('/api/usage','/api/cleanup'):
            try:
                if not self.server.usage_lock.acquire(blocking=False):
                    self.reply(409,{'error':'正在统计，完成后再生成名单。' if path == '/api/cleanup' else '正在统计用量，请稍候。','retry':path == '/api/usage'})
                    return
                try:
                    result = usage.report(self.server.home,self.server.usage_database,progress=self.server.usage_progress) if path == '/api/usage' else cleanup.preview(self.server.home,self.server.usage_database)
                finally:
                    if path == '/api/usage': self.server.usage_progress['running'] = False
                    self.server.usage_lock.release()
                self.reply(200,result)
            except (ValueError,OSError,KeyError,sqlite3.Error) as error:
                self.reply(409,{'error':('正在统计，完成后再生成名单。' if path == '/api/cleanup' else '用量暂时读不到，技能分配仍可照常操作。') if isinstance(error,sqlite3.Error) else str(error), 'retry':getattr(error,'sqlite_errorcode',None) in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED)})
        elif path in ('/api/table', '/api/log'):
            try:
                result = operations.table(self.server.home,self.server.usage_database) if path == '/api/table' else operations.history(self.server.home)
                self.reply(200, result)
            except (ValueError, OSError, KeyError) as error:
                self.reply(409, {'error': str(error)})
        elif path == "/api/status":
            self.reply(200, {"pid": os.getpid(), "read_only": not preview_allowed(self.server.home)})
        elif path in ("/api/migration/plan", "/api/backups", "/api/migration/compare"):
            try:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                agents = query.get("agents", [None])[0]
                if path == "/api/backups":
                    self.reply(200, backups(self.server.home))
                    return
                plan = preview(self.server.home, agents.split(",") if agents is not None else None)
                if path == "/api/migration/plan":
                    self.reply(200, plan)
                    return
                if query.get("plan_id", [""])[0] != plan["plan_id"]:
                    raise ValueError("目录内容已经变了，请重新预览。")
                skill = next(s for s in plan["skills"] if s["name"] == query.get("name", [""])[0])
                baseline = next(o for o in skill["options"] if o["id"] == skill["default"])
                texts = []
                for option in skill["options"]:
                    if option == baseline:
                        continue
                    texts.append(compare_files(Path(baseline["path"]), Path(option["path"])))
                self.reply(200, {"comparison": "\n".join(texts)})
            except (ValueError, OSError, StopIteration) as error:
                self.reply(409, {"error": str(error) or "这个技能已不在预览里，请重新预览。"})
        elif path in ("/", "/app.js", "/app.css"):
            file = STATIC / ("index.html" if path == "/" else path.removeprefix("/"))
            body = file.read_bytes().replace(b"__SESSION_TOKEN__", self.server.token.encode())
            kind = {"html": "text/html", "js": "text/javascript", "css": "text/css"}[file.suffix.removeprefix(".")]
            self.reply(200, body, kind + "; charset=utf-8")
        else:
            self.reply(404, {"error": "没有这个页面。"})

    def do_POST(self):
        if not self.authorized() or self.headers.get("Origin") != self.server.origin:
            self.reply(403, {"error": "请求来源不属于本次看板。"})
            return
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/heartbeat":
            self.server.last_heartbeat = time.monotonic()
            self.reply(200, {"ok": True})
            return
        read_routes = {'/api/assignment/preview', '/api/install/inspect', '/api/incoming/compare',
                       '/api/updates/check', '/api/updates/explain', '/api/updates/merge', '/api/updates/calibrate'}
        write_routes = {'/api/assignment/apply', '/api/dependencies', '/api/install/apply', '/api/absorb', '/api/undo',
                        '/api/updates/apply','/api/cleanup/apply','/api/withdrawn/restore'}
        settings_routes = {'/api/settings/llm', '/api/settings/llm/test', '/api/labels/run'}
        if path not in {"/api/migration/apply", "/api/restore"} | read_routes | write_routes | settings_routes:
            self.reply(405, {"error": "当前阶段没有这个操作。"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024 * 1024:
                raise ValueError("请求内容不完整或太长，请重新打开核对页。")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('请求内容格式不正确。')
            if path in settings_routes:
                if not preview_allowed(self.server.home):
                    self.reply(403, {'error': '当前处于只读模式，文件没有改动。'})
                    return
                if path == '/api/settings/llm':
                    self.reply(200, labels.save_settings(self.server.home, body))
                elif path == '/api/settings/llm/test':
                    self.reply(200, labels.test(self.server.home))
                else:
                    mode = body.get('mode')
                    if mode not in ('missing', 'all'):
                        raise ValueError('请选择补齐中文名或重新整理全部。')
                    with self.server.labels_lock:
                        if self.server.labels_progress['running']:
                            raise ValueError('正在给技能起中文名，请等这次完成。')
                        if not labels.settings(self.server.home).get('api_key'):
                            raise ValueError('请先到设置里填好 AI 服务的 key。')
                        self.server.labels_progress.update(running=True, done=0, total=0, message='正在准备技能名单…', error='')
                        self.server.labels_thread = threading.Thread(target=labels.run,
                            args=(self.server.home, mode, self.server.labels_progress), daemon=True)
                        self.server.labels_thread.start()
                        self.reply(200, self.server.labels_progress.copy())
                return
            if path == '/api/updates/check':
                with self.server.update_lock:
                    review = next(reversed(self.server.update_reviews.values()), None)
                    if review is None or not review['running']:
                        review = updates.create(self.server.home, body.get('withdrawn', False))
                        self.server.update_reviews[review['id']] = review
                        self.server.update_thread = threading.Thread(target=updates.check, kwargs={'review': review, 'lock': self.server.update_lock}, daemon=True)
                        self.server.update_thread.start()
                    self.reply(200, updates.public(review))
                return
            if path in {'/api/updates/explain', '/api/updates/merge', '/api/updates/calibrate'}:
                with self.server.update_lock:
                    review = self.server.update_reviews[body['review_id']]
                action = updates.explain if path.endswith('explain') else updates.calibrate if path.endswith('calibrate') else updates.prepare_merge
                result = action(review, body['name'])
                self.reply(200, result)
                return
            if path == '/api/assignment/preview':
                self.reply(200, operations.preview_assign(body['changes'], self.server.home))
                return
            if path == '/api/install/inspect':
                review = github.inspect(body['url'])
                self.server.install_reviews[review['id']] = review
                registry = operations.load(self.server.home)[1]
                self.reply(200, {**review, 'conflicts': operations.conflicts(review['skills'], registry, self.server.home)})
                return
            if path == '/api/incoming/compare':
                existing = self.server.home / '.skill-pilot/store' / body['name']
                if body.get('review_id'):
                    review = self.server.install_reviews[body['review_id']]
                    incoming = Path(next(s['path'] for s in review['skills'] if s['name'] == body['name']))
                else:
                    home, registry, agents = operations.load(self.server.home)
                    incoming = Path(next(s['path'] for s in operations.new_skills(home, agents)
                                         if s['relative'] == body['relative'] and s['name'] == body['name']))
                github.safe_skill(incoming)
                self.reply(200, {'comparison': compare_files(existing, incoming)})
                return
            if body.get("confirmed") is not True:
                self.reply(400, {"error": "请先核对，并确认这次操作。"})
                return
            if not preview_allowed(self.server.home):
                self.reply(403, {"error": "当前处于只读模式，文件没有改动。"})
                return
            if path == "/api/migration/apply":
                result = apply(body["plan_id"], self.server.home, body["agents"], body.get("choices"), body.get("sources"))
                operations.bootstrap(self.server.home)
            elif path == '/api/restore':
                result = restore(body["backup_id"], self.server.home)
            elif path == '/api/assignment/apply':
                result = operations.apply_assign(body['changes'], body['revision'], True, self.server.home)
            elif path == '/api/dependencies':
                result = operations.decide_dependencies(body['decisions'], body['revision'], self.server.home)
            elif path == '/api/install/apply':
                result = operations.install(self.server.install_reviews[body['review_id']], body['skills'],
                                            body.get('agents'), body['revision'], self.server.home)
            elif path == '/api/absorb':
                result = operations.absorb(body.get('all', True), body.get('selected'), body['revision'], self.server.home)
            elif path == '/api/updates/apply':
                with self.server.update_lock:
                    review = self.server.update_reviews[body['review_id']]
                    result = updates.apply(review, body['skills'], body.get('choices'), True,
                                           body.get('merge_ids'), body.get('confirm_lark_cli', False))
            elif path == '/api/cleanup/apply':
                if not self.server.usage_lock.acquire(blocking=False):
                    raise ValueError('正在统计，完成后再生成名单。')
                try:
                    result = cleanup.apply(body.get('keep'),True,self.server.home,self.server.usage_database,
                                           body['revision'],body['candidates'])
                finally:
                    self.server.usage_lock.release()
            elif path == '/api/withdrawn/restore':
                result = cleanup.restore(body['skills'],self.server.home,body['revision'])
            else:
                result = operations.undo(body['id'], body['revision'], self.server.home)
            self.server.inventory = scan(self.server.home)
            self.reply(200, result)
        except (ValueError, OSError, KeyError, TypeError, StopIteration, sqlite3.Error) as error:
            message = '设置没能保存，请核对后再试。' if path in settings_routes and not isinstance(error, ValueError) else str(error)
            self.reply(409, {"error": '正在统计，完成后再生成名单。' if isinstance(error,sqlite3.Error) else message or "操作没能完成，请重新预览。"})


def preview_allowed(home):
    try:
        guard(home / ".skill-pilot", home)
        return True
    except ValueError:
        return False


def compare_files(left, right):
    def files(root):
        return {str(p.relative_to(root)): p for p in root.rglob("*") if p.is_file()
                and not any(part in SKIP_CONTENT for part in p.relative_to(root).parts)}
    one, two = files(left), files(right)
    result = [f"默认选择：{left}\n另一份：{right}\n"]
    for name in sorted(one.keys() | two.keys()):
        a = one[name].read_bytes() if name in one else b""
        b = two[name].read_bytes() if name in two else b""
        if a == b:
            continue
        result.append(f"文件：{name}" + ("（脚本或可执行文件）" if Path(name).suffix in {".py", ".js", ".sh"} else ""))
        try:
            result.extend(difflib.unified_diff(a.decode().splitlines(), b.decode().splitlines(), fromfile="默认选择", tofile="另一份", lineterm=""))
        except UnicodeError:
            result.append("此文件不是文本，内容不同。")
    return "\n".join(result)


def lock_path():
    identity = hashlib.sha256(str(target_home()).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"skill-pilot-{os.getuid()}-{identity}.lock"


def open_existing(lock):
    # A simultaneous launcher may hold the lock just before writing its URL.
    for _ in range(50):
        lock.seek(0)
        try:
            state = json.loads(lock.read())
            url = urllib.parse.urlsplit(state["url"])
            if url.scheme != "http" or url.hostname != "127.0.0.1":
                return False
            request = urllib.request.Request(f"http://127.0.0.1:{url.port}/api/status?{url.query}")
            with urllib.request.urlopen(request, timeout=0.5) as response:
                if json.load(response)["pid"] != state["pid"]:
                    return False
            webbrowser.open(state["url"])
            return True
        except (ValueError, KeyError, OSError, urllib.error.URLError):
            time.sleep(0.1)
    return False


def run(json_output=False):
    fd = os.open(lock_path(), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        os.fchmod(lock.fileno(), 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if open_existing(lock):
                print(json.dumps({"message": "已打开正在运行的看板。"}, ensure_ascii=False) if json_output else "已打开正在运行的看板。")
                return
            raise SystemExit("已有看板正在启动或退出，请稍后再打开。")
        operations.bootstrap(target_home())
        server = Dashboard(scan())
        lock.seek(0)
        lock.truncate()
        json.dump({"pid": os.getpid(), "url": server.url}, lock)
        lock.flush()
        server.last_heartbeat = time.monotonic()
        threading.Thread(target=server.watch, daemon=True).start()
        webbrowser.open(server.url)
        print(json.dumps({"message": "看板已打开；关掉全部页面后，程序会在 30 秒内退出；正在检查更新或起中文名时，会等任务完成。", "pid": os.getpid(), "url": server.url}, ensure_ascii=False) if json_output else "看板已打开；关掉全部页面后，程序会在 30 秒内退出；正在检查更新或起中文名时，会等任务完成。", flush=True)
        try:
            server.serve_forever(poll_interval=0.1)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            import shutil
            for review in server.install_reviews.values():
                shutil.rmtree(review['temporary'], ignore_errors=True)
            for review in server.update_reviews.values():
                shutil.rmtree(review['temporary'], ignore_errors=True)
            lock.seek(0)
            lock.truncate()
            # Do not unlink: another launcher could be holding the same inode.
