#!/usr/bin/env python3
"""Import issues from a UX tracker HTML file into .issuetracker/ format.

Usage:
    python scripts/import_ux_tracker.py <path-to-ux-tracker.html> <path-to-target-project> [--force]

Example:
    python scripts/import_ux_tracker.py \\
        /path/to/ux-tracker.html \\
        /path/to/project
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_issues_js(html: str) -> str:
    """Extract the raw JS array string from const issues = [...]."""
    # Find 'const issues = ['
    start_marker = "const issues = ["
    start = html.find(start_marker)
    if start == -1:
        raise ValueError("Could not find 'const issues = [' in HTML file.")

    # Walk forward to find the matching '];'
    bracket_start = start + len(start_marker) - 1  # points at '['
    depth = 0
    i = bracket_start
    while i < len(html):
        ch = html[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                # Confirm it's followed by ';'
                return html[bracket_start : i + 1]
        i += 1
    raise ValueError("Could not find closing '];' for issues array.")


# ---------------------------------------------------------------------------
# JS -> JSON cleanup
# ---------------------------------------------------------------------------

def js_to_json(js: str) -> str:
    """Convert a JavaScript object/array literal to valid JSON.

    Handles:
    - // line comments
    - unquoted object keys
    - single-quoted strings
    - trailing commas before } or ]
    """
    # 1. Remove // line comments (but not inside strings)
    js = _remove_line_comments(js)

    # 2. Convert single-quoted strings to double-quoted
    js = _convert_single_quotes(js)

    # 3. Quote unquoted keys:  word:  ->  "word":
    js = re.sub(r'(?<!["\w])([a-zA-Z_][a-zA-Z0-9_]*)(\s*):', _quote_key, js)

    # 4. Remove trailing commas before } or ]
    js = re.sub(r",(\s*[}\]])", r"\1", js)

    return js


def _remove_line_comments(s: str) -> str:
    """Remove // comments, respecting string literals."""
    result = []
    i = 0
    in_string = False
    string_char = None
    while i < len(s):
        ch = s[i]
        if in_string:
            result.append(ch)
            if ch == "\\" and i + 1 < len(s):
                # escaped char — include next char too
                i += 1
                result.append(s[i])
            elif ch == string_char:
                in_string = False
        else:
            if ch in ('"', "'"):
                in_string = True
                string_char = ch
                result.append(ch)
            elif ch == "/" and i + 1 < len(s) and s[i + 1] == "/":
                # skip to end of line
                while i < len(s) and s[i] != "\n":
                    i += 1
                continue
            else:
                result.append(ch)
        i += 1
    return "".join(result)


def _convert_single_quotes(s: str) -> str:
    """Replace single-quoted strings with double-quoted strings."""
    result = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '"':
            # already a double-quoted string — copy verbatim
            result.append(ch)
            i += 1
            while i < len(s):
                c = s[i]
                result.append(c)
                if c == "\\" and i + 1 < len(s):
                    i += 1
                    result.append(s[i])
                elif c == '"':
                    break
                i += 1
        elif ch == "'":
            # single-quoted string — convert to double-quoted
            result.append('"')
            i += 1
            while i < len(s):
                c = s[i]
                if c == "\\" and i + 1 < len(s):
                    next_c = s[i + 1]
                    if next_c == "'":
                        result.append("'")
                        i += 2
                        continue
                    else:
                        result.append(c)
                        result.append(next_c)
                        i += 2
                        continue
                elif c == "'":
                    result.append('"')
                    break
                elif c == '"':
                    result.append('\\"')
                else:
                    result.append(c)
                i += 1
            # end of single-quoted string
        else:
            result.append(ch)
        i += 1
    return "".join(result)


def _quote_key(m: re.Match) -> str:
    key = m.group(1)
    spacing = m.group(2)
    # Don't re-quote if it's a JSON keyword or already inside a string context
    # (the regex already guards against starting after " or word char)
    return f'"{key}"{spacing}:'


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------

STATUS_MAP = {
    "IMPLEMENTED": "done",
    "DEFERRED": "open",
    "REJECTED": "closed",
}

PRIORITY_MAP = {
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
}

VERDICT_MAP = {
    "APPROVE": "approve",
    "DEFER": "defer",
    "BLOCK": "reject",
    "BLOCK W/O FIX": "reject",
    "N/A": None,
    "—": None,
    "-": None,
    "": None,
}


