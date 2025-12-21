import argparse
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# Centralized logging
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logging_config import get_logger
logger = get_logger(__name__)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


class SyncServer:
    def __init__(self, storage_dir: str, token: str):
        self.storage_dir = storage_dir
        self.token = token or ""
        ensure_dir(self.storage_dir)

    def user_db_path(self, user: str) -> str:
        safe = "".join(ch for ch in user if ch.isalnum() or ch in ("-", "_")) or "default"
        return os.path.join(self.storage_dir, f"{safe}.db")

    def user_meta_path(self, user: str) -> str:
        safe = "".join(ch for ch in user if ch.isalnum() or ch in ("-", "_")) or "default"
        return os.path.join(self.storage_dir, f"{safe}.meta.json")

    def get_meta(self, user: str) -> dict:
        db_path = self.user_db_path(user)
        if not os.path.exists(db_path):
            return {"exists": False}
        st = os.stat(db_path)
        with open(db_path, "rb") as f:
            data = f.read()
        return {
            "exists": True,
            "size": st.st_size,
            "mtime": st.st_mtime,
            "sha256": sha256_bytes(data),
        }

    def save_db(self, user: str, data: bytes) -> dict:
        db_path = self.user_db_path(user)
        tmp = db_path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, db_path)
        meta = self.get_meta(user)
        with open(self.user_meta_path(user), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        return meta


def make_handler(server_state: SyncServer):
    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, obj: dict, code: int = 200):
            data = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_bytes(self, data: bytes, code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _auth_ok(self) -> bool:
            if not server_state.token:
                return True
            token = self.headers.get("X-Token", "")
            return token == server_state.token

        def do_GET(self):
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            user = (qs.get("user", ["default"])[0] or "default").strip()

            if parsed.path == "/api/ping":
                return self._send_json({"ok": True})

            if parsed.path == "/api/meta":
                if not self._auth_ok():
                    return self._send_json({"ok": False, "error": "unauthorized"}, 401)
                meta = server_state.get_meta(user)
                meta["ok"] = True
                return self._send_json(meta)

            if parsed.path == "/api/db":
                if not self._auth_ok():
                    return self._send_json({"ok": False, "error": "unauthorized"}, 401)
                db_path = server_state.user_db_path(user)
                if not os.path.exists(db_path):
                    return self._send_json({"ok": False, "error": "not_found"}, 404)
                with open(db_path, "rb") as f:
                    return self._send_bytes(f.read(), 200)

            return self._send_json({"ok": False, "error": "not_found"}, 404)

        def do_POST(self):
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            user = (qs.get("user", ["default"])[0] or "default").strip()

            if parsed.path != "/api/db":
                return self._send_json({"ok": False, "error": "not_found"}, 404)
            if not self._auth_ok():
                return self._send_json({"ok": False, "error": "unauthorized"}, 401)

            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return self._send_json({"ok": False, "error": "empty_body"}, 400)
            data = self.rfile.read(length)

            meta = server_state.save_db(user, data)
            meta["ok"] = True
            return self._send_json(meta, 200)

        def log_message(self, format, *args):
            # quiet
            return

    return Handler


def main():
    ap = argparse.ArgumentParser(description="DailyDashboard DB Sync Server")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--storage", default="sync_storage", help="Folder to store per-user DB files")
    ap.add_argument("--token", default="", help="Shared token; if empty, auth is disabled")
    args = ap.parse_args()

    state = SyncServer(storage_dir=args.storage, token=args.token)
    handler = make_handler(state)
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Sync server running on http://{args.host}:{args.port}")
    print(f"Storage: {os.path.abspath(args.storage)}")
    print("Endpoints: GET /api/ping | GET /api/meta?user=... | GET/POST /api/db?user=...")
    httpd.serve_forever()


if __name__ == "__main__":
    main()


