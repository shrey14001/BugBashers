"""
demo.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AutoFix Agent — Live Demo
Reads REAL code from local git repo → sends to Groq → shows fix → saves patch
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Usage:
    python demo.py                        # interactive — paste your log
    python demo.py --sample laravel       # built-in Laravel sample
    python demo.py --sample cakephp       # built-in CakePHP sample
    python demo.py --log "raw log line"   # pass log directly
"""

import os
import re
import sys
import argparse
import subprocess
import hashlib
import datetime
from typing import Optional
from groq import Groq
from dotenv import load_dotenv

from parsers.laravel  import parse as parse_laravel
from parsers.cakephp2 import parse as parse_cakephp2

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
# REPO CONFIG — hardcoded for demo
# ══════════════════════════════════════════════════════════════════════════════

REPO_ROOT = "/Users/shrey.shukla/bizom/bizomweb3"

SERVER_PREFIX_RE = re.compile(r"^/var/sites/[^/]+/")

SKIP_PREFIXES = (
    "/usr/share/vendor_bizom/",
    "/usr/share/",
    "/vendor/",
)

WINDOW = 30


# ══════════════════════════════════════════════════════════════════════════════
# SAMPLE LOGS
# ══════════════════════════════════════════════════════════════════════════════

SAMPLE_LOGS = {
    "laravel": (
        'Function name must be a string {"userId":177,"exception":"[object] (Error(code: 0): '
        'Function name must be a string at /var/sites/uniteddistributors.bizom.in/app/laravel/app/'
        'CompanyManagement/Repositories/OutletRepository.php:14252)\n'
        '[stacktrace]\n'
        '#0 /var/sites/uniteddistributors.bizom.in/app/laravel/app/CompanyManagement/Repositories/'
        'OutletRepository.php(14215): App\\CompanyManagement\\Repositories\\OutletRepository->getExtraParams()\n'
        '#1 /var/sites/uniteddistributors.bizom.in/app/laravel/app/Http/Controllers/'
        'OutletController.php(1914): App\\CompanyManagement\\Repositories\\OutletRepository->'
        'getPendingInvoicesMultiDistributorInternal()\n'
        '#2 /usr/share/vendor_bizom/laravel/laravel_8_20251024/laravel/framework/src/Illuminate/'
        'Routing/Controller.php(54): App\\Http\\Controllers\\OutletController->getPendingInvoicesMultiDistributor()"}'
    ),
    "cakephp": (
        "2024-01-15 10:23:45 Error: Fatal error: "
        "Call to undefined method Order::findByStatus() "
        "in /var/sites/demo.bizom.in/app/Model/Order.php on line 77\n"
        "Stack trace:\n"
        "#0 /var/sites/demo.bizom.in/app/Controller/OrdersController.php(120): Order->findByStatus()\n"
        "#1 /var/sites/demo.bizom.in/app/Controller/AppController.php(44): OrdersController->index()"
    ),
}


# ══════════════════════════════════════════════════════════════════════════════
# PATH RESOLVER
# ══════════════════════════════════════════════════════════════════════════════

def is_vendor_path(path: str) -> bool:
    return any(path.startswith(p) for p in SKIP_PREFIXES)


def resolve_local_path(server_path: str) -> Optional[str]:
    if is_vendor_path(server_path):
        return None
    relative = SERVER_PREFIX_RE.sub("", server_path)
    return os.path.join(REPO_ROOT, relative)


def best_frame(parsed) -> Optional[object]:
    for frame in parsed.stack_frames:
        if not is_vendor_path(frame.file) and "/var/sites/" in frame.file:
            return frame
    return parsed.top_frame()


# ══════════════════════════════════════════════════════════════════════════════
# CODE FETCHER
# ══════════════════════════════════════════════════════════════════════════════

def fetch_code_window(local_path: str, error_line: int):
    """
    Returns (annotated_window: str, source_lines: list[str])
    Also scans backwards from error_line to find the real buggy line
    (handles cases where error_line points to closing bracket).
    """
    try:
        rel_path = os.path.relpath(local_path, REPO_ROOT)
    except ValueError:
        rel_path = local_path

    result = subprocess.run(
        ["git", "-C", REPO_ROOT, "show", f"HEAD:{rel_path}"],
        capture_output=True, text=True
    )

    if result.returncode == 0:
        source = result.stdout
        method = "git HEAD"
    elif os.path.exists(local_path):
        with open(local_path, "r", errors="replace") as f:
            source = f.read()
        method = "local file"
    else:
        return None, []

    print(f"  📂 Source   : {method} → {rel_path}")

    lines = source.splitlines()

    # Find the real buggy line — scan backwards from error_line
    # to find the first non-bracket, non-whitespace-only line
    real_error_line = error_line
    for i in range(error_line - 1, max(error_line - 10, 0), -1):
        stripped = lines[i - 1].strip() if i <= len(lines) else ""
        # Skip lines that are just closing brackets/parens
        if stripped and stripped not in (")", ");", "];", "}"):
            real_error_line = i
            break

    start = max(0, real_error_line - WINDOW - 1)
    end   = min(len(lines), real_error_line + WINDOW)

    annotated = []
    for i, line in enumerate(lines[start:end], start=start + 1):
        marker = ">>>" if i == real_error_line else "   "
        annotated.append(f"{marker} {i:4d} | {line}")

    return "\n".join(annotated), lines


