#!/usr/bin/env python3
"""Aggregate complexity metrics for a repository.

Reports size and shape only: file counts, line counts, AST node counts, and
symbol/edge *counts*. It never prints identifiers, paths, or any source text, so
the output can be published without disclosing the corpus.

Usage:
    harness/repo_complexity.py <repo-path> [--json]
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys

CODE_EXT = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".rb": "Ruby",
    ".sh": "Shell",
    ".sql": "SQL",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", "dist", "build"}


def count_lines(text: str) -> tuple[int, int, int]:
    """Return (code, comment, blank) line counts, best effort."""
    code = comment = blank = 0
    in_block = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            blank += 1
            continue
        if in_block:
            comment += 1
            if "*/" in line:
                in_block = False
            continue
        if line.startswith("/*"):
            comment += 1
            if "*/" not in line:
                in_block = True
            continue
        if line.startswith(("#", "//", "--", "*")):
            comment += 1
            continue
        code += 1
    return code, comment, blank


def python_metrics(path: pathlib.Path) -> dict:
    counts = {"classes": 0, "functions": 0, "methods": 0, "imports": 0, "ast_nodes": 0, "max_depth": 0}
    try:
        tree = ast.parse(path.read_text(errors="replace"))
    except SyntaxError:
        return counts

    def depth(node: ast.AST, level: int = 0) -> None:
        counts["ast_nodes"] += 1
        counts["max_depth"] = max(counts["max_depth"], level)
        for child in ast.iter_child_nodes(node):
            depth(child, level + 1)

    depth(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            counts["classes"] += 1
            counts["methods"] += sum(isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) for b in node.body)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            counts["functions"] += 1
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            counts["imports"] += 1
    return counts


def measure(root: pathlib.Path) -> dict:
    files = 0
    total_code = total_comment = total_blank = 0
    by_language: dict[str, dict] = {}
    py = {"classes": 0, "functions": 0, "methods": 0, "imports": 0, "ast_nodes": 0, "max_depth": 0}
    dirs = set()

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        lang = CODE_EXT.get(path.suffix)
        if lang is None:
            continue
        files += 1
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        code, comment, blank = count_lines(text)
        total_code += code
        total_comment += comment
        total_blank += blank
        entry = by_language.setdefault(lang, {"files": 0, "code": 0, "comment": 0, "blank": 0})
        entry["files"] += 1
        entry["code"] += code
        entry["comment"] += comment
        entry["blank"] += blank
        if path.suffix == ".py":
            for key, value in python_metrics(path).items():
                if key == "max_depth":
                    py[key] = max(py[key], value)
                else:
                    py[key] += value
        if path.parent != root:
            dirs.add(path.parent.relative_to(root).parts[0])

    py["modules"] = by_language.get("Python", {}).get("files", 0)
    return {
        "root_label": "reference-corpus",
        "files": files,
        "directories": len(dirs),
        "lines": {"code": total_code, "comment": total_comment, "blank": total_blank,
                  "total": total_code + total_comment + total_blank},
        "languages": dict(sorted(by_language.items(), key=lambda kv: -kv[1]["code"])),
        "python": py,
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    root = pathlib.Path(argv[0]).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    result = measure(root)

    if "--json" in argv[1:]:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    print(f"Files: {result['files']}   Directories: {result['directories']}")
    print(f"Lines: {result['lines']['code']} code, {result['lines']['comment']} comment, "
          f"{result['lines']['blank']} blank ({result['lines']['total']} total)")
    print("Languages (by code lines):")
    for lang, data in result["languages"].items():
        print(f"  {lang:12} {data['files']:5} files  {data['code']:7} code")
    py = result["python"]
    print("Python shape:")
    print(f"  modules {py['modules']}, classes {py['classes']}, functions {py['functions']}, "
          f"methods {py['methods']}, import statements {py['imports']}")
    print(f"  AST nodes {py['ast_nodes']}, max AST depth {py['max_depth']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
