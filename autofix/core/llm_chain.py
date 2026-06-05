"""
core/llm_chain.py
LangChain prompt template + LLMChain for generating unified diff patches.

Supports:
  - Groq  (llama-3.3-70b-versatile)   LLM_PROVIDER=groq      + GROQ_API_KEY
  - Gemini (gemini-2.0-flash)        LLM_PROVIDER=gemini    + GEMINI_API_KEY
  - OpenAI GPT-4o                      LLM_PROVIDER=openai    + OPENAI_API_KEY
  - Anthropic Claude                   LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY
  - Local CodeLlama via Ollama         LLM_PROVIDER=codellama
"""

import os
import re
from dotenv import load_dotenv

load_dotenv()

from langchain_core.prompts import PromptTemplate


# ── LLM factory ──────────────────────────────────────────────────────────────

def _build_llm():
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=0,
            groq_api_key=os.getenv("GROQ_API_KEY"),
        )

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            temperature=0,
            google_api_key=os.getenv("GEMINI_API_KEY"),
            timeout=timeout,
        )

    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model="claude-sonnet-4-20250514",
            temperature=0,
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        )

    elif provider == "codellama":
        # Requires Ollama running locally: `ollama pull codellama`
        from langchain_community.llms import Ollama
        return Ollama(model="codellama:13b", temperature=0)

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


# ── Prompt template ───────────────────────────────────────────────────────────

_TEMPLATE = """\
You are a senior {framework} developer reviewing a production 5xx error.
Your task is to produce a minimal unified diff that fixes the issue.

## Error Details
- Type    : {error_type}
- Message : {error_message}
- File    : {file_path}
- Lines   : {start_line} – {end_line}

## Code Snippet (line numbers shown)
```php
{snippet}
```

## Instructions
1. Output ONLY a valid unified diff (--- / +++ / @@ format).
2. Do NOT include explanations outside the diff block.
3. Keep changes minimal — fix only the root cause.
4. If the fix requires importing a class or adding a use statement, include it.
5.Note dont change Base functions immediately.

Diff:
"""

_PROMPT = PromptTemplate(
    input_variables=[
        "framework",
        "error_type",
        "error_message",
        "file_path",
        "start_line",
        "end_line",
        "snippet",
    ],
    template=_TEMPLATE,
)


# ── Diff extractor ────────────────────────────────────────────────────────────

