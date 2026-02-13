"""
Парсер automobile-catalog.com: марки, модели, характеристики, фото.

Загрузка страниц — через браузер (Playwright), поскольку сайт
блокирует прямые HTTP-запросы (403).
"""
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .config import (
    CATALOG_BASE_URL,
    REQUEST_DELAY_SEC,
    REQUEST_RETRIES,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

SESSION_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# ─── Модель данных ────────────────────────────────────────

@dataclass
class CarSpecs:
    """Характеристики автомобиля + URL фото."""
    make: str
    model: str
    full_name: str
    specs: dict = field(default_factory=dict)
    image_url: Optional[str] = None


# ─── CSS/HTML мусор ───────────────────────────────────────

_CSS_NOISE_PATTERNS = frozenset({
    "margin", "padding", "display", "font-", "color:", "border",
    "position", "background", "text-align", "overflow", "line-height",
    "z-index", "opacity", "visibility", "cursor", "transform",
    "transition", "animation", "flex", "grid", "outline",
    "list-style", "vertical-align", "white-space", "word-",
    "letter-spacing", "text-decoration", "text-transform", "box-",
    "float", "clear", "appearance",
    "{", "}", ";", "!important", "::", "@media", "@font", "url(",
    ".h1", ".h2", ".h3", ".h4", "rem;", "rem}", "em;", "px;", "px}",
    "rgba", "rgb(", "hsl", "var(--",
    "cloudflare", "javascript", "stylesheet", "recaptcha",
    "http://", "https://", ".css", ".js", ".php",
    "cookie", "captcha", "noscript", "doctype",
})


def _is_noise(text: str) -> bool:
    """True если текст похож на CSS/HTML/JS, а не на характеристику авто."""
    t = text.lower().strip()
    if not t or len(t) > 150:
        return True
    return any(p in t for p in _CSS_NOISE_PATTERNS)


# ─── HTTP ─────────────────────────────────────────────────

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(SESSION_HEADERS)
    s.timeout = REQUEST_TIMEOUT
    return s


def _get_url(session: requests.Session, url: str) -> Optional[str]:
    """Загрузка страницы: сначала requests, при 403/ошибке -- через браузер."""
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            if attempt > 1:
                time.sleep(REQUEST_DELAY_SEC)
            r = session.get(url)
            if r.status_code == 403:
                logger.info("403 -> загрузка через Playwright...")
                return _fetch_via_browser(url)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            logger.warning("Request %s attempt %s: %s", url, attempt, e)
    logger.info("Fallback -> Playwright...")
    return _fetch_via_browser(url)


def _fetch_via_browser(url: str) -> Optional[str]:
    from .browser_fetcher import fetch_html_with_browser
    return fetch_html_with_browser(url, visit_home_first=True)


# ─── URL-помощники ────────────────────────────────────────

def _normalize_make(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def get_make_url(make: str) -> str:
    normalized = _normalize_make(make)
    return f"{CATALOG_BASE_URL.rstrip('/')}/make/{normalized}/"


def get_search_url(query: str) -> str:
    q = quote_plus(query.strip())
    return f"{CATALOG_BASE_URL.rstrip('/')}/search.php?q={q}"


# ─── Известные рабочие URL автомобилей ────────────────────

KNOWN_CAR_URLS: dict[tuple[str, str], str] = {
    ("audi", "tt rs"): "https://www.automobile-catalog.com/car/2018/2470640/audi_tt_rs_coupe_s-tronic.html",
    ("audi", "tt"): "https://www.automobile-catalog.com/car/2018/2470640/audi_tt_rs_coupe_s-tronic.html",
    ("bmw", "m3"): "https://www.automobile-catalog.com/car/2025/3317015/bmw_m3_competition_m_xdrive.html",
    ("porsche", "911 turbo"): "https://www.automobile-catalog.com/car/2018/2871365/porsche_911_turbo_coupe.html",
    ("porsche", "911 turbo s"): "https://www.automobile-catalog.com/car/2018/2871365/porsche_911_turbo_coupe.html",
    ("porsche", "911"): "https://www.automobile-catalog.com/car/2018/2871365/porsche_911_turbo_coupe.html",
    ("mercedes-benz", "amg gt"): "https://www.automobile-catalog.com/car/2020/2874950/mercedes-amg_gt_c_roadster.html",
    ("mercedes", "amg gt"): "https://www.automobile-catalog.com/car/2020/2874950/mercedes-amg_gt_c_roadster.html",
    ("nissan", "gt-r"): "https://www.automobile-catalog.com/car/2016/2183225/nissan_gt-r_nismo.html",
    ("nissan", "gt-r nismo"): "https://www.automobile-catalog.com/car/2016/2183225/nissan_gt-r_nismo.html",
}


# ─── Извлечение фотографии авто ──────────────────────────

_SKIP_IMAGE_PATTERNS = frozenset({
    "logo", "icon", "banner", "advert", "button", "flag", "pixel",
    "tracking", "spacer", "blank", "avatar", "favicon", "sprite",
    "social", "facebook", "twitter", "instagram", "youtube",
    "cloudflare", "captcha", "recaptcha", "widget",
})


def _extract_car_image_url(
    soup: BeautifulSoup, base_url: str, make: str, model: str,
) -> Optional[str]:
    """
    Извлекает URL основного фото автомобиля со страницы.
    Оценивает каждое <img> по релевантности и возвращает лучший вариант.
    """
    make_lower = make.lower()
    model_lower = model.lower().replace(" ", "")
    candidates: list[tuple[int, str]] = []

    for img in soup.find_all("img", src=True):
        src = (img.get("src") or "").strip()
        if not src:
            continue

        src_lower = src.lower()
        alt = (img.get("alt") or "").lower()
        full_url = urljoin(base_url, src)

        # Пропускаем не-изображения
        if not any(ext in src_lower for ext in (".jpg", ".jpeg", ".png", ".webp")):
            continue

        # Пропускаем иконки/баннеры/трекеры
        if any(skip in src_lower for skip in _SKIP_IMAGE_PATTERNS):
            continue
        if any(skip in alt for skip in _SKIP_IMAGE_PATTERNS):
            continue

        # Пропускаем маленькие изображения
        width = img.get("width", "")
        height = img.get("height", "")
        if width and width.isdigit() and int(width) < 80:
            continue
        if height and height.isdigit() and int(height) < 80:
            continue

        # Оценка релевантности
        score = 0

        # Alt-текст содержит марку/модель
        if make_lower in alt:
            score += 10
        if model_lower in alt.replace(" ", ""):
            score += 10

        # URL содержит марку/модель
        if make_lower in src_lower:
            score += 5
        if model_lower in src_lower.replace("_", "").replace("-", ""):
            score += 5

        # URL содержит пути к фотографиям
        if any(p in src_lower for p in ("/pic/", "/img/", "/photo/", "/car/", "/image/")):
            score += 5

        # Размер: предпочитаем крупные
        if width and width.isdigit() and int(width) >= 300:
            score += 3
        if height and height.isdigit() and int(height) >= 200:
            score += 3

        # Alt-текст с авто-ключевыми словами
        if any(kw in alt for kw in ("car", "auto", "photo", "vehicle", "coupe", "sedan")):
            score += 3

        if score > 0:
            candidates.append((score, full_url))

    if not candidates:
        return None

    candidates.sort(key=lambda x: -x[0])
    best_score, best_url = candidates[0]
    logger.debug("Car image candidate: score=%d, url=%s", best_score, best_url)
    return best_url


# ─── Парсинг HTML ─────────────────────────────────────────

def _clean_soup(soup: BeautifulSoup) -> None:
    """Удаляет style / script / noscript / link теги ДО извлечения текста."""
    for tag in soup.find_all(["style", "script", "noscript", "link", "meta"]):
        tag.decompose()


def get_models_from_make_page(html: str, base_url: str, make: str) -> list[dict]:
    """Извлекает ссылки на модели/машины со страницы марки."""
    soup = BeautifulSoup(html, "lxml")
    _clean_soup(soup)
    models: list[dict] = []
    seen: set[str] = set()
    make_lower = _normalize_make(make)

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        text = (a.get_text() or "").strip()
        if not text or len(text) > 150:
            continue
        full = urljoin(base_url, href)
        if full in seen:
            continue
        path = urlparse(full).path.lower()
        if "/car/" in path and ".html" in path:
            seen.add(full)
            models.append({"url": full, "name": text})
            continue
        if f"/make/{make_lower}/" in path:
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 3:
                seen.add(full)
                models.append({"url": full, "name": text})

    by_name: dict[str, dict] = {}
    for m in models:
        name = (m["name"] or "").strip()
        if len(name) >= 2 and name not in by_name:
            by_name[name] = m
    return list(by_name.values())[:100]


def get_car_links_from_search_page(html: str, base_url: str) -> list[dict]:
    """Из страницы поиска -- ссылки на /car/....html."""
    soup = BeautifulSoup(html, "lxml")
    _clean_soup(soup)
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        text = (a.get_text() or "").strip()
        full = urljoin(base_url, href)
        path = urlparse(full).path.lower()
        if "/car/" not in path or ".html" not in path or full in seen:
            continue
        seen.add(full)
        fallback_name = path.split("/")[-1].replace(".html", "").replace("_", " ")
        out.append({"url": full, "name": text or fallback_name})
    return out


def parse_specs_from_car_page(html: str, make: str, model: str, page_url: str) -> CarSpecs:
    """
    Парсит страницу автомобиля: таблицы th/td, списки dt/dd, фото.
    Предварительно удаляет все style/script теги для чистого извлечения.
    """
    soup = BeautifulSoup(html, "lxml")

    # Извлекаем URL фото ДО очистки (img теги не мешают)
    image_url = _extract_car_image_url(soup, page_url, make, model)

    _clean_soup(soup)  # убираем CSS/JS ДО обхода текста

    specs: dict[str, str] = {}

    def add(k: str, v: str) -> None:
        k = (k or "").strip().replace("\n", " ").strip()
        v = (v or "").strip().replace("\n", " ").strip()
        if k and v and not _is_noise(k) and not _is_noise(v):
            specs[k] = v

    # Таблицы
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                add(cells[0].get_text(), cells[1].get_text())
            elif len(cells) == 1:
                t = cells[0].get_text().strip()
                if ":" in t:
                    key, _, val = t.partition(":")
                    add(key, val)

    # Списки определений (dt/dd)
    for dl in soup.find_all("dl"):
        dts, dds = dl.find_all("dt"), dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            add(dt.get_text(), dd.get_text())

    # Пары label/value в div/span/p
    for tag in soup.find_all(
        ["div", "span", "p"],
        class_=re.compile(r"spec|param|label|data|value", re.I),
    ):
        label = tag.get_text().strip()
        nxt = tag.find_next_sibling()
        if nxt and label and len(label) < 100:
            add(label, nxt.get_text())

    # Название автомобиля
    full_name = f"{make} {model}"
    title = soup.find("title")
    if title and title.get_text():
        t = title.get_text().strip()
        if make.lower() in t.lower() and len(t) < 200:
            full_name = t.split("|")[0].split("-")[0].strip() or full_name

    return CarSpecs(
        make=make, model=model, full_name=full_name,
        specs=specs, image_url=image_url,
    )


# ─── Публичное API ────────────────────────────────────────

def fetch_models_for_make(make: str) -> list[dict]:
    """Загружает страницу марки и возвращает список моделей [{url, name}]."""
    url = get_make_url(make)
    html = _fetch_via_browser(url)
    if not html:
        logger.warning("He удалось загрузить страницу марки: %s", url)
        return []
    time.sleep(REQUEST_DELAY_SEC)
    return get_models_from_make_page(html, url, make)


def fetch_car_links_via_search(make: str, model: str) -> list[dict]:
    """Поиск по запросу 'Make Model' -> ссылки на /car/....html."""
    query = f"{make} {model}".strip()
    url = get_search_url(query)
    html = _fetch_via_browser(url)
    if not html:
        return []
    time.sleep(REQUEST_DELAY_SEC)
    return get_car_links_from_search_page(html, url)


def fetch_car_specs(make: str, model: str, car_page_url: str) -> Optional[CarSpecs]:
    """Загружает страницу автомобиля и парсит характеристики + фото."""
    html = _fetch_via_browser(car_page_url)
    if not html:
        session = _session()
        html = _get_url(session, car_page_url)
    if not html:
        return None
    return parse_specs_from_car_page(html, make, model, car_page_url)


def find_model_by_name(make: str, model_query: str) -> Optional[dict]:
    """
    Ищет модель: страница марки -> поиск по сайту -> KNOWN_CAR_URLS.
    Возвращает {url, name} или None.
    """
    make_lower = _normalize_make(make)
    model_lower = (model_query or "").strip().lower()

    # 1. Страница марки
    models = fetch_models_for_make(make)
    if not models and model_query:
        logger.info("По странице марки моделей не найдено -> поиск по сайту...")
        models = fetch_car_links_via_search(make, model_query)

    if models:
        for m in models:
            name = (m.get("name") or "").lower()
            if model_lower and (
                model_lower in name
                or model_lower.replace(" ", "") in name.replace(" ", "")
            ):
                return m
        return models[0]

    # 2. Известные URL
    if model_lower and (make_lower, model_lower) in KNOWN_CAR_URLS:
        url = KNOWN_CAR_URLS[(make_lower, model_lower)]
        logger.info("Используем известный URL каталога: %s", url)
        return {"url": url, "name": model_query or "Unknown"}

    for (mk, md), url in KNOWN_CAR_URLS.items():
        if mk == make_lower and (not model_lower or md in model_lower or model_lower in md):
            logger.info("Используем известный URL каталога: %s", url)
            return {"url": url, "name": model_query or md}

    return None
