#!/usr/bin/env python3
"""Later Line: keep one shorter line of a task you are putting off.

A local open-weight model may replace the task. The line is kept only when it
is shorter than the source and still names something that was already there.
Anything else is thrown away. The fallback is the first twelve words.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MAX_WORDS = 12
DEFAULT_MODEL = "gemma3:1b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

STOP = {
    "about", "after", "again", "also", "and", "because", "before", "from",
    "have", "into", "just", "keep", "meant", "need", "open", "since", "still",
    "that", "them", "then", "there", "this", "want", "with", "would", "your",
}

# A shorter line is not allowed to announce that the task is finished.
COMPLETION = {
    "addressed", "completed", "done", "finished", "fixed", "paid", "resolved", "sent",
}


def split_words(text: str) -> list[str]:
    return [part for part in text.split() if part]


def concrete_tokens(text: str) -> set[str]:
    found = set()
    for raw in re.findall(r"[A-Za-z0-9']+", text):
        word = raw.lower().strip("'")
        if len(word) > 3 and word not in STOP:
            found.add(word)
    return found


def first_words(text: str, limit: int = MAX_WORDS) -> str:
    return " ".join(split_words(text)[:limit])


def word_set(text: str) -> set[str]:
    return {word.lower().strip(".,;:–—\"'") for word in split_words(text)}


def accept(source: str, line: str) -> bool:
    """A model line is usable only when it shrinks the task and keeps a noun."""
    source_words = split_words(source)
    line_words = split_words(line)
    if not line_words or len(line_words) > MAX_WORDS:
        return False
    if len(line_words) >= len(source_words):
        return False
    nouns = concrete_tokens(source)
    if nouns and not (nouns & concrete_tokens(line)):
        return False
    invented_done = (word_set(line) & COMPLETION) - (word_set(source) & COMPLETION)
    if invented_done:
        return False
    return True


def rejection_reason(source: str, model_line: str) -> str:
    words = split_words(model_line)
    if not words:
        return "the model did not return a line, so the first 12 words were kept"
    if len(words) > MAX_WORDS:
        return "the model line was longer than 12 words, so it was thrown away"
    if len(words) >= len(split_words(source)):
        return "the model line was not shorter, so it was thrown away"
    if concrete_tokens(source) and not (concrete_tokens(source) & concrete_tokens(model_line)):
        return "the model line dropped the thing the task was about, so it was thrown away"
    if (word_set(model_line) & COMPLETION) - (word_set(source) & COMPLETION):
        return "the model claimed the task was already done, so it was thrown away"
    return "the model line was not kept, so the first 12 words were kept"


def parse_model_line(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return ""
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return ""
    if not isinstance(payload, dict):
        return ""
    line = payload.get("line", "")
    return line.strip() if isinstance(line, str) else ""


def split_pile(text: str) -> list[str]:
    blocks = []
    for block in re.split(r"\n\s*\n", text.strip()):
        cleaned = " ".join(split_words(block))
        if cleaned:
            blocks.append(cleaned)
    return blocks


def ask_ollama(source: str, model: str, url: str, timeout: float) -> str:
    prompt = (
        "Shorten this postponed task to one line of at most 12 words. "
        "Keep one specific thing that is already named. "
        "Do not add steps, advice, or new facts. "
        'Reply as JSON: {"line":"..."}\n\n'
        f"Task:\n{source}"
    )
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": 80},
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode())
    return parse_model_line(str(payload.get("response", "")))


def shrink_one(source: str, ask) -> dict:
    source_count = len(split_words(source))
    if source_count <= MAX_WORDS:
        return {
            "source": source,
            "line": source,
            "source_words": source_count,
            "line_words": source_count,
            "path": "already_short",
            "model_line": "",
            "reason": "already one line, so the model was not asked",
        }
    started = time.perf_counter()
    try:
        model_line = ask(source)
        error = ""
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        model_line = ""
        error = str(exc)
    elapsed = round(time.perf_counter() - started, 2)
    if model_line and accept(source, model_line):
        kept = model_line
        path = "model"
        reason = "shorter, and it still names something from the task"
    else:
        kept = first_words(source)
        path = "fallback"
        if error:
            reason = "the model was unreachable, so the first 12 words were kept"
        else:
            reason = rejection_reason(source, model_line)
    return {
        "source": source,
        "line": kept,
        "source_words": source_count,
        "line_words": len(split_words(kept)),
        "path": path,
        "model_line": model_line,
        "reason": reason,
        "seconds": elapsed,
    }


def shrink_pile(items: list[str], ask) -> dict:
    rows = [shrink_one(item, ask) for item in items]
    source_words = sum(row["source_words"] for row in rows)
    line_words = sum(row["line_words"] for row in rows)
    return {
        "items": rows,
        "source_words": source_words,
        "line_words": line_words,
        "words_not_reread": source_words - line_words,
        "model_kept": sum(1 for row in rows if row["path"] == "model"),
        "fallback": sum(1 for row in rows if row["path"] == "fallback"),
        "already_short": sum(1 for row in rows if row["path"] == "already_short"),
    }


def render_text(report: dict) -> str:
    lines = [
        f"{len(report['items'])} postponed",
        f"model kept {report['model_kept']}",
        f"thrown away {report['fallback']}",
        f"already one line {report['already_short']}",
        f"{report['source_words']} words in, {report['line_words']} words left",
        f"{report['words_not_reread']} words you do not have to reread",
        "",
    ]
    for index, row in enumerate(report["items"], start=1):
        lines.append(f"{index}. {row['line']}")
        lines.append(f"   {row['line_words']} words from {row['source_words']} · {row['reason']}")
        if row["model_line"] and row["path"] != "model":
            lines.append(f"   model said: {row['model_line']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(report: dict) -> str:
    cards = []
    for row in report["items"]:
        rejected = ""
        if row["model_line"] and row["path"] != "model":
            rejected = f"<p class='rejected'>Thrown away: {escape(row['model_line'])}</p>"
        cards.append(
            "<article>"
            f"<h2>{escape(row['line'])}</h2>"
            f"<p class='meta'>{row['line_words']} words from {row['source_words']} · {escape(row['reason'])}</p>"
            f"<p class='source'>{escape(row['source'])}</p>"
            f"{rejected}"
            "</article>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Later Line</title>
<style>
  body {{ margin: 0; background: #f4f1ea; color: #231f20; font: 18px/1.45 Georgia, serif; }}
  main {{ max-width: 740px; margin: 0 auto; padding: 48px 24px 80px; }}
  h1 {{ font-weight: 500; font-size: 42px; margin: 0 0 8px; }}
  .tally {{ color: #3d5f58; margin: 0 0 32px; }}
  article {{ background: white; border: 1px solid #ddd6c8; padding: 20px 22px; margin: 0 0 16px; }}
  h2 {{ font-size: 22px; font-weight: 500; margin: 0 0 8px; }}
  .meta {{ margin: 0 0 10px; color: #3d5f58; font: 14px/1.4 ui-monospace, monospace; }}
  .source {{ margin: 0; color: #5c564e; }}
  .rejected {{ margin: 12px 0 0; color: #8a3b32; font: 14px/1.4 ui-monospace, monospace; }}
</style>
</head>
<body>
<main>
  <h1>Later Line</h1>
  <p class="tally">{report['source_words']} words in · {report['line_words']} left · {report['words_not_reread']} you do not reread · model kept {report['model_kept']} · thrown away {report['fallback']}</p>
  {''.join(cards)}
</main>
</body>
</html>
"""


def escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Shrink postponed tasks to one shorter line.")
    parser.add_argument("pile", type=Path, help="Text file of postponed tasks, separated by blank lines")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--url", default=OLLAMA_URL)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--rules-only", action="store_true", help="Do not call the model")
    parser.add_argument("--json", type=Path, help="Write the report JSON here")
    parser.add_argument("--html", type=Path, help="Write a page of the same report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    items = split_pile(args.pile.read_text())
    if not items:
        print("The pile is empty.", file=sys.stderr)
        return 1

    def ask(source: str) -> str:
        if args.rules_only:
            return ""
        return ask_ollama(source, args.model, args.url, args.timeout)

    report = shrink_pile(items, ask)
    report["model"] = None if args.rules_only else args.model
    text = render_text(report)
    sys.stdout.write(text)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(render_html(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
