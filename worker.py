"""
core/worker.py
Redis Streams consumer — reads error log messages from the queue
and feeds them to the Orchestrator.

Run with:
    python -m core.worker
"""

import os
import time
import redis
import json
from dotenv import load_dotenv
from core.orchestrator import Orchestrator

load_dotenv()

REDIS_HOST     = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT     = int(os.getenv("REDIS_PORT", "6379"))
STREAM         = os.getenv("REDIS_STREAM", "error_logs")
GROUP          = os.getenv("REDIS_GROUP", "autofix_group")
CONSUMER       = os.getenv("REDIS_CONSUMER", "autofix_worker_1")
BLOCK_MS       = 5000       # block for 5s waiting for new messages
RETRY_SLEEP    = 3          # seconds between reconnect attempts


def ensure_group(r: redis.Redis):
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        print(f"[Worker] Created consumer group '{GROUP}' on stream '{STREAM}'.")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            pass   # Group already exists — fine
        else:
            raise


def run():
    orchestrator = Orchestrator()
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

    ensure_group(r)
    print(f"[Worker] Listening on Redis stream '{STREAM}' (group='{GROUP}')...")

    while True:
        try:
            messages = r.xreadgroup(
                groupname=GROUP,
                consumername=CONSUMER,
                streams={STREAM: ">"},
                count=1,
                block=BLOCK_MS,
            )

            if not messages:
                continue

            for stream_name, entries in messages:
                for msg_id, fields in entries:
                    raw_log = fields.get("log", "")
                    domain  = fields.get("domain")

                    print(f"\n[Worker] Received message {msg_id}")

                    result = orchestrator.process(raw_log, domain)
                    print(f"[Worker] Result → status={result.status}, "
                          f"pr_url={result.pr_url}, "
                          f"detail={result.detail}")

                    # Acknowledge message
                    r.xack(STREAM, GROUP, msg_id)

        except redis.exceptions.ConnectionError:
            print(f"[Worker] Redis disconnected. Retrying in {RETRY_SLEEP}s...")
            time.sleep(RETRY_SLEEP)
        except KeyboardInterrupt:
            print("[Worker] Shutting down.")
            break


if __name__ == "__main__":
    run()