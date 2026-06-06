"""
core/code_retriever.py
Fetches source code from Bitbucket at a specific commit.

Two methods:
  1. Bitbucket REST API  — primary (no git CLI needed)
  2. git CLI             — fallback (requires local repo clone)
"""

import os
import re
import subprocess
import requests
from dataclasses import dataclass
from dotenv import load_dotenv

try:
    from tree_sitter import Language, Parser as TSParser
    import tree_sitter_php as _tsphp
    _TS_LANG = Language(_tsphp.language_php())
    _TS_AVAILABLE = True
except Exception:
    _TS_AVAILABLE = False

_METHOD_NODE_TYPES = {"method_declaration", "function_definition"}

load_dotenv()

WORKSPACE    = os.getenv("BITBUCKET_WORKSPACE")
BB_AUTH      = (
    os.getenv("BITBUCKET_USERNAME"),
    os.getenv("BITBUCKET_APP_PASSWORD"),
)
BB_BASE      = "https://api.bitbucket.org/2.0"
WINDOW_LINES = 15        # lines of context around the error line


@dataclass
class CodeSnippet:
    file_path: str
    start_line: int
    end_line: int
    content: str          # the windowed snippet with line numbers + >>> marker
    full_source: str      # entire file (used for patching)


# ── Internal deployment API ───────────────────────────────────────────────────

BIZOM_VERSION_API = "https://devlogin.bizomdev.in/companies/getCompanyVersionFromDomain"


def _domain_to_dbname(domain: str) -> str:
    """
    Convert a Bizom domain to its database name.
    e.g. "nda.bizom.in"  →  "nda_bizom_in_bizom"
         "demo.bizom.in" →  "demo_bizom_in_bizom"
    """
    return domain + "_bizomdev_in_bizom"


def resolve_commit(domain: str, framework: str = "cakephp2") -> dict:
    """
    Calls the Bizom version API to get the deployed commit for a domain.

    Returns: { commit_hash: str, repo_slug: str }
      - CakePHP2 errors → commit_id field,       repo_slug from BITBUCKET_REPO_SLUG
      - Laravel errors  → laravel_commit_id field, repo_slug from LARAVEL_REPO_SLUG
    """
    dbname = _domain_to_dbname(domain)
    try:
        r = requests.post(
            BIZOM_VERSION_API,
            json={"dbname": dbname},
            timeout=10,
        )
        r.raise_for_status()
        body = r.json()
        if not body.get("Result"):
            raise RuntimeError(f"API returned Result=false: {body.get('Reason', 'unknown')}")

        data = body["Data"]

        if framework == "laravel":
            commit_hash = data["laravel_commit_id"]
            repo_slug   = os.getenv("LARAVEL_REPO_SLUG", "bizom-laravel")
            tag         = data.get("laravel_tag", "")
        else:
            commit_hash = data["commit_id"]
            repo_slug   = os.getenv("BITBUCKET_REPO_SLUG", "bizomweb2")
            tag         = data.get("tag", "")

        return {"commit_hash": commit_hash, "repo_slug": repo_slug, "tag": tag}

    except Exception as e:
        raise RuntimeError(f"Deployment API failed for domain '{domain}' (dbname={dbname}): {e}")


# ── Source fetching ───────────────────────────────────────────────────────────

def fetch_file_at_commit(repo_slug: str, file_path: str, commit_hash: str) -> str:
    """Fetch raw file content from Bitbucket REST API at a specific commit."""
    # Strip leading slash if present
    clean_path = file_path.lstrip("/")
    url = f"{BB_BASE}/repositories/{WORKSPACE}/{repo_slug}/src/{commit_hash}/{clean_path}"

    r = requests.get(url, auth=BB_AUTH, timeout=10)
    if r.status_code == 404:
        raise FileNotFoundError(f"File not found in Bitbucket: {clean_path} @ {commit_hash}")
    r.raise_for_status()
    return r.text


def _window(source: str, error_line: int) -> tuple[str, int, int]:
    """
    Extract WINDOW_LINES lines above and below the error line.
    Returns (windowed_text, start_line, end_line).
    """
    lines = source.splitlines()
    start = max(0, error_line - WINDOW_LINES - 1)
    end   = min(len(lines), error_line + WINDOW_LINES)

    annotated = []
    for i, line in enumerate(lines[start:end], start=start + 1):
        marker = ">>>" if i == error_line else "   "
        annotated.append(f"{marker} {i:4d} | {line}")

    return "\n".join(annotated), start + 1, end


def get_snippet(
    repo_slug: str,
    file_path: str,
    error_line: int,
    commit_hash: str,
) -> CodeSnippet:
    """
    High-level helper: fetches the file and returns a focused CodeSnippet.
    """
    full_source = fetch_file_at_commit(repo_slug, file_path, commit_hash)
    windowed, start_line, end_line = _window(full_source, error_line)

    return CodeSnippet(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        content=windowed,
        full_source=full_source,
    )


# ── Method extraction ─────────────────────────────────────────────────────────

