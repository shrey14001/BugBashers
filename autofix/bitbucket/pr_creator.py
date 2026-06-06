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
    if not r.ok:
        try:
            body = r.json()
        except Exception:
            body = r.text[:500]
        raise requests.HTTPError(
            f"{r.status_code} {r.reason} — {body}", response=r
        )
    return r.json() if r.content else {}


def get_default_branch(repo_slug: str) -> str:
    data = _bb("GET", f"{repo_slug}")
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
    r.encoding = "utf-8"
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
        # File content must be multipart (files=) to preserve UTF-8.
        # Sending it in data= uses url-encoding which corrupts multi-byte chars.
        data={
            "branch": branch,
            "message": commit_message,
        },
        files={clean: (clean, new_content.encode("utf-8"), "text/plain; charset=utf-8")},
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


def apply_patch_by_context(original_content: str, diff_patch: str) -> str | None:
    """
    Hunk-level fallback applicator for LLM-generated diffs.

    Parses each @@ hunk into (op, content) triples, locates where the hunk
    belongs in the file (by matching context + minus lines, with fuzzy fallback),
    then replays the hunk: skip '-' lines, keep ' ' lines, insert '+' lines.

    Handles pure insertions (no '-' lines), wrong line numbers, and minor
    content differences from the LLM. Force-applies at the stated line number
    if all matching fails.
    """
    import re as _re
    from difflib import SequenceMatcher

    def _parse_diff(patch: str):
        """Yield (hint_0based, ops) where ops = list of (op, content_without_prefix)."""
        lines = patch.splitlines()
        i = 0
        while i < len(lines):
            m = _re.match(r"^@@ -(\d+)", lines[i])
            if m:
                hint = int(m.group(1)) - 1
                i += 1
                ops = []
                while i < len(lines) and not lines[i].startswith(("@@ ", "--- ", "+++ ")):
                    ln = lines[i]
                    if ln.startswith("-") and not ln.startswith("---"):
                        ops.append(("-", ln[1:]))
                    elif ln.startswith("+") and not ln.startswith("+++"):
                        ops.append(("+", ln[1:]))
                    else:
                        # context line (starts with ' ' or is blank)
                        ops.append((" ", ln[1:] if ln.startswith(" ") else ln))
                    i += 1
                if any(op != " " for op, _ in ops):
                    yield hint, ops
            else:
                i += 1

    def _find_start(file_lines: list, ops: list, hint: int,
                    search_start: int, search_end: int) -> int:
        """
        Find the file index where this hunk starts.
        Matches the sequence of context+minus lines (ignoring pure '+' lines).
        Uses fuzzy comparison (ratio ≥ 0.7) to tolerate minor LLM rewrites.
        """
        expected = [(op, c.strip()) for op, c in ops if op in (" ", "-")]
        if not expected:
            return hint  # pure insertion — use hint directly

        n = len(file_lines)
        for start in range(max(0, search_start), min(n, search_end)):
            src = start
            ok = True
            for op, content in expected:
                if src >= n:
                    ok = False
                    break
                if content:
                    ratio = SequenceMatcher(
                        None, content.lower(),
                        file_lines[src].strip().lower()
                    ).ratio()
                    if ratio < 0.7:
                        ok = False
                        break
                src += 1
            if ok:
                return start
        return -1

    file_lines = original_content.splitlines(keepends=True)
    changed    = False

    for hint, ops in _parse_diff(diff_patch):
        n = len(file_lines)

        # Locate hunk: near hint → whole file → force at hint
        start = _find_start(file_lines, ops, hint, hint - 50, hint + 100)
        if start == -1:
            start = _find_start(file_lines, ops, hint, 0, n)
        if start == -1:
            start = min(max(0, hint), n - 1)

        # Replay the hunk
        result  = list(file_lines[:start])
        src_idx = start
        for op, content in ops:
            if op == " ":
                if src_idx < n:
                    result.append(file_lines[src_idx])
                src_idx += 1
            elif op == "-":
                src_idx += 1            # delete: advance source, don't emit
            else:                       # "+"
                ref   = file_lines[src_idx] if src_idx < n else (result[-1] if result else "")
                ind   = " " * (len(ref) - len(ref.lstrip()))
                result.append(ind + content.strip() + "\n")

        result.extend(file_lines[src_idx:])
        file_lines = result
        changed    = True

    if not changed:
        return None
    patched = "".join(file_lines)
    return patched if patched != original_content else None


