"""
Загрузка страниц automobile-catalog.com через браузер (Playwright).
Сайт отдаёт контент при обращении как обычный браузер; при прямых HTTP-запросах часто 403.
Стратегия: одна сессия — визит главной (cookies/контекст), затем целевая страница.
"""
import logging
import time
from typing import Optional

from .config import CATALOG_BASE_URL, REQUEST_DELAY_SEC

logger = logging.getLogger(__name__)

_playwright_available: Optional[bool] = None

# Таймаут загрузки страницы (сайт может грузиться медленно)
PAGE_LOAD_TIMEOUT_MS = 45000
# Ожидание после загрузки (для JS/динамики)
WAIT_AFTER_LOAD_SEC = 3
# Ожидание после главной перед переходом на целевую
WAIT_AFTER_HOME_SEC = 2

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _playwright_ok() -> bool:
    global _playwright_available
    if _playwright_available is not None:
        return _playwright_available
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        _playwright_available = True
    except ImportError:
        logger.debug(
            "Playwright не установлен. Установите: pip install playwright && playwright install chromium"
        )
        _playwright_available = False
    return _playwright_available


def fetch_html_with_browser(
    url: str,
    visit_home_first: bool = True,
    delay_after: float = WAIT_AFTER_LOAD_SEC,
) -> Optional[str]:
    """
    Открывает URL в headless Chromium и возвращает HTML.
    Если visit_home_first — сначала загружается главная страница каталога (получение cookies/контекста).
    """
    if not _playwright_ok():
        return None
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=BROWSER_USER_AGENT)
                page.set_default_timeout(PAGE_LOAD_TIMEOUT_MS)

                if visit_home_first and url.rstrip("/") != CATALOG_BASE_URL.rstrip("/"):
                    logger.debug("Загрузка главной страницы каталога...")
                    page.goto(CATALOG_BASE_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
                    time.sleep(WAIT_AFTER_HOME_SEC)

                page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                time.sleep(delay_after)
                html = page.content()
                return html
            finally:
                browser.close()
    except Exception as e:
        logger.warning("Playwright: не удалось загрузить %s: %s", url, e)
    return None