def _extract_method_tree_sitter(source: str, error_line: int) -> tuple[str, int, int]:
    parser = TSParser(_TS_LANG)
    tree = parser.parse(source.encode())
    lines = source.splitlines()

    def _find(node):
        s = node.start_point[0] + 1
        e = node.end_point[0] + 1
        if node.type in _METHOD_NODE_TYPES and s <= error_line <= e:
            for child in node.children:
                inner = _find(child)
                if inner:
                    return inner
            return s, e
        for child in node.children:
            r = _find(child)
            if r:
                return r
        return None

    result = _find(tree.root_node)
    if result is None:
        raise ValueError("tree-sitter: no enclosing method found")

    start, end = result

    # Log the matched node so we can confirm tree-sitter found the right method
    def _node_name(node) -> str:
        for child in node.children:
            if child.type == "name":
                return source[child.start_byte:child.end_byte].decode(errors="replace") if isinstance(source, bytes) else child.text.decode(errors="replace") if child.text else "?"
        return "?"

    matched_node = None
    def _find_node(node):
        nonlocal matched_node
        s = node.start_point[0] + 1
        e = node.end_point[0] + 1
        if node.type in _METHOD_NODE_TYPES and s == start and e == end:
            matched_node = node
            return
        for child in node.children:
            _find_node(child)

    _find_node(tree.root_node)
    if matched_node is not None:
        try:
            method_name = matched_node.child_by_field_name("name")
            name_str = method_name.text.decode(errors="replace") if method_name and method_name.text else "?"
        except Exception:
            name_str = "?"
        print(f"[CodeRetriever] tree-sitter matched: {matched_node.type} '{name_str}' "
              f"(lines {start}–{end})", flush=True)

    annotated = []
    for i, line in enumerate(lines[start - 1:end], start=start):
        marker = ">>>" if i == error_line else "   "
        annotated.append(f"{marker} {i:4d} | {line}")
    return "\n".join(annotated), start, end


def _extract_method_brace_count(source: str, error_line: int) -> tuple[str, int, int]:
    lines = source.splitlines()

    func_idx = None
    for i in range(error_line - 1, -1, -1):
        if re.search(r'\bfunction\s+\w+', lines[i]):
            func_idx = i
            break
    if func_idx is None:
        raise ValueError("brace-count: no function declaration found")

    brace_idx = func_idx
    while brace_idx < len(lines) and '{' not in lines[brace_idx]:
        brace_idx += 1
    if brace_idx >= len(lines):
        raise ValueError("brace-count: no opening brace found")

    depth = 0
    end_idx = brace_idx
    for i in range(brace_idx, len(lines)):
        depth += lines[i].count('{') - lines[i].count('}')
        if depth == 0:
            end_idx = i
            break

    start_line = func_idx + 1
    end_line = end_idx + 1
    annotated = []
    for i, line in enumerate(lines[func_idx:end_idx + 1], start=start_line):
        marker = ">>>" if i == error_line else "   "
        annotated.append(f"{marker} {i:4d} | {line}")
    return "\n".join(annotated), start_line, end_line


def _log_extraction(strategy: str, result: tuple) -> None:
    content, start, end = result
    signature = next((l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("//") and not l.strip().startswith("*")), "?")
    print(f"[CodeRetriever] {strategy}: lines {start}–{end} ({end - start + 1} lines) | {signature[:120]}", flush=True)


def _extract_method(source: str, error_line: int) -> tuple[str, int, int]:
    """tree-sitter → brace count → ±30 window."""
    if _TS_AVAILABLE:
        try:
            result = _extract_method_tree_sitter(source, error_line)
            _log_extraction("tree-sitter", result)
            return result
        except Exception as e:
            print(f"[CodeRetriever] tree-sitter failed ({e}) — trying brace count.", flush=True)
    try:
        result = _extract_method_brace_count(source, error_line)
        _log_extraction("brace-count", result)
        return result
    except Exception as e:
        print(f"[CodeRetriever] Brace count failed ({e}) — falling back to ±{WINDOW_LINES} window.", flush=True)
        result = _window(source, error_line)
        _log_extraction("window-fallback", result)
        return result


def get_method_snippet(
    repo_slug: str,
    file_path: str,
    error_line: int,
    commit_hash: str,
) -> CodeSnippet:
    """Like get_snippet but extracts the full enclosing method body."""
    full_source = fetch_file_at_commit(repo_slug, file_path, commit_hash)
    content, start_line, end_line = _extract_method(full_source, error_line)
    return CodeSnippet(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        content=content,
        full_source=full_source,
    )


# ── Git CLI fallback (for local repos) ───────────────────────────────────────

def fetch_via_git_cli(repo_path: str, commit_hash: str, file_path: str, error_line: int) -> CodeSnippet:
    """
    Fallback: use `git show` to get file content.
    Requires a local clone of the repository.
    """
    cmd = ["git", "-C", repo_path, "show", f"{commit_hash}:{file_path}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

    if result.returncode != 0:
        raise RuntimeError(f"git show failed: {result.stderr}")

    full_source = result.stdout
    windowed, start_line, end_line = _window(full_source, error_line)

    return CodeSnippet(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        content=windowed,
        full_source=full_source,
    )