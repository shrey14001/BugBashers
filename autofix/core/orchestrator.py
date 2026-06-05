"""
core/orchestrator.py
Central pipeline — ties every component together.

Flow:
  parse log → embed → similarity search
      ├── KNOWN  → send email with commit ID
      └── NOVEL  → fetch code → LLM diff → create Bitbucket PR → store fix
"""

import os
import re
import subprocess
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

# ── Local-repo fallback config ────────────────────────────────────────────────
# REPO_ROOT is used as a fallback when the Bizom version API is unreachable
# (e.g. running locally without VPN). Set in .env.
REPO_ROOT           = os.getenv("REPO_ROOT", "")
SERVER_PREFIX_RE    = re.compile(r"^/var/sites/[^/]+/")
SKIP_PREFIXES       = ("/usr/share/", "/vendor/")


def _snippet_from_local(local_path: str, error_line: int):
    """Build a CodeSnippet from a local file (mirrors code_retriever logic)."""
    from autofix.core.code_retriever import CodeSnippet, _window
    with open(local_path, "r", errors="replace") as f:
        full_source = f.read()
    windowed, start_line, end_line = _window(full_source, error_line)
    return CodeSnippet(
        file_path=local_path,
        start_line=start_line,
        end_line=end_line,
        content=windowed,
        full_source=full_source,
    )


def _resolve_deployment_local(domain: str, frame_file: str) -> dict | None:
    """
    Fallback when DEPLOYMENT_API_BASE is a placeholder.
    Maps a server file path to a local path using REPO_ROOT and reads git HEAD.
    Returns the same dict shape as resolve_commit(), or None if unusable.
    """
    repo_slug = os.getenv("BITBUCKET_REPO_SLUG", "")
    if not REPO_ROOT or not repo_slug:
        return None
    # Map server path → local path
    local = SERVER_PREFIX_RE.sub("", frame_file)
    local_path = os.path.join(REPO_ROOT, local)
    if not os.path.exists(local_path):
        return None
    try:
        commit_hash = subprocess.check_output(
            ["git", "-C", REPO_ROOT, "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return None
    # repo_rel_path is what Bitbucket + patch CLI expect (no server prefix)
    repo_rel_path = local.lstrip("/")
    return {"commit_hash": commit_hash, "repo_slug": repo_slug,
            "local_path": local_path, "repo_rel_path": repo_rel_path}


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

        top_frame = parsed.best_frame()
        if top_frame is None:
            return PipelineResult(
                status="error",
                error_message=parsed.error_message,
                domain=parsed.domain,
                detail="No usable stack frame found.",
            )

        # 3. Resolve commit + repo from deployment API (with local fallback)
        local_path    = None
        commit_hash   = None
        repo_slug     = None
        repo_rel_path = None
        deploy_tag    = ""   # tag name used for branch naming (e.g. "staged_20260115_v1.13")

        # Strip server prefix (/var/sites/<domain>/) to get repo-relative path.
        repo_rel_path = SERVER_PREFIX_RE.sub("", top_frame.file).lstrip("/")
        if parsed.framework == "laravel" and repo_rel_path.startswith("app/laravel/"):
            repo_rel_path = repo_rel_path[len("app/laravel/"):]

        if parsed.domain:
            try:
                deployment  = resolve_commit(parsed.domain, framework=parsed.framework or "cakephp2")
                commit_hash = deployment["commit_hash"]
                repo_slug   = deployment["repo_slug"]
                deploy_tag  = deployment.get("tag", "")
                tag_info    = f" (tag: {deploy_tag})" if deploy_tag else ""
                print(f"[Orchestrator] Resolved commit {commit_hash[:8]} for domain '{parsed.domain}'{tag_info}", flush=True)
            except Exception as e:
                print(f"[Orchestrator] Deployment API failed: {e}. Trying local fallback.")

        if commit_hash is None:
            fallback = _resolve_deployment_local(parsed.domain or "", top_frame.file)
            if fallback is None:
                return PipelineResult(
                    status="error",
                    error_message=parsed.error_message,
                    domain=parsed.domain,
                    detail=(
                        "Could not resolve deployed commit. "
                        "Ensure the domain is present in the log and reachable via the Bizom version API, "
                        "or set REPO_ROOT + BITBUCKET_REPO_SLUG in .env for local fallback."
                    ),
                )
            commit_hash   = fallback["commit_hash"]
            repo_slug     = fallback["repo_slug"]
            local_path    = fallback["local_path"]
            repo_rel_path = fallback.get("repo_rel_path", repo_rel_path)

        print(f"[Orchestrator] Frame: {top_frame.file}:{top_frame.line}", flush=True)

        # 4. Fetch code snippet (Bitbucket API or local file)
        print("[Orchestrator] Fetching code snippet…", flush=True)
        try:
            if local_path:
                snippet = _snippet_from_local(local_path, top_frame.line)
                print(f"[Orchestrator] Using local file: {local_path}", flush=True)
            else:
                snippet = get_snippet(
                    repo_slug=repo_slug,
                    file_path=repo_rel_path,   # repo-relative
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

        # 5. Generate diff via LLM (direct SDK / LangChain with fallback)
        print("[Orchestrator] Generating fix via LLM (may take 30–90s)…", flush=True)
        # Use repo-relative path so LLM emits clean diff headers (a/app/... not a/var/sites/...)
        llm_file_path = repo_rel_path or top_frame.file
        try:
            diff = self.fix_gen.generate_diff_with_fallback(
                framework=parsed.framework,
                error_type=parsed.error_type,
                error_message=parsed.error_message,
                file_path=llm_file_path,
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

        # 6. Create Bitbucket PR (skip when AUTOFIX_SKIP_PR=1 for local testing)
        if os.getenv("AUTOFIX_SKIP_PR", "").lower() in ("1", "true", "yes"):
            print("[Orchestrator] AUTOFIX_SKIP_PR set — skipping Bitbucket PR.", flush=True)
            self.rag.store_fix(
                error_text=error_text,
                commit_id=commit_hash,
                domain=parsed.domain or "",
                file=top_frame.file,
                line=top_frame.line,
                pr_url=None,
            )
            return PipelineResult(
                status="fixed",
                error_message=parsed.error_message,
                domain=parsed.domain,
                detail="PR skipped (AUTOFIX_SKIP_PR). Diff generated successfully.",
            )

        print("[Orchestrator] Creating Bitbucket PR…", flush=True)
        try:
            # Use repo-relative path (not full server path) so Bitbucket
            # API and the patch CLI can locate the file correctly.
            pr_file_path = repo_rel_path or top_frame.file
            pr = create_fix_pr(
                repo_slug=repo_slug,
                file_path=pr_file_path,
                error_message=parsed.error_message,
                diff_patch=diff,
                commit_hash=commit_hash,
                tag=deploy_tag,
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
