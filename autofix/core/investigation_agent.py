"""
core/investigation_agent.py

Agentic investigation loop — uses Gemini function calling to read files
and search code before generating a fix diff.

Flow:
  1. LLM receives error + initial code snippet
  2. LLM calls read_file / search_code tools as needed
  3. LLM calls generate_fix when it has enough context
  4. Falls back to direct FixGenerator if function calling unavailable
"""

import os
import subprocess
from dotenv import load_dotenv

load_dotenv()

MAX_STEPS      = int(os.getenv("AUTOFIX_MAX_INVESTIGATION_STEPS", "6"))
MAX_FILE_LINES = int(os.getenv("AUTOFIX_MAX_FILE_LINES", "1000"))

_TOOL_DECLARATIONS = [
    {
        "name": "read_file",
        "description": (
            "Read a PHP source file from the repository. "
            "Use this to inspect model definitions, parent classes, traits, "
            "or any file not already in the call chain. "
            f"Files longer than {MAX_FILE_LINES} lines are truncated — use "
            "start_line/end_line to read a specific section (e.g. a method you "
            "found via search_code)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": (
                        "Repo-relative path, e.g. app/Models/ActivityPicture.php "
                        "or app/Http/Traits/LaravelFindORMTrait.php"
                    ),
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to read (1-based). Omit to start from the top.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to read (1-based, inclusive). Omit to read to end (subject to truncation).",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "search_code",
        "description": (
            "Grep the codebase for a pattern. "
            "Use this to find class definitions, method usages, or constant values."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "String or regex to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Optional subdirectory or file to restrict search",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "generate_fix",
        "description": (
            "Call this when you have identified the root cause. "
            "Provide a minimal unified diff and a one-sentence explanation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "diff": {
                    "type": "string",
                    "description": "Unified diff (--- / +++ / @@ format)",
                },
                "explanation": {
                    "type": "string",
                    "description": "One sentence: what is the root cause and what the fix does",
                },
            },
            "required": ["diff", "explanation"],
        },
    },
]