# ══════════════════════════════════════════════════════════════════════════════
# TERMINAL FORMATTING
# ══════════════════════════════════════════════════════════════════════════════

def divider(char="━", width=62):
    print(char * width)

def section(title):
    print(f"\n{'━'*62}")
    print(f"  {title}")
    print(f"{'━'*62}")

def print_parsed(parsed):
    section("📋 PARSED ERROR")
    print(f"  Framework : {parsed.framework.upper()}")
    print(f"  Timestamp : {parsed.timestamp}")
    print(f"  Level     : {parsed.level}")
    print(f"  Type      : {parsed.error_type}")
    print(f"  Message   : {parsed.error_message}")
    if parsed.stack_frames:
        top = parsed.top_frame()
        print(f"\n  Top Frame :")
        print(f"    File    : {top.file}")
        print(f"    Line    : {top.line}")
        print(f"    Func    : {top.function}")

def print_snippet(code: str, local_path: str):
    section("📄 REAL CODE FROM REPO")
    print(f"  Path : {local_path}\n")
    for line in code.splitlines():
        if line.strip().startswith(">>>"):
            print(f"  \033[93m{line}\033[0m")
        else:
            print(f"  {line}")

def print_fix(diff: str, root_cause: str, explanation: str, confidence: str):
    section("🤖 AI-GENERATED FIX  (Groq / Llama-3.3-70b)")
    print(f"\n  Root Cause  : {root_cause}")
    print(f"  Confidence  : {confidence}%")
    print(f"\n  Explanation : {explanation}")
    print(f"\n  Patch (unified diff):")
    print("  " + "─" * 54)
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            print(f"  \033[92m{line}\033[0m")
        elif line.startswith("-") and not line.startswith("---"):
            print(f"  \033[91m{line}\033[0m")
        else:
            print(f"  {line}")
    print("  " + "─" * 54)


# ══════════════════════════════════════════════════════════════════════════════
# GROQ API — LLM FIX GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def generate_fix(parsed, code_window: str, local_path: str) -> dict:
    """
    Ask LLM only for OLD_LINE and NEW_LINE.
    We apply the change ourselves and use git diff to produce a valid patch.
    """
    client = Groq(api_key="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")
    rel_path = os.path.relpath(local_path, REPO_ROOT)

    prompt = f"""You are a senior {parsed.framework} PHP developer.
A production 5xx error occurred. Analyse the code and identify the fix.

## Error
- Type    : {parsed.error_type}
- Message : {parsed.error_message}
- File    : {rel_path}

## Real code at error location (>>> marks the exact error line)
```php
{code_window}
```

Respond in EXACTLY this format, no extra text whatsoever:
ROOT_CAUSE: <one sentence>
CONFIDENCE: <number 0-100>
EXPLANATION: <one or two sentences>
OLD_LINE: <copy the single buggy line exactly as it appears in the code above, including all leading whitespace>
NEW_LINE: <the fixed version of that line, keeping the exact same leading whitespace>"""

    print("\n  Sending to Groq API (llama-3.3-70b)...")

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = response.choices[0].message.content

    root_cause  = _extract("ROOT_CAUSE",  raw)
    confidence  = _extract("CONFIDENCE",  raw)
    explanation = _extract("EXPLANATION", raw)
    old_line    = _extract("OLD_LINE",    raw)
    new_line    = _extract("NEW_LINE",    raw)

    return {
        "root_cause":  root_cause,
        "confidence":  confidence,
        "explanation": explanation,
        "old_line":    old_line,
        "new_line":    new_line,
    }


def _extract(key: str, text: str) -> str:
    match = re.search(rf"{key}:\s*(.+)", text)
    return match.group(1).strip() if match else "N/A"


