"""Send an explicitly marked test message to each of two private chats."""

from __future__ import annotations

from .cloud_sync import recipients, validate_alert_config
from .telegram_api import send_message


def main() -> None:
    validate_alert_config()
    chats = sorted(chat_id for channel, chat_id in recipients() if channel == "telegram")
    if len(chats) != 2:
        raise RuntimeError("O teste Telegram requer exatamente dois chats individuais")
    message = (
        "TESTE DE ENVIO — Radar Licita Ti.Net\n\n"
        "Esta mensagem não representa uma nova licitação e não exige nenhuma ação."
    )
    for chat_id in chats:
        send_message(chat_id, message)
    print("Telegram aceitou as duas mensagens individuais de teste.")


if __name__ == "__main__":
    main()
