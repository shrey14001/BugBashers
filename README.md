# AutoFix Agent — Automated 5xx Error Log Analysis & Fix Generation

> Built per Technical Design Document v1.0 (2026-05-15)
> Stack: LangChain · ChromaDB · FastAPI · Redis Streams · Bitbucket REST API

---

## Architecture

```
[Production Logs] → Redis Stream → Worker
                                      │
                              LangChain Orchestrator
                                      │
                    ┌─────────────────┴──────────────────┐
                    ▼                                     ▼
             ChromaDB similarity                   Novel error
             score ≥ 0.85?
                    │                                     │
                   YES                                   NO
                    │                                     │
             Send email with               1. Resolve commit (Deployment API)
             existing commit ID            2. Fetch code snippet (Bitbucket)
                                           3. Generate diff (LLM via LangChain)
                                           4. Apply patch + open PR (Bitbucket)
                                           5. Store fix in ChromaDB
```

---

## Quick Start

### 1. Clone & configure
```bash
cp .env.example .env
# Edit .env with your API keys and credentials
```

### 2. Run with Docker Compose
```bash
docker-compose up --build
```

This starts:
- **Redis** on port 6379 (message queue)
- **AutoFix API** on port 8000 (FastAPI)
- **Worker** (Redis stream consumer)
- **Neo4j** on port 7474 (Phase 3 knowledge graph)

### 3. Test the API
```bash
# Health check
curl http://localhost:8000/health

# Process a Laravel log line directly
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{
    "log": "[2024-01-15 10:23:45] production.ERROR: Call to a member function id() on null {\"exception\":\"[object] (Error(code: 0): Call to a member function id() on null at /var/www/app/Http/Controllers/PaymentController.php:42)\n[stacktrace]\n#0 /var/www/app/Services/PaymentService.php(88): App\\Http\\Controllers\\PaymentController->processPayment()\"}",
    "domain": "client-a.example.com"
  }'
```

### 4. Seed ChromaDB from historical fixes
```bash
curl -X POST http://localhost:8000/seed \
  -H "Content-Type: application/json" \
  -d '{
    "records": [
      {
        "error_text": "Error: Call to a member function id() on null\n/var/www/app/Http/Controllers/PaymentController.php:42",
        "commit_id": "abc123def456",
        "domain": "client-a.example.com",
        "file": "/var/www/app/Http/Controllers/PaymentController.php",
        "line": 42,
        "pr_url": "https://bitbucket.org/workspace/repo/pull-requests/101"
      }
    ]
  }'
```

### 5. Run tests
```bash
pip install pytest
pytest tests/ -v
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key (for GPT-4 + embeddings) |
| `ANTHROPIC_API_KEY` | Claude API key (alternative LLM) |
| `LLM_PROVIDER` | `openai` \| `anthropic` \| `codellamaF` |
| `CHROMA_PERSIST_DIR` | Path for ChromaDB storage |
| `SIMILARITY_THRESHOLD` | 0–1, above = known error (default 0.85) |
| `REDIS_HOST` | Redis host |
| `BITBUCKET_WORKSPACE` | Bitbucket workspace slug |
| `BITBUCKET_USERNAME` | Bitbucket username |
| `BITBUCKET_APP_PASSWORD` | Bitbucket app password |
| `DEPLOYMENT_API_BASE` | Your internal deployment API base URL |
| `SMTP_HOST` | AWS SES SMTP host |
| `ALERT_TO_EMAIL` | Dev team alert email |

---

## Project Structure

```
autofix/
├── api/
│   └── app.py              # FastAPI endpoints
├── bitbucket/
│   └── pr_creator.py       # Branch + patch + PR creation
├── core/
│   ├── orchestrator.py     # Central pipeline coordinator
│   ├── llm_chain.py        # LangChain prompt + LLM
│   ├── code_retriever.py   # Bitbucket src API + git CLI fallback
│   ├── notifier.py         # Email via AWS SES
│   └── worker.py           # Redis stream consumer
├── parsers/
│   ├── laravel.py          # Laravel JSON log parser
│   └── cakephp2.py         # CakePHP 2 text log parser
├── rag/
│   └── engine.py           # ChromaDB vector store
├── tests/
│   └── test_parsers.py     # Parser unit tests
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Bitbucket Webhook Setup (Feedback Loop)

After a human reviews and merges an AUTO-FIX PR, Bitbucket will call your
webhook to store the fix in ChromaDB automatically.

1. Go to: **Repository Settings → Webhooks → Add webhook**
2. URL: `https://your-server.com/webhook/merge`
3. Events: ✅ Pull Request → Fulfilled (merged)

---

## Implementation Phases

### Phase 1 — MVP ✅
- [x] Laravel log parser
- [x] ChromaDB + LangChain similarity search
- [x] LLM fix generation (GPT-4 / Claude)
- [x] Bitbucket PR creation
- [x] Email notification for known errors
- [x] Redis stream worker

### Phase 2 — Production Ready
- [ ] CakePHP 2 parser (skeleton done, needs real log samples)
- [ ] Rate limiting (max 1 PR per domain per 5 min)
- [ ] LangSmith tracing integration
- [ ] Patch sandbox validation (`php -l`)

### Phase 3 — Advanced
- [ ] RAG over full codebase (embed all PHP functions)
- [ ] Knowledge Graph (Neo4j) for error/file/service relationships
- [ ] Fine-tune local embedding model on PHP error corpus
- [ ] Self-healing: auto-merge trivial fixes after CI passes