def _normalise_diff(diff: str) -> str:
    """
    Fix common LLM diff formatting issues before handing to GNU patch:
    1. Blank context lines inside hunks must start with a single space.
    2. Lines that are not valid diff lines inside a hunk are promoted to context.
    3. @@ hunk header counts are recomputed to match the actual hunk content,
       so GNU patch never hits "unexpected end of file".
    """
    import re as _re

    lines = diff.splitlines()

    # ── Pass 1: fix blank/unlabelled lines inside hunks ───────────────────────
    fixed: list[str] = []
    in_hunk = False
    for line in lines:
        if line.startswith(("--- ", "+++ ")):
            in_hunk = False
            fixed.append(line)
        elif line.startswith("@@ "):
            in_hunk = True
            fixed.append(line)
        elif in_hunk:
            if line == "":
                fixed.append(" ")
            elif line[0] not in (" ", "+", "-", "\\"):
                fixed.append(" " + line)
            else:
                fixed.append(line)
        else:
            fixed.append(line)

    # ── Pass 2: recompute @@ counts to match actual hunk content ─────────────
    _HUNK_RE = _re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)")
    out: list[str] = []
    i = 0
    while i < len(fixed):
        line = fixed[i]
        m = _HUNK_RE.match(line)
        if m:
            old_start, new_start, rest = m.group(1), m.group(2), m.group(3)
            i += 1
            hunk: list[str] = []
            while i < len(fixed) and not fixed[i].startswith(("@@ ", "--- ", "+++ ")):
                hunk.append(fixed[i])
                i += 1
            old_count = sum(1 for l in hunk if l and l[0] in (" ", "-"))
            new_count = sum(1 for l in hunk if l and l[0] in (" ", "+"))
            out.append(f"@@ -{old_start},{old_count} +{new_start},{new_count} @@{rest}")
            out.extend(hunk)
        else:
            out.append(line)
            i += 1

    return "\n".join(out)


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
    diff_patch = _normalise_diff(diff_patch)
    strip = _diff_strip_level(diff_patch, rel_path)
    last_err = ""

    # 0) Reject diffs that delete >40% of original lines — LLMs sometimes
    #    emit full-file replacements instead of minimal patches.
    orig_line_count = len(original_content.splitlines())
    deletions = sum(
        1 for ln in diff_patch.splitlines()
        if ln.startswith("-") and not ln.startswith("---")
    )
    additions = sum(
        1 for ln in diff_patch.splitlines()
        if ln.startswith("+") and not ln.startswith("+++")
    )
    print(
        f"[PR] Patch stats: orig={orig_line_count} lines, "
        f"diff -{deletions}/+{additions} lines", flush=True
    )
    if orig_line_count > 10 and deletions > orig_line_count * 0.4:
        pct = int(deletions / orig_line_count * 100)
        note = (
            "\n// TODO: AUTO-FIX PATCH COULD NOT BE APPLIED\n"
            f"// Diff was too destructive — deleted {pct}% of file lines "
            f"({deletions} of {orig_line_count}). LLM likely generated a full-file replacement.\n"
        )
        print(f"[PR] Rejected destructive diff: {deletions}/{orig_line_count} lines deleted ({pct}%)", flush=True)
        return original_content + note

    # 1) patch CLI
    with tempfile.TemporaryDirectory() as tmpdir:
        # Place the file at the path the diff header actually references
        # (after stripping the a/ or b/ prefix), not the caller's rel_path.
        # If they differ (e.g. diff has app/laravel/... but rel_path is
        # app/...) the patch command would say "No file to patch".
        diff_target = _diff_target_file(diff_patch)
        file_in_tmpdir = diff_target if diff_target else rel_path
        target_path = os.path.join(tmpdir, file_in_tmpdir)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        with open(target_path, "w") as f:
            f.write(original_content)
        with open(os.path.join(tmpdir, "fix.patch"), "w") as f:
            f.write(diff_patch)

        result = subprocess.run(
            ["patch", f"-p{strip}", "-l", "--fuzz=10", "-u", "-i", "fix.patch",
             "--no-backup-if-mismatch", "--force"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=10,
        )
        if result.returncode == 0:
            with open(target_path) as f:
                patched_by_gnu = f.read()
            # Sanity check: LLM diffs with bad context can cause GNU patch to
            # "succeed" but strip most of the file. Reject if >30% of lines lost.
            orig_lines  = len(original_content.splitlines())
            patch_lines = len(patched_by_gnu.splitlines())
            if orig_lines > 10 and patch_lines < orig_lines * 0.7:
                last_err = (
                    f"patch output lost too many lines "
                    f"({patch_lines} vs {orig_lines} original) — likely misapplied"
                )
                print(f"[PR] GNU patch sanity check failed: {last_err}", flush=True)
            else:
                return patched_by_gnu
        last_err = last_err or (result.stderr or result.stdout or "").strip()

    # 2) Context search — find hunk by surrounding lines regardless of line numbers
    contextual = apply_patch_by_context(original_content, diff_patch)
    if contextual is not None:
        ctx_lines = len(contextual.splitlines())
        if orig_line_count > 10 and ctx_lines < orig_line_count * 0.7:
            print(
                f"[PR] apply_patch_by_context sanity check failed: "
                f"{ctx_lines} vs {orig_line_count} original lines", flush=True
            )
        else:
            return contextual

    # 3) Give up — commit file with TODO so PR still opens for human review
    note = (
        "\n// TODO: AUTO-FIX PATCH COULD NOT BE APPLIED\n"
        f"// {last_err.replace(chr(10), chr(10) + '// ') if last_err else 'no matching context found in file'}\n"
    )
    return original_content + note


# ── Diff introspection ───────────────────────────────────────────────────────

def _diff_target_file(diff_patch: str) -> str | None:
    """
    Extract the repo-relative target file path from the +++ line of the diff.
    The LLM may have targeted a different file than the error origin
    (e.g. a caller instead of the base trait that threw).
    Returns None if the path cannot be determined or is /dev/null.
    """
    for line in diff_patch.splitlines():
        if line.startswith("+++ "):
            path = line[4:].split("\t")[0].strip()
            if path.startswith(("a/", "b/")):
                path = path[2:]
            path = normalize_repo_file_path(path)
            if path and path != "dev/null":
                return path
    return None


# ── Tag helpers ───────────────────────────────────────────────────────────────

_TAG_DATE_RE = re.compile(r"(\d{8})")

def _date_from_tag(tag: str) -> str:
    """
    Extract YYYYMMDD from a tag name.
    e.g. "staged_20260115_v1.13"  → "20260115"
         "20260115_v1.33"         → "20260115"
    Falls back to today's date if no match.
    """
    m = _TAG_DATE_RE.search(tag)
    if m:
        return m.group(1)
    return time.strftime("%Y%m%d")


# ── Main entry point ──────────────────────────────────────────────────────────

def create_fix_pr(
    repo_slug: str,
    file_path: str,
    error_message: str,
    diff_patch: str,
    commit_hash: str,
    tag: str = "",
    original_content: str | None = None,
) -> PRResult:
    """
    Inspired by the Bizom hotfix shell script pattern:

      1. hotfix_{date}_{ts}    — created from the deployed tag/commit (base branch)
      2. cherry_pick_{date}_{ts} — created from hotfix branch, AI fix applied here
      3. PR: cherry_pick → hotfix branch

    This mirrors the manual hotfix flow so reviewers see a familiar PR structure.
    """
    ts        = int(time.time())
    tag_date  = _date_from_tag(tag) if tag else time.strftime("%Y%m%d")
    err_hash  = hashlib.md5(error_message.encode()).hexdigest()[:8]

    hotfix_branch      = f"hotfix_{tag_date}_{ts}"
    cherry_pick_branch = f"autofix_{tag_date}_{err_hash}_{ts}"

    # 1. Create hotfix base branch from the deployed commit (same point as the tag)
    create_branch(repo_slug, hotfix_branch, commit_hash)

    # 2. Create cherry-pick branch from hotfix branch
    hotfix_head = get_branch_head(repo_slug, hotfix_branch)
    create_branch(repo_slug, cherry_pick_branch, hotfix_head)

    # 3. Determine which file the diff actually targets.
    # The agent may have chosen a caller instead of the error origin.
    patch_file = _diff_target_file(diff_patch) or file_path

    # Claude Code generates paths relative to the local monorepo root (e.g.
    # bizomweb3), so Laravel files carry the app/laravel/ prefix.  Strip it
    # so the path matches the structure of the bizom-laravel Bitbucket repo.
    laravel_repo   = os.getenv("LARAVEL_REPO_SLUG", "bizom-laravel")
    laravel_prefix = os.getenv("BITBUCKET_LARAVEL_PATH_PREFIX", "").strip("/")
    if repo_slug == laravel_repo and laravel_prefix:
        prefix_slash = laravel_prefix + "/"
        if patch_file.startswith(prefix_slash):
            patch_file = patch_file[len(prefix_slash):]

    if patch_file != file_path:
        print(f"[PR] Diff targets {patch_file} (error was in {file_path})", flush=True)

    # 4. Get the original content for the file the diff actually targets.
    #    When the agent fixes a caller instead of the error-origin file,
    #    patch_file != file_path — we must fetch patch_file's content, not
    #    original_content (which is for the error file and would be wrong).
    if patch_file != file_path:
        print(f"[PR] Fetching content for diff target {patch_file}", flush=True)
        original = get_file_content(repo_slug, patch_file, commit_hash)
    else:
        original = original_content or get_file_content(repo_slug, patch_file, commit_hash)
    patched  = apply_patch_to_content(original, diff_patch, patch_file)

    # 5. Commit the patched file onto the cherry-pick branch
    new_commit = commit_file(
        repo_slug=repo_slug,
        branch=cherry_pick_branch,
        file_path=patch_file,
        new_content=patched,
        commit_message=f"[AUTO-FIX] {error_message[:80]}",
    )

    # 5. Open PR: cherry-pick branch → hotfix branch
    tag_note  = f"Based on tag `{tag}`." if tag else f"Based on commit `{commit_hash}`."
    file_note = f"`{patch_file}`" + (f" (error origin: `{file_path}`)" if patch_file != file_path else "")
    pr_description = f"""
## Automated Fix — Generated by AutoFix Agent

### Error
```
{error_message}
```

### File Changed
{file_note}

### AI-Generated Patch
```diff
{diff_patch}
```

---
> **Please review carefully before merging.**
> This PR was auto-generated. {tag_note}
> Branch `{cherry_pick_branch}` → `{hotfix_branch}`
    """.strip()

    pr_data = open_pr(
        repo_slug=repo_slug,
        branch=cherry_pick_branch,
        base_branch=hotfix_branch,
        title=f"[AUTO-FIX] {error_message[:72]}",
        description=pr_description,
    )

    return PRResult(
        pr_id=pr_data["id"],
        pr_url=pr_data["links"]["html"]["href"],
        branch=cherry_pick_branch,
        commit_hash=new_commit,
    )