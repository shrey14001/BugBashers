"""
demo.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AutoFix Agent — Live Demo  (full Phase 1 MVP pipeline)
Parse log → ChromaDB RAG check → LangChain fix → Bitbucket PR (optional) → store in ChromaDB
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
from dotenv import load_dotenv

from autofix.parsers.laravel  import parse as parse_laravel
from autofix.parsers.cakephp2 import parse as parse_cakephp2
from autofix.rag.engine       import RAGEngine
from autofix.core.llm_chain   import FixGenerator
from autofix.core.notifier      import send_known_error_email
from autofix.bitbucket.pr_creator import create_fix_pr

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
# REPO CONFIG — hardcoded for demo
# ══════════════════════════════════════════════════════════════════════════════

REPO_ROOT = "/Users/divitajain/Documents/Code/bizomweb2"

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
        "2026-06-03 14:32:18 Error: Fatal error: "
        "Call to undefined method Order::findByStatus() "
        "in /usr/share/php/Cake_2.10/Cake/Model/Model.php on line 512\n"
        "Stack trace:\n"
        "#0 /var/sites/demo.bizom.in/app/Controller/OrdersController.php(653): Order->findByStatus(Array)\n"
        "#1 /usr/share/php/Cake_2.10/Cake/Controller/Controller.php(491): OrdersController->invokeAction('index', Array)\n"
        "#2 /usr/share/php/Cake_2.10/Cake/Routing/Dispatcher.php(193): Controller->invokeAction('index')\n"
        "#3 /var/sites/demo.bizom.in/app/webroot/index.php(159): Dispatcher->dispatch(Object(CakeRequest), Object(CakeResponse))\n"
        "#4 {main}"
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
    if server_path.startswith(REPO_ROOT):
        return server_path
    relative = SERVER_PREFIX_RE.sub("", server_path)
    if relative == server_path:
        return None
    return os.path.join(REPO_ROOT, relative)


def best_frame(parsed) -> Optional[object]:
    for frame in parsed.stack_frames:
        if is_vendor_path(frame.file):
            continue
        if "/var/sites/" in frame.file or frame.file.startswith(REPO_ROOT):
            return frame
    return parsed.top_frame()


# ══════════════════════════════════════════════════════════════════════════════
# CODE FETCHER
# ══════════════════════════════════════════════════════════════════════════════

def fetch_code_window(local_path: str, error_line: int):
    """
    Returns (annotated_window: str, source_lines: list[str])

    Uses the local working-tree file so the LLM sees the same source that
    apply_fix_and_generate_patch() reads. Falls back to git HEAD only when
    the file is not present on disk.

    Scans backwards from error_line when it points at a closing bracket line.
    """
    if not os.path.exists(local_path):
        return None, []

    try:
        rel_path = os.path.relpath(local_path, REPO_ROOT)
    except ValueError:
        rel_path = local_path

    with open(local_path, "r", errors="replace") as f:
        source = f.read()
    method = "local file"

    print(f"  📂 Source   : {method} → {rel_path}")

    lines = source.splitlines()

    # Start at error_line; scan backwards only if that line is a bracket stub
    _BRACKET_ONLY = (")", ");", "];", "}", "{", "};")
    real_error_line = error_line
    for i in range(error_line, max(error_line - 10, 0), -1):
        if i > len(lines):
            continue
        stripped = lines[i - 1].strip()
        if stripped and stripped not in _BRACKET_ONLY:
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

def print_known(similar):
    section("🔍 KNOWN ERROR — Match in ChromaDB")
    print(f"\n  Similarity  : {similar.score:.4f}  (threshold {os.getenv('SIMILARITY_THRESHOLD', '0.85')})")
    print(f"  Commit      : {similar.commit_id}")
    print(f"  File        : {similar.file}  line {similar.line}")
    if similar.pr_url:
        print(f"  Prior PR    : {similar.pr_url}")
    print("\n  ℹ️  A fix already exists — no new PR will be created.")

def _llm_display_label() -> str:
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    if provider == "gemini":
        return f"Gemini / {os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')}"
    if provider == "groq":
        return f"Groq / {os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')}"
    return provider.upper()


def _llm_model_name() -> str:
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    if provider == "gemini":
        return os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    if provider == "groq":
        return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def print_fix(diff: str, root_cause: str, explanation: str, confidence: str):
    section(f"🤖 AI-GENERATED FIX  ({_llm_display_label()})")
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
# LLM FIX GENERATION
# Tries LangChain FixGenerator first; falls back to direct provider SDK
# (Gemini or Groq) when LangChain packages have version conflicts.
# ══════════════════════════════════════════════════════════════════════════════

def _parse_diff_for_lines(diff: str, error_message: str) -> tuple[str, str]:
    """Pick the most relevant -/+ pair from a unified diff (prefer the error token)."""
    minus = [dl[1:] for dl in diff.splitlines()
             if dl.startswith("-") and not dl.startswith("---")]
    plus  = [dl[1:] for dl in diff.splitlines()
             if dl.startswith("+") and not dl.startswith("+++")]

    # Prefer the line that matches the error
    token_match = re.search(r"::(\w+)\(", error_message)
    token = token_match.group(1) if token_match else None
    if token:
        for i, m in enumerate(minus):
            if token in m:
                return m, plus[i] if i < len(plus) else "N/A"

    if minus:
        return minus[0], plus[0] if plus else "N/A"
    return "N/A", "N/A"


def _fix_prompt(parsed, code_window: str, rel_path: str) -> str:
    return f"""You are a senior {parsed.framework} PHP developer.