class InvestigationAgent:
    """
    Gemini-powered agent that investigates a production error before fixing it.
    Falls back to direct FixGenerator for non-Gemini providers.
    """

    def __init__(
        self,
        repo_slug: str,
        commit_hash: str,
        repo_root: str = "",
        laravel_path_prefix: str = "app/laravel",
    ):
        self.repo_slug           = repo_slug
        self.commit_hash         = commit_hash
        self.repo_root           = repo_root
        self.laravel_path_prefix = laravel_path_prefix.strip("/")

    # ── Public entry point ────────────────────────────────────────────────────

    def run(
        self,
        framework: str,
        error_type: str,
        error_message: str,
        file_path: str,
        snippet: str,
        app_frames: list | None = None,
    ) -> str:
        """
        Investigate the error and return a unified diff.
        Falls back to FixGenerator.generate_diff_with_fallback on any failure.
        """
        provider = os.getenv("LLM_PROVIDER", "gemini").lower()

        if provider == "claude_code":
            try:
                return self._run_claude_code(
                    framework, error_type, error_message, file_path, snippet,
                    app_frames=app_frames or [],
                )
            except Exception as e:
                print(
                    f"[Agent] Claude Code investigation failed ({e}) — "
                    "falling back to Gemini direct.",
                    flush=True,
                )
                # Claude Code failed — fall through to Gemini direct below

        if provider in ("gemini", "claude_code"):
            try:
                return self._run_gemini(
                    framework, error_type, error_message, file_path, snippet,
                    app_frames=app_frames or [],
                )
            except Exception as e:
                print(
                    f"[Agent] Gemini investigation failed ({e}) — "
                    "falling back to direct fix generation.",
                    flush=True,
                )

        from autofix.core.llm_chain import FixGenerator
        return FixGenerator().generate_diff_with_fallback(
            framework=framework,
            error_type=error_type,
            error_message=error_message,
            file_path=file_path,
            snippet=snippet,
            start_line=0,
            end_line=0,
        )

    # ── Claude Code CLI runner ────────────────────────────────────────────────

    def _run_claude_code(
        self,
        framework: str,
        error_type: str,
        error_message: str,
        file_path: str,
        snippet: str,
        app_frames: list | None = None,
    ) -> str:
        import shutil
        import re as _re

        if not shutil.which("claude"):
            raise RuntimeError("'claude' CLI not found in PATH — install Claude Code first")

        repo_root = os.getenv("CLAUDE_CODE_REPO_ROOT", self.repo_root)
        if not repo_root or not os.path.isdir(repo_root):
            raise RuntimeError(
                f"CLAUDE_CODE_REPO_ROOT is not set or not a valid directory: {repo_root!r}"
            )

        prompt = self._claude_code_prompt(
            framework, error_type, error_message, file_path, snippet,
            app_frames=app_frames or [],
        )

        timeout = int(os.getenv("CLAUDE_CODE_TIMEOUT", "300"))
        max_turns = int(os.getenv("CLAUDE_CODE_MAX_TURNS", "15"))
        cmd = [
            "claude", "-p", prompt,
            "--dangerously-skip-permissions",
            "--max-turns", str(max_turns),
            "--output-format", "text",
        ]
        print(f"[Agent] Claude Code: cwd={repo_root}  max-turns={max_turns}  timeout={timeout}s", flush=True)

        # Build a clean env: inherit everything EXCEPT keys that dotenv may have
        # set to placeholders (sk-ant-...) which would override Claude Code's own
        # stored credentials in ~/.claude/.
        env = os.environ.copy()
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"):
            env.pop(key, None)

        result = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        if stderr.strip():
            print(f"[Agent] Claude Code stderr: {stderr[:600]}", flush=True)

        if result.returncode not in (0, 1):
            raise RuntimeError(
                f"claude CLI exited {result.returncode}.\n"
                f"stderr: {stderr[:400]}\nstdout: {stdout[:200]}"
            )

        if not stdout.strip():
            raise RuntimeError(
                f"Claude Code produced no output (rc={result.returncode}).\n"
                f"stderr: {stderr[:600]}"
            )

        # Prefer explicit <diff>…</diff> tags so explanatory text is ignored
        m = _re.search(r"<diff>(.*?)</diff>", stdout, _re.DOTALL)
        if m:
            diff = m.group(1).strip()
            if diff:
                print("[Agent] Claude Code diff extracted from <diff> tags.", flush=True)
                return diff

        from autofix.core.llm_chain import _extract_diff
        diff = _extract_diff(stdout)
        if diff:
            print("[Agent] Claude Code diff extracted from fenced block.", flush=True)
            return diff

        raise ValueError(
            f"Claude Code returned no recognisable diff.\n"
            f"stdout (first 800):\n{stdout[:800]}\n"
            f"stderr (first 400):\n{stderr[:400]}"
        )

    def _claude_code_prompt(
        self,
        framework: str,
        error_type: str,
        error_message: str,
        file_path: str,
        snippet: str,
        app_frames: list | None = None,
    ) -> str:
        chain_lines = []
        if app_frames:
            for i, f in enumerate(app_frames):
                tag = "  ← error fires here" if i == 0 else ""
                fname = getattr(f, "function", "") or ""
                chain_lines.append(f"  #{i}  {f.file}:{f.line}  {fname}{tag}")
        chain_section = (
            "\n## Call chain (outermost → deepest caller)\n"
            + "\n".join(chain_lines) + "\n"
        ) if chain_lines else ""

        base_warning = (
            "\nNOTE: The error fires inside a shared base trait/abstract. "
            "Do NOT modify that file. Trace the callers to find who passes wrong data.\n"
        ) if self._is_base_file(file_path) else ""

        return (
            f"You are fixing a production {framework} bug in this codebase.\n"
            f"DO NOT modify any files. Read relevant source files, trace the root cause,\n"
            f"then output a unified diff.\n\n"
            f"## Error\n"
            f"- Type    : {error_type}\n"
            f"- Message : {error_message}\n"
            f"- File    : {file_path}\n"
            f"{chain_section}"
            f"{base_warning}\n"
            f"## Snippet at error site (>>> = error line)\n"
            f"```php\n{snippet}\n```\n\n"
            f"## Investigation rules — follow these strictly\n\n"
            f"### SQL / column-not-found errors\n"
            f"- The column name in the error is the clue. Find where the ORM condition\n"
            f"  or eager-load key is built — it will contain that exact string.\n"
            f"- Check for case mismatches: `class_basename(Model)` returns the class name\n"
            f"  with its exact capitalisation. If the conditions array uses a different\n"
            f"  capitalisation, that is the bug — fix the key in the conditions array.\n"
            f"- Do NOT touch the base ORM trait/query builder.\n\n"
            f"### Undefined index / missing array key errors\n"
            f"- Do NOT use `?? ''` or null-coalescing as the fix unless you can confirm\n"
            f"  the key is genuinely optional by design.\n"
            f"- Instead: trace back to the query or data source that fills the array.\n"
            f"  If the key should be there, fix the query (missing SELECT column,\n"
            f"  missing JOIN, or a typo in the column/key name).\n"
            f"- Check for typos: e.g. `desingation_name` vs `designation_name`.\n\n"
            f"### Call to member function on null\n"
            f"- Do NOT add null guards as the only fix.\n"
            f"- Find why the object is null — missing eager-load, wrong scope, or\n"
            f"  a query that returns null when it should not.\n\n"
            f"## Output\n"
            f"Output ONLY the block below — no explanation, no other text:\n\n"
            f"<diff>\n"
            f"--- a/path/to/file.php\n"
            f"+++ b/path/to/file.php\n"
            f"@@ -N,M +N,M @@\n"
            f" context\n"
            f"-old line\n"
            f"+fixed line\n"
            f" context\n"
            f"</diff>"
        )

    # ── Gemini function-calling loop ──────────────────────────────────────────

    @staticmethod
    def _is_base_file(file_path: str) -> bool:
        """Return True if the file is a shared base that should never be modified."""
        low = file_path.lower()
        return any(seg in low for seg in (
            "/traits/", "trait.php", "/abstract", "abstract.php",
            "/base/", "basecontroller", "basemodel", "/helpers/",
        ))

    def _initial_prompt(
        self,
        framework: str,
        error_type: str,
        error_message: str,
        file_path: str,
        snippet: str,
        app_frames: list | None = None,
    ) -> str:
        chain_section = ""
        if app_frames:
            lines = []
            for i, f in enumerate(app_frames):
                tag = "  (error here)" if i == 0 else ""
                fname = getattr(f, "function", "") or ""
                lines.append(f"  #{i}  {f.file}:{f.line}  {fname}{tag}")
            chain_section = (
                "\n## Call Chain (outermost → deepest caller)\n"
                + "\n".join(lines)
                + "\n"
            )

        base_warning = ""
        if self._is_base_file(file_path):
            base_warning = (
                "\n## IMPORTANT\n"
                "The error fires inside a shared base trait/abstract class. "
                "**Do NOT modify that file.** "
                "The bug is almost certainly in a CALLER that passes wrong data. "
                "Use read_file on the callers listed in the call chain above "
                "to find where the incorrect value originates, then fix only that caller.\n"
            )

        return (
            f"You are a senior {framework} developer debugging a production error.\n\n"
            f"## Error\n"
            f"- Type    : {error_type}\n"
            f"- Message : {error_message}\n"
            f"- File    : {file_path}\n"
            f"{chain_section}"
            f"{base_warning}\n"
            f"## Code Snippet at error site (>>> = error line)\n"
            f"```php\n{snippet}\n```\n\n"
            f"Use the available tools to trace the root cause:\n"
            f"1. Read the error file to understand what it expects from callers.\n"
            f"2. Read each caller in the call chain — find who passes the wrong value.\n"
            f"3. Once you identify the caller with the bug, call generate_fix "
            f"targeting THAT file, not the base trait.\n"
            f"Fix only the specific line(s) causing the error."
        )

    def _run_gemini(
        self,
        framework: str,
        error_type: str,
        error_message: str,
        file_path: str,
        snippet: str,
        app_frames: list | None = None,
    ) -> str:
        from google import genai as google_genai
        from google.genai import types

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")

        model      = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        timeout_ms = int(os.getenv("LLM_TIMEOUT_SECONDS", "120")) * 1000
        client     = google_genai.Client(
            api_key=api_key,
            http_options={"timeout": timeout_ms},
        )

        tools = [types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=t["parameters"],
            )
            for t in _TOOL_DECLARATIONS
        ])]
        config = types.GenerateContentConfig(tools=tools, temperature=0)

        contents = [
            types.Content(
                role="user",
                parts=[types.Part(text=self._initial_prompt(
                    framework, error_type, error_message, file_path, snippet,
                    app_frames=app_frames or [],
                ))],
            )
        ]

        for step in range(MAX_STEPS + 1):
            print(f"[Agent] Step {step + 1}/{MAX_STEPS}", flush=True)

            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

            candidate = response.candidates[0]
            if not candidate.content or not candidate.content.parts:
                raise ValueError(
                    "Gemini returned empty content (likely context-length overflow). "
                    "Try increasing AUTOFIX_MAX_FILE_LINES or reducing call chain depth."
                )
            function_calls = [
                p.function_call
                for p in candidate.content.parts
                if getattr(p, "function_call", None)
            ]

            if not function_calls:
                # Model responded with text — extract diff directly
                text = getattr(response, "text", "") or ""
                print("[Agent] No tool calls — extracting diff from text.", flush=True)
                from autofix.core.llm_chain import _extract_diff
                diff = _extract_diff(text)
                if diff:
                    return diff
                raise ValueError(f"Agent returned no valid diff.\nRaw:\n{text[:500]}")

            # Execute each tool call and collect responses
            tool_response_parts = []
            for fc in function_calls:
                name = fc.name
                args = dict(fc.args) if fc.args else {}
                result = self._dispatch(name, args)
                tool_response_parts.append(
                    types.Part.from_function_response(
                        name=name,
                        response={"result": result},
                    )
                )
                if name == "generate_fix":
                    diff = args.get("diff", "")
                    expl = args.get("explanation", "")
                    print(f"[Agent] generate_fix — {expl}", flush=True)
                    if diff:
                        return diff

            # Append model turn + tool results to conversation
            contents.append(candidate.content)
            contents.append(
                types.Content(role="user", parts=tool_response_parts)
            )

        # Max steps hit — force one last generation without tools
        print("[Agent] Max steps reached — forcing final generation.", flush=True)
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=(
                "You have used all investigation steps. "
                "Now call generate_fix with your best unified diff based on everything you found."
            ))],
        ))
        final = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(tools=tools, temperature=0),
        )
        for p in final.candidates[0].content.parts:
            fc = getattr(p, "function_call", None)
            if fc and fc.name == "generate_fix":
                diff = dict(fc.args or {}).get("diff", "")
                if diff:
                    return diff

        from autofix.core.llm_chain import _extract_diff
        diff = _extract_diff(getattr(final, "text", "") or "")
        if diff:
            return diff
        raise ValueError("Investigation agent could not produce a valid diff after max steps")

    # ── Tool dispatcher ───────────────────────────────────────────────────────

    def _dispatch(self, name: str, args: dict) -> str:
        if name == "read_file":
            return self._read_file(
                args.get("file_path", ""),
                start_line=int(args.get("start_line") or 0),
                end_line=int(args.get("end_line") or 0),
            )
        if name == "search_code":
            return self._search_code(args.get("pattern", ""), args.get("path", ""))
        if name == "generate_fix":
            return "OK"
        return f"Unknown tool: {name}"

    # ── Tool implementations ──────────────────────────────────────────────────

    def _read_file(self, file_path: str, start_line: int = 0, end_line: int = 0) -> str:
        file_path = file_path.strip().lstrip("/")
        range_tag = f" [{start_line}–{end_line}]" if start_line or end_line else ""
        print(f"[Agent] read_file: {file_path}{range_tag}", flush=True)

        # Candidate paths to try in order
        candidates = [file_path]
        if self.laravel_path_prefix and not file_path.startswith(self.laravel_path_prefix):
            candidates.append(f"{self.laravel_path_prefix}/{file_path}")

        content = None
        source_tag = ""

        # 1. Local repo
        if self.repo_root:
            for candidate in candidates:
                local = os.path.join(self.repo_root, candidate)
                if os.path.exists(local):
                    with open(local, "r", errors="replace") as f:
                        content = f.read()
                    source_tag = "local"
                    break

        # 2. Bitbucket API
        if content is None:
            try:
                from autofix.core.code_retriever import fetch_file_at_commit
                for candidate in candidates:
                    try:
                        content = fetch_file_at_commit(
                            self.repo_slug, candidate, self.commit_hash
                        )
                        source_tag = "Bitbucket"
                        break
                    except FileNotFoundError:
                        continue
            except Exception:
                pass

        if content is None:
            return f"ERROR: file not found — {file_path}"

        all_lines = content.splitlines()
        total = len(all_lines)

        # Apply requested line range
        if start_line > 0 or end_line > 0:
            s = max(0, (start_line or 1) - 1)
            e = (end_line or total)
            lines  = all_lines[s:e]
            offset = s
        else:
            lines  = all_lines
            offset = 0

        # Truncate if still too large
        truncation_note = ""
        if len(lines) > MAX_FILE_LINES:
            lines = lines[:MAX_FILE_LINES]
            shown_end = offset + MAX_FILE_LINES
            truncation_note = (
                f"\n\n... TRUNCATED at line {shown_end} (file has {total} lines total). "
                f"Use search_code to find the relevant function/method name, "
                f"then call read_file again with start_line/end_line to read that section."
            )

        numbered = "\n".join(
            f"{offset + i + 1:4d} | {line}"
            for i, line in enumerate(lines)
        )
        print(f"[Agent] read_file: {len(lines)}/{total} lines ({source_tag})", flush=True)
        return numbered + truncation_note

    def _search_code(self, pattern: str, path: str = "") -> str:
        print(f"[Agent] search_code: '{pattern}' in '{path or 'repo'}'", flush=True)

        if not self.repo_root:
            return "ERROR: search_code requires REPO_ROOT to be set in .env"

        search_in = os.path.join(self.repo_root, path.lstrip("/")) if path else self.repo_root
        if not os.path.exists(search_in):
            return f"ERROR: path does not exist — {search_in}"

        try:
            result = subprocess.run(
                ["grep", "-r", "-n", "--include=*.php", pattern, search_in],
                capture_output=True,
                text=True,
                timeout=15,
            )
            output = result.stdout.strip()
            if not output:
                return "No matches found."

            lines = output.splitlines()
            # Strip the repo_root prefix to keep paths readable
            cleaned = [
                line.replace(self.repo_root.rstrip("/") + "/", "", 1)
                for line in lines
            ]
            if len(cleaned) > 40:
                cleaned = cleaned[:40] + [f"... ({len(lines) - 40} more lines truncated)"]

            print(f"[Agent] search_code: {len(lines)} matches", flush=True)
            return "\n".join(cleaned)
        except subprocess.TimeoutExpired:
            return "ERROR: search timed out"
        except Exception as e:
            return f"ERROR: search failed — {e}"
