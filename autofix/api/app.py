"""
api/app.py
FastAPI application exposing:
  POST /process        — process a raw log line directly (for testing)
  POST /webhook/merge  — Bitbucket PR merge webhook (feedback loop)
  POST /seed           — bulk-seed ChromaDB from historical records
  GET  /health         — health check
"""

import threading
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from autofix.core.orchestrator import Orchestrator
from autofix.rag.engine import RAGEngine

app = FastAPI(
    title="AutoFix Agent",
    description="Automated 5xx error log analysis and fix generation",
    version="1.0.0",
)

orchestrator = Orchestrator()
rag          = RAGEngine()


@app.on_event("startup")
async def _warm_up():
    """Pre-load embedding model and ChromaDB so first request isn't slow."""
    try:
        rag.find_similar("warmup")
        print("[Startup] RAG engine warmed up.", flush=True)
    except Exception:
        pass


# ── Request / Response models ─────────────────────────────────────────────────

class ProcessRequest(BaseModel):
    log: str
    domain: Optional[str] = None


class ErrorEventPayload(BaseModel):
    fingerprint: str
    tenant: str
    error: str
    stack_trace: str
    framework: Optional[str] = "cakephp2"
    exception_class: Optional[str] = None
    category: Optional[str] = None
    status_code: Optional[int] = None
    endpoint: Optional[str] = None
    source_file: Optional[str] = None
    first_seen_at: Optional[str] = None


class ProcessResponse(BaseModel):
    status: str
    error_message: str
    domain: Optional[str]
    commit_id: Optional[str] = None
    similarity: Optional[float] = None
    pr_id: Optional[int] = None
    pr_url: Optional[str] = None
    branch: Optional[str] = None
    detail: Optional[str] = None


class MergeWebhookPayload(BaseModel):
    """
    Bitbucket sends this when a PR is merged.
    We use it to update ChromaDB with the real fix commit.
    """
    pullrequest: dict
    repository: dict


class SeedRecord(BaseModel):
    error_text: str
    commit_id: str
    domain: Optional[str] = ""
    file: Optional[str] = ""
    line: Optional[int] = 0
    pr_url: Optional[str] = ""


class SeedRequest(BaseModel):
    records: list[SeedRecord]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/process", response_model=ProcessResponse)
def process_log(req: ProcessRequest):
    """
    Synchronously process a raw log line.
    Use this for testing; in production the Redis worker handles this.
    """
    result = orchestrator.process(req.log, req.domain)
    return ProcessResponse(
        status=result.status,
        error_message=result.error_message,
        domain=result.domain,
        commit_id=result.commit_id,
        similarity=result.similarity,
        pr_id=result.pr_id,
        pr_url=result.pr_url,
        branch=result.branch,
        detail=result.detail,
    )


@app.post("/webhook/error", status_code=202)
def receive_error_event(payload: ErrorEventPayload):
    """
    Accepts a structured error event and returns 202 immediately.
    Pipeline runs in a dedicated thread — avoids blocking the event loop
    and prevents uvicorn signal handling from interfering with the Claude
    Code subprocess (which caused false timeouts via BackgroundTasks).
    """
    thread = threading.Thread(
        target=orchestrator.process_event,
        args=(payload.model_dump(),),
        daemon=True,
    )
    thread.start()
    return {"accepted": True, "fingerprint": payload.fingerprint}


@app.post("/webhook/merge")
def bitbucket_merge_webhook(payload: MergeWebhookPayload, bg: BackgroundTasks):
    """
    Called by Bitbucket when a PR is merged.
    Stores the fix embedding in ChromaDB (feedback loop).

    Configure in Bitbucket: Repository Settings → Webhooks
    Events: Pull Request → Fulfilled
    """
    pr    = payload.pullrequest
    title = pr.get("title", "")

    # Only handle AUTO-FIX PRs
    if not title.startswith("[AUTO-FIX]"):
        return {"ignored": True}

    merge_commit = pr.get("merge_commit", {}).get("hash", "")
    pr_url       = pr.get("links", {}).get("html", {}).get("href", "")
    description  = pr.get("description", "")
    repo_slug    = payload.repository.get("slug", "")

    # Extract error message from PR title
    error_text = title.replace("[AUTO-FIX]", "").strip()

    # Run in background to not block webhook response
    bg.add_task(
        rag.store_fix,
        error_text=error_text,
        commit_id=merge_commit,
        domain="",
        file="",
        line=0,
        pr_url=pr_url,
    )

    return {"stored": True, "commit": merge_commit}


@app.post("/seed")
def seed_chroma(req: SeedRequest):
    """
    Bulk-seed ChromaDB from historical fix records.
    Use this once during initial setup to pre-populate the vector store.
    """
    records = [r.model_dump() for r in req.records]
    rag.seed_from_history(records)
    return {"seeded": len(records)}
