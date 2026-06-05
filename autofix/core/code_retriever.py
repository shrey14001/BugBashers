"""
core/code_retriever.py
Fetches source code from Bitbucket at a specific commit.

Two methods:
  1. Bitbucket REST API  — primary (no git CLI needed)
  2. git CLI             — fallback (requires local repo clone)
"""

import os
import subprocess
import requests
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

WORKSPACE    = os.getenv("BITBUCKET_WORKSPACE")
BB_AUTH      = (
    os.getenv("BITBUCKET_USERNAME"),
    os.getenv("BITBUCKET_APP_PASSWORD"),
)
BB_BASE      = "https://api.bitbucket.org/2.0"
WINDOW_LINES = 30        # lines of context around the error line


@dataclass
class CodeSnippet:
    file_path: str
    start_line: int
    end_line: int
    content: str          # the windowed snippet with line numbers + >>> marker
    full_source: str      # entire file (used for patching)


# ── Internal deployment API ───────────────────────────────────────────────────

BIZOM_VERSION_API = "https://backuplogin.bizombackup.in/companies/getCompanyVersionFromDomain"


def _domain_to_dbname(domain: str) -> str:
    """
    Convert a Bizom domain to its database name.
    e.g. "nda.bizom.in"  →  "nda_bizom_in_bizom"
         "demo.bizom.in" →  "demo_bizom_in_bizom"
    """
    return domain.replace(".", "_") + "_bizom"


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