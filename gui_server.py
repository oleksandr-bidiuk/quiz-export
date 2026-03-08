#!/usr/bin/env python3
"""Local web GUI for Quizlet flashcard export."""

from __future__ import annotations

import argparse
import io
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import quizlet_exporter as exporter

BASE_DIR = Path(__file__).resolve().parent
HTML_FILE = BASE_DIR / "gui.html"


def build_output(cards: list[tuple[str, str]], fmt: str) -> tuple[str, str, str]:
    if fmt == "json":
        payload = [{"term": term, "definition": definition} for term, definition in cards]
        return (
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            "application/json; charset=utf-8",
            "cards.json",
        )

    delimiter = "," if fmt == "csv" else "\t"
    mimetype = "text/csv; charset=utf-8" if fmt == "csv" else "text/tab-separated-values; charset=utf-8"
    filename = "cards.csv" if fmt == "csv" else "cards.tsv"
    buffer = io.StringIO()
    buffer.write(f"term{delimiter}definition\n")
    for term, definition in cards:
        escaped_term = term.replace('"', '""')
        escaped_definition = definition.replace('"', '""')
        buffer.write(f'"{escaped_term}"{delimiter}"{escaped_definition}"\n')
    return buffer.getvalue(), mimetype, filename


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in ("/", "/index.html"):
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        html = HTML_FILE.read_text(encoding="utf-8")
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/export":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body"})
            return

        url = str(payload.get("url", "")).strip()
        fmt = str(payload.get("format", "csv")).strip().lower()
        cookie = str(payload.get("cookie", "")).strip() or None

        if not url:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "URL is required"})
            return
        if fmt not in {"csv", "tsv", "json"}:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Format must be csv, tsv, or json"})
            return

        try:
            html = exporter.fetch_html(url, cookie=cookie)
            next_data = exporter.extract_next_data_json(html)
            cards = exporter.extract_flashcards(next_data)
            body_text, mimetype, filename = build_output(cards, fmt)
            body = body_text.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mimetype)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("X-Card-Count", str(len(cards)))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"GUI available at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
