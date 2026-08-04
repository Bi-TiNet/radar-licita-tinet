from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def load_dotenv(path: Path = BASE_DIR / ".env") -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Radar Licita ISP")
    host: str = os.getenv("APP_HOST", "0.0.0.0")
    port: int = int(os.getenv("APP_PORT", "8080"))
    sync_interval_minutes: int = int(os.getenv("SYNC_INTERVAL_MINUTES", "180"))
    lookback_days: int = int(os.getenv("LOOKBACK_DAYS", "45"))
    min_score_notify: int = int(os.getenv("MIN_SCORE_NOTIFY", "45"))
    db_path: Path = DATA_DIR / "radar_licitacoes.db"
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")
    email_to: str = os.getenv("EMAIL_TO", "")
    webhook_url: str = os.getenv("WEBHOOK_URL", "")
    whatsapp_numbers: str = os.getenv("WHATSAPP_NUMBERS", "")
    evolution_api_url: str = os.getenv("EVOLUTION_API_URL", "")
    evolution_instance: str = os.getenv("EVOLUTION_INSTANCE", "")
    evolution_api_key: str = os.getenv("EVOLUTION_API_KEY", "")


settings = Settings()
