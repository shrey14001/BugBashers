"""
core/llm_chain.py
LangChain prompt template + LLMChain for generating unified diff patches.

Supports:
  - OpenAI GPT-4 / GPT-4o
  - Anthropic Claude (via langchain-anthropic)
  - Local CodeLlama via Ollama
"""

import os
import re
from dotenv import load_dotenv

load_dotenv()

from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.output_parsers import RegexParser


# ── LLM factory ──────────────────────────────────────────────────────────────

def _build_llm():
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "openai":
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

    elif provider == "codellamaF":
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
        self._chain = LLMChain(llm=_build_llm(), prompt=_PROMPT)

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
        raw = self._chain.run(
            framework=framework,
            error_type=error_type,
            error_message=error_message,
            file_path=file_path,
            snippet=snippet,
            start_line=start_line,
            end_line=end_line,
        )

        diff = _extract_diff(raw)
        if not diff:
            raise ValueError(f"LLM returned no valid diff.\nRaw output:\n{raw}")

        return diff