def apply_fix_and_generate_patch(local_path: str, old_line: str, new_line: str) -> Optional[str]:
    """
    1. Read the real file
    2. Replace old_line with new_line using multiple strategies
    3. Use git diff --no-index to produce a guaranteed-valid patch
    """
    import tempfile

    with open(local_path, "r", errors="replace") as f:
        original = f.read()

    modified = None
    stripped_old = old_line.strip()
    stripped_new = new_line.strip()
    file_lines = original.splitlines(keepends=True)

    # Strategy 1: exact full string match
    if old_line in original:
        modified = original.replace(old_line, new_line, 1)

    # Strategy 2: stripped content match (preserves original indentation)
    if not modified:
        new_lines = []
        found = False
        for line in file_lines:
            if not found and line.strip() == stripped_old:
                indent = len(line) - len(line.lstrip())
                new_lines.append(" " * indent + stripped_new + "\n")
                found = True
            else:
                new_lines.append(line)
        if found:
            modified = "".join(new_lines)

    # Strategy 3: partial token match — find the line containing
    # the key broken token from old_line inside the file
    if not modified:
        # Extract the most unique token from old_line
        # e.g. "$requestData('filters')" from the collapsed LLM line
        token_match = re.search(r'(\$\w+\([^)]+\))', stripped_old)
        if token_match:
            broken_token = token_match.group(1)
            # Build fixed token — replace () with []
            fixed_token = re.sub(r'\(([^)]+)\)', r'[\1]', broken_token)
            new_lines = []
            found = False
            for line in file_lines:
                if not found and broken_token in line:
                    new_lines.append(line.replace(broken_token, fixed_token, 1))
                    found = True
                    print(f"  Token fix: {broken_token!r} → {fixed_token!r}")
                else:
                    new_lines.append(line)
            if found:
                modified = "".join(new_lines)

    if not modified:
        return None

    # Write modified to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".php", delete=False, dir="/tmp"
    ) as tmp:
        tmp.write(modified)
        tmp_path = tmp.name

    rel_path = os.path.relpath(local_path, REPO_ROOT)

    # git diff --no-index produces a real valid unified diff
    result = subprocess.run(
        ["git", "diff", "--no-index",
         "--src-prefix=a/", "--dst-prefix=b/",
         rel_path, tmp_path],  # ← rel_path not local_path
        capture_output=True, text=True,
        cwd=REPO_ROOT  # ← git runs from repo root so rel_path resolves correctly
    )

    os.unlink(tmp_path)

    patch = result.stdout
    # Fix the temp file path in the +++ header
    patch = patch.replace(
        f"b/{tmp_path.lstrip('/')}",
        f"b/{rel_path}"
    )
    return patch if patch.strip() else None


def save_patch(patch: str, error_message: str) -> str:
    os.makedirs("patches", exist_ok=True)
    short_hash = hashlib.md5(error_message.encode()).hexdigest()[:8]
    timestamp  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename   = f"patches/patch_{short_hash}_{timestamp}.patch"
    if not patch.endswith("\n"):
        patch += "\n"
    with open(filename, "w") as f:
        f.write(patch)
    return filename



# ══════════════════════════════════════════════════════════════════════════════
# MAIN DEMO FLOW
# ══════════════════════════════════════════════════════════════════════════════

def run_demo(raw_log: str):
    divider("═")
    print("  🚀 AutoFix Agent — Demo  |  Bizom")
    divider("═")

    # 1. Parse log
    section("📥 INPUT LOG")
    print(f"\n  {raw_log[:140]}")
    if len(raw_log) > 140:
        print("  ...")

    parsed = parse_laravel(raw_log) or parse_cakephp2(raw_log)
    if not parsed:
        print("\n  ❌ Could not parse log — unrecognised format.")
        sys.exit(1)

    print_parsed(parsed)

    # 2. Resolve file path
    top = best_frame(parsed)
    if not top:
        print("\n  ❌ No stack frame found in log.")
        sys.exit(1)

    section("🗺️  PATH RESOLUTION")
    print(f"\n  Server path : {top.file}")
    local_path = resolve_local_path(top.file)
    print(f"  Local path  : {local_path}")
    print(f"  Error line  : {top.line}")

    # 3. Fetch real code from git
    code_window, _ = fetch_code_window(local_path, top.line)
    if not code_window:
        print(f"\n  File not found locally: {local_path}")
        sys.exit(1)

    print_snippet(code_window, local_path)

    # 4. Generate fix via Groq (returns old_line + new_line)
    result = generate_fix(parsed, code_window, local_path)

    # 5. Apply fix to real file + generate patch via git diff
    patch = apply_fix_and_generate_patch(
        local_path=local_path,
        old_line=result["old_line"],
        new_line=result["new_line"],
    )

    if not patch:
        print(f"\n  Could not locate the buggy line in the file.")
        print(f"  OLD_LINE was: {result['old_line']}")
        sys.exit(1)

    # Show the fix to audience
    print_fix(
        diff=patch,
        root_cause=result["root_cause"],
        explanation=result["explanation"],
        confidence=result["confidence"],
    )

    # 6. Save the git-generated patch file
    patch_file = save_patch(patch, parsed.error_message)
    abs_patch  = os.path.abspath(patch_file)

    section("PATCH FILE SAVED")
    print(f"\n  File : {patch_file}")
    print(f"\n  Apply via terminal:")
    print(f"  cd {REPO_ROOT}")
    print(f"  git apply {abs_patch}")
    print(f"\n  Apply via PhpStorm:")
    print(f"  Git > Apply Patch > select {abs_patch}")

    divider("═")
    print("  ✅ Demo complete!")
    divider("═")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="AutoFix Agent Demo")
    ap.add_argument("--log",    help="Raw log line to process")
    ap.add_argument("--sample", choices=["laravel", "cakephp"],
                    help="Use a built-in Bizom-style sample log")
    args = ap.parse_args()

    if args.sample:
        raw_log = SAMPLE_LOGS[args.sample]
    elif args.log:
        raw_log = args.log
    else:
        print("\n  Paste your error log below (press Enter twice when done):")
        lines = []
        while True:
            line = input()
            if line == "" and lines:
                break
            lines.append(line)
        raw_log = "\n".join(lines)

    run_demo(raw_log)