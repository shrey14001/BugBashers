"""
bitbucket/pr_creator.py
Creates a fix branch, applies the unified diff patch, and opens a PR
on Bitbucket using the REST API.
"""

import os
import re
import time
import hashlib
import subprocess
import tempfile
import requests
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def normalize_repo_file_path(file_path: str) -> str:
    """
    Bitbucket src API expects a path relative to repo root (e.g. app/Controller/Foo.php).
    Strips server prefixes like /var/sites/{domain}/.
    """
    path = file_path.lstrip("/")
    match = re.match(r"var/sites/[^/]+/(.+)", path)
    if match:
        return match.group(1)
    return path


def _normalize_workspace(raw: str | None) -> str | None:
    """
    BITBUCKET_WORKSPACE must be the slug only (e.g. 'bizom'), not a full URL.
    Accepts pasted URLs and extracts the workspace slug.
    """
    if not raw:
        return None
    raw = raw.strip().rstrip("/")
    match = re.match(r"https?://bitbucket\.org/([^/]+)", raw)
    if match:
        return match.group(1)
    return raw


WORKSPACE = _normalize_workspace(os.getenv("BITBUCKET_WORKSPACE"))
AUTH      = (
    os.getenv("BITBUCKET_USERNAME"),
    os.getenv("BITBUCKET_APP_PASSWORD"),
)
BB_BASE   = "https://api.bitbucket.org/2.0"


@dataclass
class PRResult:
    pr_id: int
    pr_url: str
    branch: str
    commit_hash: str


# ── Low-level Bitbucket API helpers ───────────────────────────────────────────

def _bb(method: str, path: str, **kwargs) -> dict:
    url = f"{BB_BASE}/repositories/{WORKSPACE}/{path}"
    r = requests.request(method, url, auth=AUTH, timeout=15, **kwargs)
    r.raise_for_status()
    return r.json() if r.content else {}


def get_default_branch(repo_slug: str) -> str:
    data = _bb("GET", f"{repo_slug}")
    return 'dummy_branch'
    return data.get("mainbranch", {}).get("name", "main")


def get_branch_head(repo_slug: str, branch: str) -> str:
    data = _bb("GET", f"{repo_slug}/refs/branches/{branch}")
    return data["target"]["hash"]


def create_branch(repo_slug: str, branch_name: str, from_commit: str) -> None:
    _bb("POST", f"{repo_slug}/refs/branches", json={
        "name": branch_name,
        "target": {"hash": from_commit},
    })


def get_file_content(repo_slug: str, file_path: str, commit: str) -> str:
    clean = normalize_repo_file_path(file_path)
    url = f"{BB_BASE}/repositories/{WORKSPACE}/{repo_slug}/src/{commit}/{clean}"
    r = requests.get(url, auth=AUTH, timeout=10)
    r.raise_for_status()
    return r.text


def commit_file(
    repo_slug: str,
    branch: str,
    file_path: str,
    new_content: str,
    commit_message: str,
) -> str:
    """
    Upload the patched file content to Bitbucket via the src endpoint.
    Returns the new commit hash.
    """
    clean = normalize_repo_file_path(file_path)
    url   = f"{BB_BASE}/repositories/{WORKSPACE}/{repo_slug}/src"
    r = requests.post(
        url,
        auth=AUTH,
        data={
            "branch": branch,
            "message": commit_message,
            clean: new_content,          # filename=content
        },
        timeout=15,
    )
    r.raise_for_status()
    # Fetch the new head commit of the branch
    return get_branch_head(repo_slug, branch)


def open_pr(
    repo_slug: str,
    branch: str,
    base_branch: str,
    title: str,
    description: str,
) -> dict:
    return _bb("POST", f"{repo_slug}/pullrequests", json={
        "title": title,
        "description": description,
        "source": {"branch": {"name": branch}},
        "destination": {"branch": {"name": base_branch}},
        "reviewers": [],
        "close_source_branch": True,
    })


# ── Patch application (local git apply) ───────────────────────────────────────