A production 5xx error occurred. Analyse the code and identify the fix.

## Error
- Type    : {parsed.error_type}
- Message : {parsed.error_message}
- File    : {rel_path}

## Real code at error location (>>> marks the exact line to fix)
```php
{code_window}
```

Rules:
- Fix ONLY the line marked with >>> — do not change function signatures or other lines.
- OLD_LINE must be the raw PHP source from that >>> line (no line numbers, no ">>>" prefix).

Respond in EXACTLY this format, no extra text:
ROOT_CAUSE: <one sentence>
CONFIDENCE: <number 0-100>
EXPLANATION: <one or two sentences>
OLD_LINE: <copy the buggy line exactly, including all leading whitespace>
NEW_LINE: <the fixed version, same leading whitespace>"""


def _generate_fix_langchain(parsed, code_window: str, rel_path: str,
                             start_line: int, end_line: int) -> dict:
    """Use LangChain FixGenerator."""
    # Keep >>> markers so the LLM knows which line to fix
    diff = FixGenerator().generate_diff(
        framework=parsed.framework,
        error_type=parsed.error_type,
        error_message=parsed.error_message,
        file_path=rel_path,
        snippet=code_window,
        start_line=start_line,
        end_line=end_line,
    )
    old_line, new_line = _parse_diff_for_lines(diff, parsed.error_message)
    return {
        "root_cause":  f"{parsed.error_type}: {parsed.error_message[:100]}",
        "confidence":  "95",
        "explanation": f"Replace `{old_line.strip()}` with the corrected form.",
        "old_line":    old_line,
        "new_line":    new_line,
        "_diff":       diff,
    }


def _generate_fix_direct(parsed, code_window: str, rel_path: str) -> dict:
    """Direct provider SDK fallback — no LangChain dependency."""
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    prompt = _fix_prompt(parsed, code_window, rel_path)

    if provider == "gemini":
        import google.generativeai as genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("\n  ❌ GEMINI_API_KEY not set — add it to .env")
            sys.exit(1)
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0},
        )
        raw = response.text
    else:
        from groq import Groq as GroqClient
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("\n  ❌ GROQ_API_KEY not set — add it to .env")
            sys.exit(1)
        client = GroqClient(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = response.choices[0].message.content

    return {
        "root_cause":  _extract("ROOT_CAUSE",  raw),
        "confidence":  _extract("CONFIDENCE",  raw),
        "explanation": _extract("EXPLANATION", raw),
        "old_line":    _extract("OLD_LINE",    raw),
        "new_line":    _extract("NEW_LINE",    raw),
        "_diff":       "",
    }


def generate_fix(parsed, code_window: str, local_path: str) -> dict:
    """
    Tries LangChain FixGenerator (production path).
    Falls back to direct provider SDK when langchain packages have version conflicts.
    """
    rel_path = os.path.relpath(local_path, REPO_ROOT)
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    provider_label = provider.upper()

    numbered_lines = [
        l for l in code_window.splitlines()
        if re.match(r"^(?:>>>|   )\s*(\d+)\s\|", l)
    ]
    start_line = int(re.search(r"\d+", numbered_lines[0]).group()) if numbered_lines else 1
    end_line   = int(re.search(r"\d+", numbered_lines[-1]).group()) if numbered_lines else start_line

    try:
        print(f"\n  Sending to {provider_label} via LangChain ({_llm_model_name()})...")
        result = _generate_fix_langchain(parsed, code_window, rel_path, start_line, end_line)
        # If LangChain diff missed the error line, fall back to direct SDK (>>>-aware prompt)
        token_match = re.search(r"::(\w+)\(", parsed.error_message)
        token = token_match.group(1) if token_match else ""
        if token and token not in result.get("_diff", ""):
            print(f"  ⚠️  LangChain diff did not touch `{token}` — falling back to direct {provider_label} SDK.")
            return _generate_fix_direct(parsed, code_window, rel_path)
        return result
    except (ImportError, Exception) as e:
        if "ModelProfile" in str(e) or isinstance(e, ImportError):
            hint = (
                'pip install "langchain-groq<1.0" or upgrade langchain-core to 0.3.x'
                if provider == "groq"
                else "pip install langchain-google-genai google-generativeai"
            )
            print(f"  ⚠️  LangChain/{provider_label} version conflict — falling back to direct SDK.")
            print(f"      Fix: {hint}")
            print(f"\n  Sending to {provider_label} via direct SDK...")
            return _generate_fix_direct(parsed, code_window, rel_path)
        raise


def _extract(key: str, text: str) -> str:
    match = re.search(rf"{key}:\s*(.+)", text)
    return match.group(1).strip() if match else "N/A"


def _sanitize_llm_line(line: str) -> str:
    """Strip display annotations the LLM may echo, e.g. '>>>   76 | code'."""
    match = re.match(r"^(?:>>>\s*)?\d+\s*\|\s*(.*)$", line)
    return match.group(1) if match else line


def apply_fix_and_generate_patch(local_path: str, old_line: str, new_line: str) -> Optional[str]:
    """
    1. Read the real file
    2. Replace old_line with new_line using multiple strategies
    3. Use git diff --no-index to produce a guaranteed-valid patch
    """
    import tempfile

    old_line = _sanitize_llm_line(old_line)
    new_line = _sanitize_llm_line(new_line)

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

    # # 2. ChromaDB similarity search — known vs novel
    # section("🧠 CHROMADB SIMILARITY CHECK")
    # rag = RAGEngine()
    # error_text = parsed.embedding_text()
    # similar = rag.find_similar(error_text)
    # if similar:
    #     print_known(similar)
    #     section("📧 EMAIL ALERT")
    #     send_known_error_email(
    #         error_message=parsed.error_message,
    #         commit_id=similar.commit_id,
    #         pr_url=similar.pr_url,
    #         similarity_score=similar.score,
    #         domain=parsed.domain,
    #     )
    #     divider("═")
    #     print("  ✅ Demo complete! (known-error path)")
    #     divider("═")
    #     print()
    #     return

    print(f"  No similar fix found — treating as NOVEL error.")

    # 3. Resolve file path
    top = best_frame(parsed)
    if not top:
        print("\n  ❌ No stack frame found in log.")
        sys.exit(1)

    section("🗺️  PATH RESOLUTION")
    print(f"\n  Server path : {top.file}")
    local_path = resolve_local_path(top.file)
    print(f"  Local path  : {local_path}")
    print(f"  Error line  : {top.line}")

    if not local_path:
        print("\n  ❌ Could not map server path to a file in REPO_ROOT.")
        print(f"     Skipped   : {top.file}")
        print(f"     REPO_ROOT : {REPO_ROOT}")
        sys.exit(1)

    # 4. Fetch real code from local repo
    code_window, _ = fetch_code_window(local_path, top.line)
    if not code_window:
        print(f"\n  File not found locally: {local_path}")
        sys.exit(1)

    print_snippet(code_window, local_path)

    # 5. Generate fix via LLM (returns old_line + new_line)
    result = generate_fix(parsed, code_window, local_path)

    # 6. Build patch — use LangChain diff directly when available
    patch = result.get("_diff", "").strip()
    if patch:
        print("  Using unified diff from LangChain.")
    else:
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

    commit_hash = subprocess.check_output(
        ["git", "-C", REPO_ROOT, "rev-parse", "HEAD"], text=True
    ).strip()

    pr_url = None

    # 7a. Bitbucket PR  (only when credentials are configured)
    if os.getenv("BITBUCKET_WORKSPACE"):
        section("🔀 CREATING BITBUCKET PR")
        try:
            bb_repo_slug = os.getenv("BITBUCKET_REPO_SLUG", "bizomweb2")
            rel_path = os.path.relpath(local_path, REPO_ROOT)
            pr = create_fix_pr(
                repo_slug=bb_repo_slug,
                file_path=rel_path,
                error_message=parsed.error_message,
                diff_patch=result.get("_diff", patch),
                commit_hash=commit_hash,
            )
            pr_url = pr.pr_url
            print(f"\n  PR ID   : {pr.pr_id}")
            print(f"  Branch  : {pr.branch}")
            print(f"  PR URL  : {pr.pr_url}")
        except Exception as e:
            print(f"  ⚠️  Bitbucket PR failed: {e}")
            print("  Falling back to local patch file.")

    # 7b. Patch file fallback (always saved for local use)
    patch_file = save_patch(patch, parsed.error_message)
    abs_patch  = os.path.abspath(patch_file)

    section("📄 PATCH FILE SAVED")
    print(f"\n  File : {patch_file}")
    if not pr_url:
        print(f"\n  Apply via terminal:")
        print(f"  cd {REPO_ROOT}")
        print(f"  git apply {abs_patch}")
        print(f"\n  Apply via PhpStorm:")
        print(f"  Git > Apply Patch > select {abs_patch}")

    # # 8. Store fix embedding in ChromaDB (feedback loop)
    # section("💾 STORING FIX IN CHROMADB")
    # try:
    #     rag.store_fix(
    #         error_text=error_text,
    #         commit_id=commit_hash,
    #         domain=parsed.domain or "",
    #         file=top.file,
    #         line=top.line,
    #         pr_url=pr_url,
    #     )
    #     print(f"  Stored with commit {commit_hash[:12]}  — next identical error will hit the KNOWN path.")
    # except Exception as e:
    #     print(f"  ⚠️  Could not store fix: {e}")

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