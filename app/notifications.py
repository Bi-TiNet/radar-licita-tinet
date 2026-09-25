from __future__ import annotations

import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

import requests

from .config import settings
from .db import execute
from .domain import classify_focus


def render_message(item: dict) -> str:
    _, _, _, company = classify_focus(
        item.get("title") or "", item.get("description") or "", str(item.get("municipality_code") or "")
    )
    value = item.get("estimated_value")
    if value:
        value_text = ("R$ {:,.2f}".format(value)
                      .replace(",", "X")
                      .replace(".", ",")
                      .replace("X", "."))
    else:
        value_text = "Não informado"

    return (
        "🚨 NOVA OPORTUNIDADE DE LICITAÇÃO\n\n"
        "📍 Município: {}\n"
        "🏢 Empresa: {}\n"
        "🏛️ Órgão: {}\n"
        "🏷️ Categoria: {}\n"
        "🎯 Aderência: {}%\n\n"
        "📄 {}\n\n"
        "💰 Valor: {}\n"
        "⏰ Prazo: {}\n"
        "🔗 {}"
    ).format(
        item.get("municipality") or "Não informado",
        company or "Não classificada",
        item.get("agency") or "Órgão público",
        item.get("category") or "Outras oportunidades",
        item.get("score", 0),
        item.get("title") or "Oportunidade pública",
        value_text,
        item.get("proposal_end_at") or "Não informado",
        item.get("url") or "Sem link",
    )


def _log(opportunity_id: int, channel: str, status: str, detail: str = "") -> None:
    if opportunity_id <= 0:
        return
    execute(
        "INSERT INTO notifications(opportunity_id,channel,status,detail,sent_at) VALUES (?,?,?,?,?)",
        (
            opportunity_id,
            channel,
            status,
            detail[:1000],
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def _email_recipients() -> List[str]:
    return [x.strip() for x in (settings.email_to or "").split(",") if x.strip()]


def _whatsapp_recipients() -> List[str]:
    return [
        "".join(ch for ch in x if ch.isdigit())
        for x in (settings.whatsapp_numbers or "").split(",")
        if x.strip()
    ]


def send_email(item: dict, message: str, opportunity_id: int, recipients: Optional[List[str]] = None, subject: Optional[str] = None) -> Dict[str, Any]:
    recipients = _email_recipients() if recipients is None else recipients
    if not settings.smtp_host or not recipients:
        return {"channel": "email", "status": "skipped", "detail": "E-mail não configurado"}

    try:
        msg = EmailMessage()
        _, _, _, company = classify_focus(
            item.get("title") or "", item.get("description") or "", str(item.get("municipality_code") or "")
        )
        msg["Subject"] = subject or "Licitação {}: {}".format(
            company or "Radar Licita", item.get("municipality") or "oportunidade"
        )
        msg["From"] = settings.smtp_from or settings.smtp_user
        msg["To"] = ", ".join(recipients)
        msg.set_content(message)

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg, to_addrs=recipients)

        detail = "Enviado para: " + ", ".join(recipients)
        _log(opportunity_id, "email", "sent", detail)
        return {"channel": "email", "status": "sent", "detail": detail}
    except Exception as exc:
        detail = str(exc)
        _log(opportunity_id, "email", "error", detail)
        return {"channel": "email", "status": "error", "detail": detail}


def send_whatsapp(item: dict, message: str, opportunity_id: int, numbers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    numbers = _whatsapp_recipients() if numbers is None else numbers
    if not (
        settings.evolution_api_url
        and settings.evolution_instance
        and settings.evolution_api_key
        and numbers
    ):
        return [{
            "channel": "whatsapp",
            "status": "skipped",
            "detail": "Evolution API não configurada",
        }]

    endpoint = "{}/message/sendText/{}".format(
        settings.evolution_api_url.rstrip("/"),
        settings.evolution_instance,
    )
    headers = {
        "apikey": settings.evolution_api_key,
        "Content-Type": "application/json",
    }

    results = []
    for number in numbers:
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json={"number": number, "text": message},
                timeout=35,
            )
            response.raise_for_status()
            detail = "Enviado para {}".format(number)
            _log(opportunity_id, "whatsapp", "sent", detail)
            results.append({
                "channel": "whatsapp",
                "status": "sent",
                "number": number,
                "detail": detail,
            })
        except Exception as exc:
            detail = "{}: {}".format(number, exc)
            _log(opportunity_id, "whatsapp", "error", detail)
            results.append({
                "channel": "whatsapp",
                "status": "error",
                "number": number,
                "detail": str(exc),
            })
    return results


def send_all(item: dict) -> List[Dict[str, Any]]:
    results = []
    message = render_message(item)
    opportunity_id = int(item.get("id") or 0)

    results.append(send_email(item, message, opportunity_id))
    results.extend(send_whatsapp(item, message, opportunity_id))

    if settings.telegram_bot_token and settings.telegram_chat_id:
        try:
            url = "https://api.telegram.org/bot{}/sendMessage".format(settings.telegram_bot_token)
            response = requests.post(
                url,
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": message,
                    "disable_web_page_preview": True,
                },
                timeout=20,
            )
            response.raise_for_status()
            _log(opportunity_id, "telegram", "sent")
            results.append({"channel": "telegram", "status": "sent"})
        except Exception as exc:
            _log(opportunity_id, "telegram", "error", str(exc))
            results.append({"channel": "telegram", "status": "error", "detail": str(exc)})

    if settings.webhook_url:
        try:
            response = requests.post(
                settings.webhook_url,
                json={"event": "new_opportunity", "opportunity": item, "message": message},
                timeout=20,
            )
            response.raise_for_status()
            _log(opportunity_id, "webhook", "sent")
            results.append({"channel": "webhook", "status": "sent"})
        except Exception as exc:
            _log(opportunity_id, "webhook", "error", str(exc))
            results.append({"channel": "webhook", "status": "error", "detail": str(exc)})

    return results
