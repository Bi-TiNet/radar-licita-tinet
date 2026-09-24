"""Manually triggered SMTP check for the two configured email recipients."""

from __future__ import annotations

from .cloud_sync import enabled_channels, recipients, validate_alert_config
from .notifications import send_email


def main() -> None:
    if enabled_channels() != {"email"}:
        raise RuntimeError("O teste de e-mail requer somente o canal email")
    validate_alert_config()
    addresses = sorted(address for channel, address in recipients() if channel == "email")
    item = {"municipality": "Radar Licita", "score": 0}
    message = (
        "Este é um teste do Radar Licita Ti.Net.\n\n"
        "Não representa uma nova licitação e não exige nenhuma ação."
    )
    for address in addresses:
        result = send_email(
            item,
            message,
            0,
            recipients=[address],
            subject="TESTE DE ENVIO — Radar Licita Ti.Net",
        )
        if result.get("status") != "sent":
            raise RuntimeError("O teste SMTP falhou; confira a configuração no GitHub")
    print("Servidor SMTP aceitou as duas mensagens de teste.")


if __name__ == "__main__":
    main()
