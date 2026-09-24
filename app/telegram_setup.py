"""Send each recipient their own private chat ID after they start the bot."""

from __future__ import annotations

from .telegram_api import recent_chat_ids, send_message


def main() -> None:
    chats = sorted(chat_id for chat_id, kind in recent_chat_ids() if kind == "private")
    if not chats:
        print("Nenhuma conversa privada encontrada. As duas pessoas precisam abrir o bot e enviar /start.")
        return
    if len(chats) != 2:
        raise RuntimeError("Inicie o bot em exatamente duas conversas privadas antes de descobrir os IDs")
    for chat_id in chats:
        send_message(chat_id, f"Radar Licita Ti.Net: seu ID de conversa privada é {chat_id}.")
    print("Os dois IDs foram enviados separadamente pelo bot. Nenhum ID foi exibido neste log.")


if __name__ == "__main__":
    main()
