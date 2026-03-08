#!/usr/bin/env python3
"""Export Quizlet flashcards into CSV/TSV/JSON."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


def fetch_html(url: str, cookie: str | None = None) -> str:
    headers = {"User-Agent": USER_AGENT}
    if cookie:
        headers["Cookie"] = cookie
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_next_data_json(html: str) -> dict[str, Any]:
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("Could not find __NEXT_DATA__ script in page HTML")

    raw_json = unescape(match.group(1).strip())
    return json.loads(raw_json)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        joined = " ".join(part for part in (normalize_text(v) for v in value) if part)
        return re.sub(r"\s+", " ", joined).strip()
    if isinstance(value, dict):
        # Quizlet card side media often stores the visible text here.
        media = value.get("media")
        if isinstance(media, list):
            media_parts = []
            for item in media:
                if isinstance(item, dict):
                    plain = item.get("plainText")
                    if isinstance(plain, str) and plain.strip():
                        media_parts.append(plain.strip())
            if media_parts:
                return re.sub(r"\s+", " ", " ".join(media_parts)).strip()
        for key in ("plainText", "text", "label", "word", "term", "definition", "value"):
            if key in value:
                text = normalize_text(value[key])
                if text:
                    return text
        nested = [normalize_text(v) for v in value.values()]
        joined = " ".join(part for part in nested if part)
        return re.sub(r"\s+", " ", joined).strip()
    return str(value).strip()


def looks_like_card(obj: dict[str, Any]) -> tuple[str, str] | None:
    term_keys = ("word", "term", "prompt", "question", "plainTextWord")
    def_keys = ("definition", "answer", "response", "plainTextDefinition")

    term = ""
    definition = ""

    for key in term_keys:
        if key in obj:
            term = normalize_text(obj[key])
            if term:
                break

    for key in def_keys:
        if key in obj:
            definition = normalize_text(obj[key])
            if definition:
                break

    if term and definition:
        return term, definition

    # Common Quizlet shape: {"cardSides": [{"label": "term"}, {"label": "definition"}]}
    sides = obj.get("cardSides")
    if isinstance(sides, list) and len(sides) >= 2:
        left = normalize_text(sides[0])
        right = normalize_text(sides[1])
        if left and right:
            return left, right

    return None


def iter_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from iter_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_dicts(item)


def extract_cards_from_studiable_items(node: Any, set_id: int | None) -> list[tuple[str, str]]:
    cards: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for obj in iter_dicts(node):
        items = obj.get("studiableItems") if isinstance(obj, dict) else None
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue
            if set_id is not None and item.get("studiableContainerId") != set_id:
                continue

            sides = item.get("cardSides")
            if not isinstance(sides, list) or len(sides) < 2:
                continue
            term = normalize_text(sides[0])
            definition = normalize_text(sides[1])
            if term and definition:
                card = (term, definition)
                if card not in seen:
                    seen.add(card)
                    cards.append(card)

    return cards


def extract_flashcards(next_data: dict[str, Any]) -> list[tuple[str, str]]:
    cards: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    set_id: int | None = None
    query = next_data.get("query", {})
    if isinstance(query, dict):
        value = query.get("setId")
        if isinstance(value, str) and value.isdigit():
            set_id = int(value)
        elif isinstance(value, int):
            set_id = value

    roots: list[Any] = [next_data]
    redux_blob = (
        next_data.get("props", {})
        .get("pageProps", {})
        .get("dehydratedReduxStateKey")
    )
    if isinstance(redux_blob, str):
        try:
            redux_state = json.loads(redux_blob)
            roots.append(redux_state)
            targeted = extract_cards_from_studiable_items(redux_state, set_id)
            if targeted:
                return targeted
        except json.JSONDecodeError:
            pass

    for root in roots:
        for obj in iter_dicts(root):
            maybe = looks_like_card(obj)
            if maybe and maybe not in seen:
                seen.add(maybe)
                cards.append(maybe)

    if not cards:
        raise ValueError(
            "No cards found. The set may be private, blocked by anti-bot, or page structure changed."
        )

    return cards


def write_cards(cards: list[tuple[str, str]], fmt: str, output: Path | None) -> None:
    if fmt == "json":
        payload = [{"term": term, "definition": definition} for term, definition in cards]
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if output:
            output.write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
        return

    delimiter = "," if fmt == "csv" else "\t"
    if output:
        with output.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter=delimiter)
            writer.writerow(["term", "definition"])
            writer.writerows(cards)
    else:
        writer = csv.writer(sys.stdout, delimiter=delimiter)
        writer.writerow(["term", "definition"])
        writer.writerows(cards)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Quizlet set URL")
    parser.add_argument("-o", "--output", type=Path, help="Output file path")
    parser.add_argument(
        "-f",
        "--format",
        choices=("csv", "tsv", "json"),
        default="csv",
        help="Output format (default: csv)",
    )
    parser.add_argument(
        "--cookie",
        help="Optional Cookie header value for authenticated access",
    )
    args = parser.parse_args(argv)

    try:
        html = fetch_html(args.url, cookie=args.cookie)
        next_data = extract_next_data_json(html)
        cards = extract_flashcards(next_data)
        write_cards(cards, args.format, args.output)
        print(f"Exported {len(cards)} cards.", file=sys.stderr)
        return 0
    except (HTTPError, URLError) as exc:
        print(f"Network error: {exc}", file=sys.stderr)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Parse error: {exc}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected error: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
