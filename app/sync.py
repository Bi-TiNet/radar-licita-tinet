from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .bll import fetch_all
from .config import settings
from .db import execute, row, upsert_opportunity
from .workflow import SYNC_LOCK, ensure_workflow_schema, notify_if_needed, now_iso


def run_sync() -> Dict[str, Any]:
    ensure_workflow_schema()

    if not SYNC_LOCK.acquire(blocking=False):
        return {
            "status": "skipped",
            "reason": "sync_already_running",
            "found": 0,
            "inserted": 0,
            "updated": 0,
            "notified": 0,
            "errors": [],
        }

    started = datetime.now(timezone.utc).isoformat()
    run_id = execute(
        "INSERT INTO sync_runs(source,started_at,status) VALUES (?,?,?)",
        ("BLL", started, "running"),
    )

    totals = {
        "found": 0,
        "inserted": 0,
        "updated": 0,
        "notified": 0,
        "skipped_notifications": 0,
        "errors": [],
    }

    try:
        items = fetch_all()
        totals["found"] = len(items)

        for item in items:
            action, opportunity_id = upsert_opportunity(item)
            totals[action] += 1

            execute(
                """
                UPDATE opportunities
                SET first_seen_at = COALESCE(first_seen_at, created_at, ?),
                    last_seen_at = ?
                WHERE id = ?
                """,
                (now_iso(), now_iso(), opportunity_id),
            )

            stored = row("SELECT * FROM opportunities WHERE id=?", (opportunity_id,))
            eligible = (
                stored
                and int(stored.get("score") or 0) >= settings.min_score_notify
                and stored.get("status") != "encerrada"
            )

            if eligible:
                result = notify_if_needed(stored, force=False)
                if result.get("status") == "sent":
                    totals["notified"] += 1
                elif result.get("reason") == "already_notified":
                    totals["skipped_notifications"] += 1

    except Exception as exc:
        totals["errors"].append("BLL: {}".format(exc))

    finally:
        finished = datetime.now(timezone.utc).isoformat()
        status = "partial" if totals["errors"] else "success"

        execute(
            """
            UPDATE sync_runs
            SET finished_at=?,status=?,found=?,inserted=?,updated=?,detail=?
            WHERE id=?
            """,
            (
                finished,
                status,
                totals["found"],
                totals["inserted"],
                totals["updated"],
                " | ".join(totals["errors"]),
                run_id,
            ),
        )
        SYNC_LOCK.release()

    return {
        "status": status,
        **totals,
        "started_at": started,
        "finished_at": finished,
    }
