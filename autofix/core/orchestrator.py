"""
core/orchestrator.py
Central pipeline — ties every component together.

Flow:
  parse log → embed → similarity search
      ├── KNOWN  → send email with commit ID
      └── NOVEL  → fetch code → LLM diff → create Bitbucket PR → store fix
"""

import os
import traceback
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

from autofix.parsers.laravel   import parse as parse_laravel,  ParsedError
from autofix.parsers.cakephp2  import parse as parse_cakephp2
from autofix.rag.engine        import RAGEngine
from autofix.core.code_retriever import resolve_commit, get_snippet
from autofix.core.llm_chain    import FixGenerator
from autofix.core.notifier     import send_known_error_email
from autofix.bitbucket.pr_creator import create_fix_pr


@dataclass
class PipelineResult:
    status: str          # "known" | "fixed" | "error"
    error_message: str
    domain: str | None
    # known path
    commit_id: str | None = None
    similarity: float | None = None
    pr_url: str | None = None
    # novel path
    pr_id: int | None = None
    branch: str | None = None
    detail: str | None = None


class Orchestrator:
    def __init__(self):
        self.rag       = RAGEngine()
        self.fix_gen   = FixGenerator()

    # ── Main entry point ──────────────────────────────────────────────────────

    def process(self, raw_log: str, domain: str | None = None) -> PipelineResult:
        """
        Process a single raw log line or block.
        Returns a PipelineResult describing what happened.
        """
        # 1. Parse
        parsed = self._parse(raw_log, domain)
        if parsed is None:
            return PipelineResult(
                status="error",
                error_message="",
                domain=domain,
                detail="Could not parse log line — unrecognised format.",
            )

        error_text = parsed.embedding_text()
        print(f"\n[Orchestrator] Processing: {error_text[:120]}")

        # 2. Similarity search
        similar = self.rag.find_similar(error_text)

        if similar:
            return self._handle_known(parsed, similar)
        else:
            return self._handle_novel(parsed, error_text)

    # ── Known error path ──────────────────────────────────────────────────────

    def _handle_known(self, parsed: ParsedError, similar) -> PipelineResult:
        print(f"[Orchestrator] KNOWN error (score={similar.score}). Sending email.")
        send_known_error_email(
            error_message=parsed.error_message,
            commit_id=similar.commit_id,
            pr_url=similar.pr_url,
            similarity_score=similar.score,
            domain=parsed.domain,
        )
        return PipelineResult(
            status="known",
            error_message=parsed.error_message,
            domain=parsed.domain,
            commit_id=similar.commit_id,
            similarity=similar.score,
            pr_url=similar.pr_url,
        )

    # ── Novel error path ──────────────────────────────────────────────────────

    def _handle_novel(self, parsed: ParsedError, error_text: str) -> PipelineResult:
        print(f"[Orchestrator] NOVEL error. Starting fix generation.")

        top_frame = parsed.top_frame()
        if top_frame is None:
            return PipelineResult(
                status="error",
                error_message=parsed.error_message,
                domain=parsed.domain,
                detail="No usable stack frame found.",
            )

        # 3. Resolve commit + repo from deployment API
        try:
            deployment = resolve_commit(parsed.domain or "default")
            commit_hash = deployment["commit_hash"]
            repo_slug   = deployment["repo_slug"]
        except Exception as e:
            return PipelineResult(
                status="error",
                error_message=parsed.error_message,
                domain=parsed.domain,
                detail=f"Deployment API error: {e}",
            )

        # 4. Fetch code snippet from Bitbucket
        try:
            snippet = get_snippet(
                repo_slug=repo_slug,
                file_path=top_frame.file,
                error_line=top_frame.line,
                commit_hash=commit_hash,
            )
        except Exception as e:
            return PipelineResult(
                status="error",
                error_message=parsed.error_message,
                domain=parsed.domain,
                detail=f"Code retrieval error: {e}",
            )

        # 5. Generate diff via LLM
        try:
            diff = self.fix_gen.generate_diff(
                framework=parsed.framework,
                error_type=parsed.error_type,
                error_message=parsed.error_message,
                file_path=top_frame.file,
                snippet=snippet.content,
                start_line=snippet.start_line,
                end_line=snippet.end_line,
            )
        except Exception as e:
            return PipelineResult(
                status="error",
                error_message=parsed.error_message,
                domain=parsed.domain,
                detail=f"LLM error: {e}",
            )

        # 6. Create Bitbucket PR
        try:
            pr = create_fix_pr(
                repo_slug=repo_slug,
                file_path=top_frame.file,
                error_message=parsed.error_message,
                diff_patch=diff,
                commit_hash=commit_hash,
            )
        except Exception as e:
            return PipelineResult(
                status="error",
                error_message=parsed.error_message,
                domain=parsed.domain,
                detail=f"PR creation error: {e}",
            )

        # 7. Store in ChromaDB (feedback loop — also done on PR merge via webhook)
        self.rag.store_fix(
            error_text=error_text,
            commit_id=pr.commit_hash,
            domain=parsed.domain or "",
            file=top_frame.file,
            line=top_frame.line,
            pr_url=pr.pr_url,
        )

        print(f"[Orchestrator] PR created: {pr.pr_url}")
        return PipelineResult(
            status="fixed",
            error_message=parsed.error_message,
            domain=parsed.domain,
            pr_id=pr.pr_id,
            pr_url=pr.pr_url,
            branch=pr.branch,
        )

    # ── Parser router ─────────────────────────────────────────────────────────

    def _parse(self, raw_log: str, domain: str | None) -> ParsedError | None:
        # Try Laravel first, then CakePHP 2
        parsed = parse_laravel(raw_log, domain)
        if parsed:
            return parsed
        return parse_cakephp2(raw_log, domain)
