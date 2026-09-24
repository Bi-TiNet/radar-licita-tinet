"""Small Telegram Bot API client for cloud alerts and setup checks."""

from __future__ import annotations

import requests

from .config import settings


def _call(method: str, payload: dict) -> object:
    token = settings.telegram_bot_token
    if not token:
        raise RuntimeError("Token do bot Telegram não configurado")
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload,
            timeout=35,
        )
    except requests.RequestException as exc:
        # Request exception strings may include the URL (and bot token).
        raise RuntimeError(f"Falha de conexão com Telegram ({type(exc).__name__})") from None
    try:
        body = response.json()
    except ValueError:
        raise RuntimeError(f"Telegram retornou HTTP {response.status_code} sem JSON") from None
    if not isinstance(body, dict) or not response.ok or not body.get("ok"):
        # Do not include request URLs or response bodies in public Actions logs.
        raise RuntimeError(f"Telegram recusou a chamada {method} (HTTP {response.status_code})")
    return body.get("result")


def send_message(chat_id: str, message: str) -> None:
    if not message or len(message) > 4096:
        raise RuntimeError("Mensagem Telegram vazia ou longa demais")
    _call("sendMessage", {"chat_id": chat_id, "text": message, "disable_web_page_preview": True})


def recent_chat_ids() -> list[tuple[str, str]]:
    updates = _call("getUpdates", {"limit": 100, "timeout": 0})
    if not isinstance(updates, list):
        raise RuntimeError("Telegram não retornou uma lista de conversas")
    chats = set()
    for update in updates:
        if not isinstance(update, dict):
            continue
        event = update.get("message") or update.get("my_chat_member") or {}
        if not isinstance(event, dict):
            continue
        chat = event.get("chat") or {}
        if not isinstance(chat, dict):
            continue
        if chat.get("id") is not None:
            chats.add((str(chat["id"]), str(chat.get("type") or "unknown")))
    return sorted(chats)
