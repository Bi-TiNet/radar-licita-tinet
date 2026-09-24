"""Send each recipient their own private chat ID after they start the bot."""

from __future__ import annotations

from .telegram_api import recent_chat_ids, send_message


def main() -> None:
    chats = sorted({chat_id for chat_id, kind in recent_chat_ids() if kind == "private"})
    if not chats:
        raise RuntimeError("Nenhuma conversa privada encontrada. Abra o bot criado e envie /start em cada conta.")
    for chat_id in chats:
        send_message(chat_id, f"Radar Licita Ti.Net: seu ID de conversa privada é {chat_id}.")
    print(f"IDs enviados em privado para {len(chats)} conversa(s). Nenhum ID foi exibido neste log.")
    if len(chats) < 2:
        print("Ainda falta a segunda pessoa iniciar o bot e executar novamente a descoberta.")
    elif len(chats) > 2:
        print("Há mais de duas conversas: confirme quais são os dois destinatários antes de salvar os IDs.")


if __name__ == "__main__":
    main()
