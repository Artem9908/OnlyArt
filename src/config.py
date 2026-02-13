"""
Конфигурация приложения. Переменные окружения имеют приоритет.
"""
import os
from pathlib import Path

# Базовый URL каталога
CATALOG_BASE_URL = os.getenv("AUTO_CATALOG_BASE", "https://www.automobile-catalog.com")

# Таймауты и повторные запросы
REQUEST_TIMEOUT = int(os.getenv("AUTO_REQUEST_TIMEOUT", "15"))
REQUEST_RETRIES = int(os.getenv("AUTO_REQUEST_RETRIES", "3"))
REQUEST_DELAY_SEC = float(os.getenv("AUTO_REQUEST_DELAY", "1.0"))

# User-Agent для вежливого парсинга
USER_AGENT = os.getenv(
    "AUTO_USER_AGENT",
    "AutoPosters/1.0 (Educational; +https://github.com/Artem9908)",
)

# Папка вывода по умолчанию
OUTPUT_DIR = Path(os.getenv("AUTO_OUTPUT_DIR", "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Референс постера (прикреплённый к ТЗ пример AUDI TT RS)
# Положите reference.png / reference.jpg в корень проекта
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_IMAGE: Path | None = None
for _name in ("reference.png", "reference.jpg", "reference.jpeg"):
    _p = PROJECT_ROOT / _name
    if _p.exists():
        REFERENCE_IMAGE = _p
        break

# API-ключ OpenAI (опционально, для генерации фото авто через DALL-E)
# Если ключ не задан -- используется фото с сайта или постер без фото
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