def _diff_strip_level(diff_patch: str, rel_path: str) -> int:
    """
    Detect the correct -p (strip) level for the patch command.

    The LLM may emit headers in two styles:
      a/app/Controller/Foo.php  → -p1 strips the leading "a/"
      app/Controller/Foo.php    → -p0 (no prefix to strip)
    """
    for line in diff_patch.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            path = line[4:].split("\t")[0].strip()
            if path.startswith("a/") or path.startswith("b/"):
                return 1
            return 0
    return 1


def apply_patch_to_content(
    original_content: str,
    diff_patch: str,
    repo_relative_path: str,
) -> str:
    """
    Apply a unified diff patch to file content.

    Tries in order:
      1. GNU patch with auto-detected strip level (-p0 or -p1) + fuzz
      2. Context-based search (ignores wrong @@ line numbers from LLM)
      3. Original + TODO comment
    """
    rel_path = normalize_repo_file_path(repo_relative_path)
    strip = _diff_strip_level(diff_patch, rel_path)
    last_err = ""

    # 1) patch CLI
    with tempfile.TemporaryDirectory() as tmpdir:
        target_path = os.path.join(tmpdir, rel_path)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        with open(target_path, "w") as f:
            f.write(original_content)
        with open(os.path.join(tmpdir, "fix.patch"), "w") as f:
            f.write(diff_patch)

        result = subprocess.run(
            ["patch", f"-p{strip}", "-l", "--fuzz=10", "-u", "-i", "fix.patch"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            with open(target_path) as f:
                return f.read()
        last_err = (result.stderr or result.stdout or "").strip()

    # 2) Context search — find hunk by surrounding lines regardless of line numbers
    contextual = apply_patch_by_context(original_content, diff_patch)
    if contextual is not None:
        return contextual

    # 3) Give up — commit file with TODO so PR still opens for human review
    note = (
        "\n// TODO: AUTO-FIX PATCH COULD NOT BE APPLIED\n"
        f"// {last_err.replace(chr(10), chr(10) + '// ') if last_err else 'no matching context found in file'}\n"
    )
    return original_content + note


# ── Main entry point ──────────────────────────────────────────────────────────

def create_fix_pr(
    repo_slug: str,
    file_path: str,
    error_message: str,
    diff_patch: str,
    commit_hash: str,
) -> PRResult:
    """
    Full flow:
      1. Create a fix branch from commit_hash
      2. Apply the AI-generated diff to the file
      3. Commit the patched file
      4. Open a PR back to the default branch
    """
    base_branch = get_default_branch(repo_slug)

    # Unique branch name
    short_hash = hashlib.md5(error_message.encode()).hexdigest()[:8]
    branch_name = f"auto-fix-{short_hash}-{int(time.time())}"

    # 1. Create branch from the bad commit
    create_branch(repo_slug, branch_name, commit_hash)

    # 2. Fetch original file, apply patch
    original = get_file_content(repo_slug, file_path, commit_hash)
    patched  = apply_patch_to_content(original, diff_patch, file_path)

    # 3. Commit patched file
    new_commit = commit_file(
        repo_slug=repo_slug,
        branch=branch_name,
        file_path=file_path,
        new_content=patched,
        commit_message=f"[AUTO-FIX] {error_message[:80]}",
    )

    # 4. Open PR
    pr_description = f"""
## 🤖 Automated Fix — Generated by AutoFix Agent

### Error
```
{error_message}
```

### File Changed
`{file_path}`

### AI-Generated Patch
```diff
{diff_patch}
```

---
> **Please review carefully before merging.**
> This PR was auto-generated. The patch was applied to commit `{commit_hash}`.
    """.strip()

    pr_data = open_pr(
        repo_slug=repo_slug,
        branch=branch_name,
        base_branch=base_branch,
        title=f"[AUTO-FIX] {error_message[:72]}",
        description=pr_description,
    )

    return PRResult(
        pr_id=pr_data["id"],
        pr_url=pr_data["links"]["html"]["href"],
        branch=branch_name,
        commit_hash=new_commit,
    )