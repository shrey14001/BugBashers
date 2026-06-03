"""
rag/engine.py
ChromaDB + LangChain vector store for error similarity search.

Responsibilities:
  - Embed incoming error text
  - Search for similar past errors (known error path)
  - Store new fix embeddings after a PR is merged (feedback loop)
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

# ── LangChain imports ─────────────────────────────────────────────────────────
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document


# ── Config ────────────────────────────────────────────────────────────────────
PERSIST_DIR  = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
COLLECTION   = os.getenv("CHROMA_COLLECTION", "error_fixes")
THRESHOLD    = float(os.getenv("SIMILARITY_THRESHOLD", "0.85"))
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")


@dataclass
class SimilarFix:
    commit_id: str
    domain: str
    file: str
    line: int
    score: float          # 0–1, higher = more similar
    pr_url: str | None


def _get_embedding_model():
    """
    Return the configured embedding model.
    Falls back to a free HuggingFace model if no OpenAI key is set.
    """
    if os.getenv("OPENAI_API_KEY") and LLM_PROVIDER == "openai":
        return OpenAIEmbeddings(model="text-embedding-3-small")
    # Free fallback — runs locally, no API key needed
    return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")


class RAGEngine:
    def __init__(self):
        self._embedding = _get_embedding_model()
        self._store = Chroma(
            collection_name=COLLECTION,
            embedding_function=self._embedding,
            persist_directory=PERSIST_DIR,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def find_similar(self, error_text: str) -> SimilarFix | None:
        """
        Search ChromaDB for a similar past error.
        Returns a SimilarFix if score >= THRESHOLD, else None.
        """
        results = self._store.similarity_search_with_relevance_scores(
            query=error_text,
            k=1,
        )
        if not results:
            return None

        doc, score = results[0]
        if score < THRESHOLD:
            return None

        meta = doc.metadata
        return SimilarFix(
            commit_id=meta.get("commit_id", ""),
            domain=meta.get("domain", ""),
            file=meta.get("file", ""),
            line=int(meta.get("line", 0)),
            score=round(score, 4),
            pr_url=meta.get("pr_url"),
        )

    def store_fix(
        self,
        error_text: str,
        commit_id: str,
        domain: str,
        file: str,
        line: int,
        pr_url: str | None = None,
    ) -> None:
        """
        Persist a new fix embedding after a PR is merged.
        Called by the feedback loop (webhook from Bitbucket).
        """
        doc = Document(
            page_content=error_text,
            metadata={
                "commit_id": commit_id,
                "domain": domain,
                "file": file,
                "line": str(line),
                "pr_url": pr_url or "",
            },
        )
        self._store.add_documents([doc])
        self._store.persist()

    def seed_from_history(self, records: list[dict]) -> None:
        """
        Bulk-seed ChromaDB from a list of historical fix records.
        Each record: { error_text, commit_id, domain, file, line, pr_url }
        Used during initial setup to pre-populate the store.
        """
        docs = [
            Document(
                page_content=r["error_text"],
                metadata={
                    "commit_id": r["commit_id"],
                    "domain": r.get("domain", ""),
                    "file": r.get("file", ""),
                    "line": str(r.get("line", 0)),
                    "pr_url": r.get("pr_url", ""),
                },
            )
            for r in records
        ]
        self._store.add_documents(docs)
        self._store.persist()
        print(f"[RAG] Seeded {len(docs)} records into ChromaDB.")