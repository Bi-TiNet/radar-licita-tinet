from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List

from .db import execute, row, rows
from .notifications import send_all

SYNC_LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_workflow_schema() -> None:
    columns = {item["name"] for item in rows("PRAGMA table_info(opportunities)")}
    additions = {
        "viewed_at": "TEXT",
        "first_seen_at": "TEXT",
        "last_seen_at": "TEXT",
    }
    for name, sql_type in additions.items():
        if name not in columns:
            execute("ALTER TABLE opportunities ADD COLUMN {} {}".format(name, sql_type))

    execute(
        """
        UPDATE opportunities
        SET first_seen_at = COALESCE(first_seen_at, created_at),
            last_seen_at = COALESCE(last_seen_at, updated_at)
        """
    )


def workflow_status(item: Dict[str, Any]) -> str:
    if int(item.get("dismissed") or 0) == 1:
        return "descartada"
    if int(item.get("favorite") or 0) == 1:
        return "favorita"
    if item.get("viewed_at"):
        return "visualizada"
    if item.get("notified_at"):
        return "notificada"
    return "nova"


def decorate(item: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(item)
    result["workflow_status"] = workflow_status(result)
    return result


def mark_seen(opportunity_id: int) -> None:
    now = now_iso()
    execute(
        """
        UPDATE opportunities
        SET viewed_at = COALESCE(viewed_at, ?),
            updated_at = ?
        WHERE id = ?
        """,
        (now, now, opportunity_id),
    )


def successful_notification_exists(opportunity_id: int) -> bool:
    return bool(
        row(
            """
            SELECT id
            FROM notifications
            WHERE opportunity_id = ?
              AND status = 'sent'
            LIMIT 1
            """,
            (opportunity_id,),
        )
    )


def notify_if_needed(item: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    opportunity_id = int(item.get("id") or 0)

    if not force:
        if item.get("notified_at"):
            return {"status": "skipped", "reason": "already_notified", "results": []}

        if successful_notification_exists(opportunity_id):
            execute(
                "UPDATE opportunities SET notified_at=COALESCE(notified_at,?) WHERE id=?",
                (now_iso(), opportunity_id),
            )
            return {"status": "skipped", "reason": "already_notified", "results": []}

    results: List[Dict[str, Any]] = send_all(item)
    sent = [r for r in results if r.get("status") == "sent"]

    if sent:
        now = now_iso()
        execute(
            "UPDATE opportunities SET notified_at=?,updated_at=? WHERE id=?",
            (now, now, opportunity_id),
        )

    return {
        "status": "sent" if sent else "no_channel_sent",
        "sent": len(sent),
        "results": results,
    }