def _map_verdict(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    # Handle variants like "APPROVE (critical)"
    upper = s.upper()
    if upper.startswith("APPROVE"):
        return "approve"
    if upper.startswith("BLOCK"):
        return "reject"
    if upper.startswith("DEFER"):
        return "defer"
    return VERDICT_MAP.get(upper, None)


def transform_issue(src: dict) -> dict:
    """Transform a UX tracker issue object into the .issuetracker issue format."""
    now = datetime.now(timezone.utc).isoformat()

    raw_status = src.get("status", "DEFERRED")
    status = STATUS_MAP.get(raw_status, "open")

    raw_priority = src.get("severity", "MEDIUM")
    priority = PRIORITY_MAP.get(raw_priority.upper(), "medium")

    category = src.get("category", "")
    labels = [category] if category else []

    # Reviews
    def make_review(verdict_raw, notes_raw):
        return {
            "verdict": _map_verdict(verdict_raw),
            "notes": notes_raw or "",
        }

    reviews = {
        "PM": make_review(src.get("pm"), src.get("pmNotes")),
        "Dev Lead": make_review(src.get("dev"), src.get("devNotes")),
        "Security": make_review(src.get("security"), src.get("secNotes")),
    }

    # userVote
    user_vote_text = src.get("userVote", "")
    user_vote = {
        "verdict": None,
        "notes": user_vote_text if user_vote_text else "",
    }

    issue = {
        "id": src["id"],
        "createdAt": now,
        "updatedAt": now,
        "title": src.get("issue", ""),
        "description": "",
        "status": status,
        "priority": priority,
        "labels": labels,
        "projectId": None,
        "blockedBy": [],
        "cycle": src.get("cycle"),
        "personas": src.get("personas", []),
        "files": src.get("files", []),
        "reviews": reviews,
        "userVote": user_vote,
    }

    # Include implCycle if present
    if "implCycle" in src:
        issue["implCycle"] = src["implCycle"]

    return issue


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import issues from a UX tracker HTML file into .issuetracker/ format."
    )
    parser.add_argument("html_file", help="Path to the UX tracker HTML file.")
    parser.add_argument("target_project", help="Path to the target project directory.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing .issuetracker/ without prompting.",
    )
    args = parser.parse_args()

    html_path = Path(args.html_file).expanduser().resolve()
    target = Path(args.target_project).expanduser().resolve()
    tracker_dir = target / ".issuetracker"

    # Validate inputs
    if not html_path.exists():
        print(f"Error: HTML file not found: {html_path}", file=sys.stderr)
        return 1
    if not target.exists():
        print(f"Error: Target project directory not found: {target}", file=sys.stderr)
        return 1

    # Check for existing .issuetracker
    if tracker_dir.exists() and not args.force:
        answer = input(
            f".issuetracker/ already exists at {tracker_dir}\n"
            "Overwrite? [y/N] "
        ).strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 0

    # Read HTML
    print(f"Reading {html_path} ...")
    html = html_path.read_text(encoding="utf-8")

    # Extract JS array
    try:
        js_array = extract_issues_js(html)
    except ValueError as e:
        print(f"Error extracting issues array: {e}", file=sys.stderr)
        return 1

    # Convert JS to JSON
    try:
        json_str = js_to_json(js_array)
        raw_issues = json.loads(json_str)
    except json.JSONDecodeError as e:
        # Show context around the error
        lines = json_str.splitlines()
        lineno = e.lineno - 1
        ctx_start = max(0, lineno - 3)
        ctx_end = min(len(lines), lineno + 4)
        context = "\n".join(
            f"  {'>>>' if i == lineno else '   '} {lines[i]}"
            for i in range(ctx_start, ctx_end)
        )
        print(
            f"Error: Failed to parse issues as JSON.\n"
            f"  {e}\n\n"
            f"Context (line {e.lineno}):\n{context}",
            file=sys.stderr,
        )
        return 1

    print(f"Found {len(raw_issues)} issues in source file.")

    # Create directory structure
    (tracker_dir / "issues").mkdir(parents=True, exist_ok=True)
    (tracker_dir / "projects").mkdir(parents=True, exist_ok=True)
    (tracker_dir / "assets").mkdir(parents=True, exist_ok=True)

    # Transform and write issues
    imported = 0
    failed = 0
    max_id = 0

    for raw in raw_issues:
        issue_id = raw.get("id")
        if issue_id is None:
            print(f"  Warning: Skipping issue with no id: {raw.get('issue', '')[:60]}")
            failed += 1
            continue

        try:
            issue = transform_issue(raw)
        except Exception as e:
            print(f"  Warning: Failed to transform issue #{issue_id}: {e}")
            failed += 1
            continue

        issue_path = tracker_dir / "issues" / f"{issue_id:03d}.json"
        try:
            _atomic_write(issue_path, issue)
            imported += 1
            if issue_id > max_id:
                max_id = issue_id
        except Exception as e:
            print(f"  Warning: Failed to write issue #{issue_id}: {e}")
            failed += 1

    # Write config
    config_path = tracker_dir / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError):
            config = {}
    else:
        config = {}

    config.setdefault("name", target.name)
    config["nextIssueId"] = max_id + 1
    config.setdefault("nextProjectId", 1)
    config.setdefault("reviewers", ["PM", "Dev Lead", "Security"])
    if "createdAt" not in config:
        config["createdAt"] = datetime.now(timezone.utc).isoformat()

    _atomic_write(config_path, config)

    # Summary
    print()
    print(f"Import complete.")
    print(f"  Imported : {imported}")
    if failed:
        print(f"  Failed   : {failed}")
    print(f"  nextIssueId set to: {max_id + 1}")
    print(f"  Output   : {tracker_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
