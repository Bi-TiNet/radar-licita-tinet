"""Scheduled BLL collector for GitHub Actions and Supabase.

The browser collector and scoring rules remain the same as the local radar.
Only persistence changes. No secret key is ever sent to the browser.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import requests

from .bll import fetch_all
from .config import settings
from .notifications import render_message, send_email, send_whatsapp
from .telegram_api import send_message as send_telegram_message


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CloudStore:
    def __init__(self) -> None:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url.startswith("https://") or not key:
            raise RuntimeError("SUPABASE_URL e SUPABASE_SECRET_KEY são obrigatórios")
        self.base_url = url + "/rest/v1"
        self.session = requests.Session()
        self.session.headers.update({"apikey": key, "Content-Type": "application/json"})
        if key.startswith("eyJ"):
            # Legacy service_role JWTs also work; new sb_secret keys are API keys only.
            self.session.headers["Authorization"] = "Bearer " + key

    def request(self, method: str, table: str, *, params=None, payload=None, prefer=None) -> Any:
        headers = {"Prefer": prefer} if prefer else None
        response = self.session.request(
            method,
            f"{self.base_url}/{table}",
            params=params,
            json=payload,
            headers=headers,
            timeout=45,
        )
        if not response.ok:
            raise RuntimeError(f"Supabase {table}: HTTP {response.status_code}: {response.text[:500]}")
        return response.json() if response.content else None

    def start_run(self) -> int:
        rows = self.request(
            "POST", "sync_runs",
            payload={"source": "BLL", "started_at": now_iso(), "status": "running"},
            prefer="return=representation",
        )
        return int(rows[0]["id"])

    def finish_run(self, run_id: int, status: str, totals: dict, detail: str = "") -> None:
        self.request(
            "PATCH", "sync_runs",
            params={"id": f"eq.{run_id}"},
            payload={
                "finished_at": now_iso(),
                "status": status,
                "found": totals["found"],
                "inserted": totals["inserted"],
                "updated": totals["updated"],
                "detail": detail[:2000],
            },
        )

    def upsert(self, item: dict) -> tuple[str, dict]:
        external_id = str(item["external_id"])
        previous = self.request(
            "GET", "opportunities",
            params={"external_id": f"eq.{external_id}", "select": "id,notified_at,created_at,first_seen_at"},
        )
        now = now_iso()
        payload = {
            "external_id": external_id,
            "source": item["source"],
            "municipality_code": item["municipality_code"],
            "municipality": item["municipality"],
            "agency": item.get("agency"),
            "title": item["title"],
            "description": item.get("description") or item["title"],
            "modality": item.get("modality"),
            "notice_number": item.get("notice_number"),
            "published_at": item.get("published_at"),
            "proposal_end_at": item.get("proposal_end_at"),
            "estimated_value": item.get("estimated_value"),
            "url": item.get("url"),
            "score": int(item["score"]),
            "category": item.get("category"),
            "matched_terms": item.get("matched_terms") or [],
            "status": item.get("status") or "desconhecido",
            "raw_json": item.get("raw") or {},
            "last_seen_at": now,
            "updated_at": now,
        }
        if not previous:
            payload["first_seen_at"] = now
            payload["created_at"] = now
        saved = self.request(
            "POST", "opportunities",
            params={"on_conflict": "external_id"},
            payload=payload,
            prefer="resolution=merge-duplicates,return=representation",
        )
        return ("updated" if previous else "inserted", saved[0])

    def log_notification(self, opportunity_id: int, result: dict) -> None:
        self.request(
            "POST", "notifications",
            payload={
                "opportunity_id": opportunity_id,
                "channel": result.get("channel", "desconhecido"),
                "recipient": result.get("recipient"),
                "status": result.get("status", "error"),
                "detail": str(result.get("detail") or "")[:1000],
                "sent_at": now_iso(),
            },
        )

    def delivered_recipients(self, opportunity_id: int) -> set[tuple[str, str]]:
        rows = self.request(
            "GET", "notifications",
            params={
                "opportunity_id": f"eq.{opportunity_id}",
                "status": "eq.sent",
                "select": "channel,recipient",
            },
        )
        return {(row["channel"], row["recipient"]) for row in rows if row.get("recipient")}

    def mark_notified(self, opportunity_id: int) -> None:
        self.request(
            "PATCH", "opportunities",
            params={"id": f"eq.{opportunity_id}"},
            payload={"notified_at": now_iso(), "updated_at": now_iso()},
        )

    def mark_baselined(self, opportunity_id: int) -> None:
        self.request(
            "PATCH", "opportunities",
            params={"id": f"eq.{opportunity_id}"},
            payload={"alert_baselined_at": now_iso()},
        )


def enabled_channels() -> set[str]:
    channels = {
        value.strip().lower()
        for value in os.environ.get("RADAR_NOTIFICATION_CHANNELS", "email,whatsapp").split(",")
        if value.strip()
    }
    if not channels or not channels <= {"email", "telegram", "whatsapp"}:
        raise RuntimeError("Configure canais de alerta válidos: email, telegram e/ou whatsapp")
    return channels


def recipients() -> set[tuple[str, str]]:
    channels = enabled_channels()
    destinations: set[tuple[str, str]] = set()
    if "email" in channels:
        emails = {value.strip().lower() for value in settings.email_to.split(",") if value.strip()}
        destinations.update(("email", value) for value in emails)
    if "whatsapp" in channels:
        phones = {"".join(ch for ch in value if ch.isdigit()) for value in settings.whatsapp_numbers.split(",") if value.strip()}
        destinations.update(("whatsapp", value) for value in phones)
    if "telegram" in channels:
        chats = {value.strip() for value in settings.telegram_chat_id.split(",") if value.strip()}
        if any(not value.lstrip("-").isdigit() for value in chats):
            raise RuntimeError("Configure IDs numéricos dos chats Telegram")
        destinations.update(("telegram", value) for value in chats)
    return destinations


def validate_alert_config() -> None:
    channels = enabled_channels()
    destinations = recipients()
    if "email" in channels:
        if sum(channel == "email" for channel, _ in destinations) != 2:
            raise RuntimeError("Configure exatamente dois e-mails de alerta")
        if not (settings.smtp_host and settings.smtp_user and settings.smtp_password):
            raise RuntimeError("Configure SMTP antes de ativar os alertas por e-mail")
    if "whatsapp" in channels:
        if sum(channel == "whatsapp" for channel, _ in destinations) != 2:
            raise RuntimeError("Configure exatamente dois números de WhatsApp")
        if not (settings.evolution_api_url and settings.evolution_instance and settings.evolution_api_key):
            raise RuntimeError("Configure uma API pública de WhatsApp antes de ativar os alertas")
        if settings.evolution_api_url.startswith(("http://127.", "http://localhost", "http://10.", "http://192.168.")):
            raise RuntimeError("A API de WhatsApp local não é alcançável pelo GitHub Actions")
    if "telegram" in channels:
        count = sum(channel == "telegram" for channel, _ in destinations)
        if count != 2 or not settings.telegram_bot_token:
            raise RuntimeError("Configure o bot e exatamente dois chats individuais Telegram")


def send_pending(item: dict, already_sent: set[tuple[str, str]]) -> list[dict]:
    message = render_message(item)
    results = []
    for channel, destination in sorted(recipients() - already_sent):
        if channel == "email":
            result = send_email(item, message, 0, recipients=[destination])
            results.append({**result, "recipient": destination})
        elif channel == "telegram":
            try:
                send_telegram_message(destination, message)
                results.append({"channel": "telegram", "recipient": destination, "status": "sent"})
            except RuntimeError as exc:
                results.append({"channel": "telegram", "recipient": destination, "status": "error", "detail": str(exc)})
        elif channel == "whatsapp":
            for result in send_whatsapp(item, message, 0, numbers=[destination]):
                results.append({**result, "recipient": destination})
    return results


def collect(store: CloudStore, *, fetcher=fetch_all, notifier=send_pending) -> dict:
    run_id = store.start_run()
    totals = {"found": 0, "inserted": 0, "updated": 0, "notified": 0}
    errors: list[str] = []
    allow_notifications = os.environ.get("RADAR_NOTIFICATIONS_ENABLED") == "1"
    try:
        items = fetcher()
        totals["found"] = len(items)
        for item in items:
            try:
                action, saved = store.upsert(item)
                totals[action] += 1
                if not allow_notifications:
                    if not saved.get("notified_at") and not saved.get("alert_baselined_at"):
                        store.mark_baselined(int(saved["id"]))
                    continue
                eligible = (
                    not saved.get("notified_at")
                    and not saved.get("alert_baselined_at")
                    and int(saved.get("score") or 0) >= settings.min_score_notify
                    and saved.get("status") != "encerrada"
                )
                if eligible:
                    delivered = store.delivered_recipients(int(saved["id"]))
                    # id=0 prevents the legacy local SQLite logger from writing.
                    results = notifier({**saved, "id": 0}, delivered)
                    for result in results:
                        store.log_notification(int(saved["id"]), result)
                    sent_now = {
                        (result["channel"], result["recipient"])
                        for result in results if result.get("status") == "sent" and result.get("recipient")
                    }
                    if recipients() <= delivered | sent_now:
                        store.mark_notified(int(saved["id"]))
                        totals["notified"] += 1
                    else:
                        errors.append(f"alerta incompleto para {item.get('external_id', '?')}")
            except Exception as exc:
                errors.append(f"{item.get('external_id', '?')}: {exc}")
    except Exception as exc:
        errors.append(f"coleta BLL: {exc}")
    status = "partial" if errors else "success"
    store.finish_run(run_id, status, totals, " | ".join(errors))
    print(json.dumps({"status": status, **totals, "errors": errors[:10]}, ensure_ascii=False))
    if errors:
        raise RuntimeError(f"Coleta incompleta: {len(errors)} erro(s)")
    return totals


if __name__ == "__main__":
    if os.environ.get("RADAR_NOTIFICATIONS_ENABLED") == "1":
        validate_alert_config()
    collect(CloudStore())
