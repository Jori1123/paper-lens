#!/usr/bin/env python3
"""Paper Lens 本地静态服务器。

用法：
    python3 server.py
    python3 server.py --port 8788 --no-browser
"""

from __future__ import annotations

import argparse
import contextlib
import http.server
import json
import socketserver
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class PaperLensHandler(http.server.SimpleHTTPRequestHandler):
    """提供静态资源，并暴露一个轻量健康检查接口。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/api/health":
            data_file = ROOT / "data" / "papers.json"
            try:
                payload = json.loads(data_file.read_text(encoding="utf-8"))
                body = json.dumps(
                    {
                        "status": "ok",
                        "papers": len(payload.get("papers", [])),
                        "updated_at": payload.get("meta", {}).get("updated_at"),
                    },
                    ensure_ascii=False,
                ).encode()
                self.send_response(200)
            except (OSError, json.JSONDecodeError) as exc:
                body = json.dumps({"status": "error", "message": str(exc)}).encode()
                self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 Paper Lens 论文检索网站")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    with ReusableTCPServer((args.host, args.port), PaperLensHandler) as server:
        url = f"http://{args.host}:{args.port}"
        print(f"Paper Lens 已启动：{url}")
        print("按 Ctrl+C 停止")
        if not args.no_browser:
            threading.Timer(0.4, lambda: webbrowser.open(url)).start()
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()


if __name__ == "__main__":
    main()