def _extract_diff(raw_output: str) -> str:
    """
    Pull the unified diff block out of the LLM response.
    Handles both fenced (```diff ... ```) and raw output.
    """
    # Try fenced block first
    fenced = re.search(r"```(?:diff)?\n(.*?)```", raw_output, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()

    # Fall back to lines starting with ---, +++, @@, +, -
    diff_lines = [
        line for line in raw_output.splitlines()
        if line.startswith(("---", "+++", "@@", "+", "-", " "))
    ]
    return "\n".join(diff_lines).strip()


# ── Public API ────────────────────────────────────────────────────────────────

class FixGenerator:
    def __init__(self):
        self._llm = None      # built lazily on first use
        self._chain = None

    def _get_chain(self):
        if self._chain is None:
            self._llm   = _build_llm()
            self._chain = _PROMPT | self._llm
        return self._chain

    def generate_diff(
        self,
        framework: str,
        error_type: str,
        error_message: str,
        file_path: str,
        snippet: str,
        start_line: int,
        end_line: int,
    ) -> str:
        """
        Call the LLM chain and return a cleaned unified diff string.
        Raises ValueError if no valid diff is found in the output.
        """
        response = self._get_chain().invoke({
            "framework":     framework,
            "error_type":    error_type,
            "error_message": error_message,
            "file_path":     file_path,
            "snippet":       snippet,
            "start_line":    start_line,
            "end_line":      end_line,
        })
        raw = response.content if hasattr(response, "content") else str(response)

        diff = _extract_diff(raw)
        if not diff:
            raise ValueError(f"LLM returned no valid diff.\nRaw output:\n{raw}")

        return diff

    def generate_diff_with_fallback(
        self,
        framework: str,
        error_type: str,
        error_message: str,
        file_path: str,
        snippet: str,
        start_line: int,
        end_line: int,
    ) -> str:
        """
        Generate a unified diff. Gemini uses the direct SDK first (faster, no
        LangChain deprecation noise). Groq/OpenAI try LangChain then direct SDK.
        """
        provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        model    = os.getenv("GEMINI_MODEL" if provider == "gemini" else "GROQ_MODEL", "")

        # Gemini: direct SDK first — avoids long silent LangChain hangs in tests/CI
        if provider == "gemini":
            print(f"[LLM] Calling Gemini direct SDK ({model or 'gemini-2.0-flash'})…", flush=True)
            try:
                return _generate_diff_direct(
                    provider=provider, framework=framework,
                    error_type=error_type, error_message=error_message,
                    file_path=file_path, snippet=snippet,
                )
            except Exception as e:
                print(f"[LLM] Direct SDK failed ({e}) — trying LangChain…", flush=True)

        print(f"[LLM] Calling LangChain ({provider})…", flush=True)
        timeout_secs = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
        import concurrent.futures
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(
                    self.generate_diff,
                    framework=framework, error_type=error_type,
                    error_message=error_message, file_path=file_path,
                    snippet=snippet, start_line=start_line, end_line=end_line,
                )
                diff = future.result(timeout=timeout_secs)
            if diff:
                print("[LLM] Diff received from LangChain.", flush=True)
                return diff
        except concurrent.futures.TimeoutError:
            print(f"[LLM] LangChain timed out after {timeout_secs}s — aborting.", flush=True)
            raise RuntimeError(f"LLM timed out after {timeout_secs}s. Use a faster model or raise LLM_TIMEOUT_SECONDS in .env.")
        except (ImportError, Exception) as e:
            if "ModelProfile" not in str(e) and not isinstance(e, ImportError):
                raise
            print(f"[LLM] LangChain/{provider} conflict — using direct SDK.", flush=True)
            return _generate_diff_direct(
                provider=provider, framework=framework,
                error_type=error_type, error_message=error_message,
                file_path=file_path, snippet=snippet,
            )


def _build_direct_prompt(framework: str, error_type: str, error_message: str,
                          file_path: str, snippet: str) -> str:
    return f"""You are a senior {framework} developer reviewing a production 5xx error.
Produce a minimal unified diff (--- / +++ / @@ format) that fixes the issue.

## Error
- Type    : {error_type}
- Message : {error_message}
- File    : {file_path}

## Code (>>> marks the exact error line)
```php
{snippet}
```

Rules:
1. Output ONLY a valid unified diff.
2. Fix ONLY the line(s) causing the error.
3. Do NOT include explanations outside the diff block.

Diff:
"""


def _generate_diff_direct(provider: str, framework: str, error_type: str,
                           error_message: str, file_path: str, snippet: str) -> str:
    prompt = _build_direct_prompt(framework, error_type, error_message,
                                  file_path, snippet)
    if provider == "gemini":
        from google import genai as google_genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set in .env")
        timeout_ms = int(os.getenv("LLM_TIMEOUT_SECONDS", "120")) * 1000
        client = google_genai.Client(
            api_key=api_key,
            http_options={"timeout": timeout_ms},
        )
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            contents=prompt,
            config={"temperature": 0},
        )
        raw = response.text
        print("[LLM] Gemini response received.", flush=True)
    elif provider == "groq":
        from groq import Groq as GroqClient
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set in .env")
        client = GroqClient(api_key=api_key)
        resp = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = resp.choices[0].message.content
    else:
        raise RuntimeError(f"Direct SDK fallback not implemented for provider '{provider}'")

    diff = _extract_diff(raw)
    if not diff:
        raise ValueError(f"Direct SDK returned no valid diff.\nRaw:\n{raw}")
    return diff