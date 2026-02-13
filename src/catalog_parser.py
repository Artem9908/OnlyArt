"""
Парсер automobile-catalog.com: марки, модели, характеристики.
Устойчив к таймаутам и разной вёрстке страниц.
"""
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

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


@dataclass
class CarSpecs:
    """Характеристики автомобиля."""
    make: str
    model: str
    full_name: str
    specs: dict = field(default_factory=dict)
    raw_html_snippet: Optional[str] = None


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(SESSION_HEADERS)
    s.timeout = REQUEST_TIMEOUT
    return s


def _get_url(session: requests.Session, url: str) -> Optional[str]:
    """Загрузка страницы с повторами и задержкой."""
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            if attempt > 1:
                time.sleep(REQUEST_DELAY_SEC)
            r = session.get(url)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            logger.warning("Request %s attempt %s: %s", url, attempt, e)
    return None


def _normalize_make(name: str) -> str:
    """Нормализация имени марки для URL (например Audi -> audi)."""
    return name.strip().lower().replace(" ", "_")


def _normalize_model(name: str) -> str:
    """Нормализация имени модели."""
    return name.strip()


def get_make_url(make: str) -> str:
    """Возвращает предполагаемый URL страницы марки."""
    normalized = _normalize_make(make)
    # automobile-catalog.com использует структуру /make/audi/ или /manufacturer/audi
    return f"{CATALOG_BASE_URL.rstrip('/')}/make/{normalized}/"


def get_models_from_make_page(html: str, base_url: str, make: str) -> list[dict]:
    """
    Извлекает ссылки на модели с страницы марки.
    Ищет ссылки на страницы автомобилей (типично содержат год или модель в пути).
    """
    soup = BeautifulSoup(html, "lxml")
    models = []
    seen_hrefs = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        text = (a.get_text() or "").strip()
        if not text or len(text) > 120:
            continue
        full_url = urljoin(base_url, href)
        path = urlparse(full_url).path.lower()
        # Пропускаем якоря, главную, ту же страницу марки
        if href.startswith("#") or "make/" not in path and path.count("/") < 2:
            continue
        if full_url in seen_hrefs:
            continue
        # Ссылки на машины часто содержат год или модель
        if re.search(r"(\d{4}|model|car|tt|a3|a4)", path) or (
            len(text) >= 2 and text[0].isalnum()
        ):
            seen_hrefs.add(full_url)
            models.append({"url": full_url, "name": text})

    # Дополнительно: ищем таблицы/списки с названиями моделей
    for table in soup.find_all("table"):
        for a in table.find_all("a", href=True):
            href = a.get("href", "").strip()
            text = (a.get_text() or "").strip()
            if not text or len(text) > 100:
                continue
            full_url = urljoin(base_url, href)
            if full_url in seen_hrefs:
                continue
            if "/make/" in urlparse(full_url).path:
                seen_hrefs.add(full_url)
                models.append({"url": full_url, "name": text})

    return models[:80]  # разумный лимит


def parse_specs_from_car_page(html: str, make: str, model: str, page_url: str) -> CarSpecs:
    """
    Парсит страницу автомобиля: извлекает таблицы/списки характеристик.
    Поддерживает таблицы (th/td), списки (dt/dd), div с подписями.
    """
    soup = BeautifulSoup(html, "lxml")
    specs = {}

    def add_spec(key: str, value: str):
        k = (key or "").strip().replace("\n", " ").strip()
        v = (value or "").strip().replace("\n", " ").strip()
        if k and v:
            specs[k] = v

    # Таблицы: первая колонка — название, вторая — значение
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                add_spec(cells[0].get_text(), cells[1].get_text())
            elif len(cells) == 1:
                text = cells[0].get_text().strip()
                if ":" in text:
                    k, _, v = text.partition(":")
                    add_spec(k, v)

    # Списки dt/dd
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            add_spec(dt.get_text(), dd.get_text())

    # Div'ы с классами/лейблами (часто data-spec или label)
    for div in soup.find_all(["div", "span"], class_=re.compile(r"spec|param|label|name", re.I)):
        label = div.get_text().strip()
        next_el = div.find_next_sibling()
        if next_el and label and len(label) < 80:
            add_spec(label, next_el.get_text())

    # Заголовок страницы как уточнение полного имени
    full_name = f"{make} {model}"
    title = soup.find("title")
    if title and title.get_text():
        t = title.get_text().strip()
        if make.lower() in t.lower() and len(t) < 150:
            full_name = t.split("|")[0].split("-")[0].strip() or full_name

    return CarSpecs(make=make, model=model, full_name=full_name, specs=specs)


def fetch_models_for_make(make: str) -> list[dict]:
    """
    Загружает страницу марки и возвращает список моделей (url, name).
    При ошибке сети возвращает пустой список.
    """
    url = get_make_url(make)
    session = _session()
    html = _get_url(session, url)
    if not html:
        logger.warning("Не удалось загрузить страницу марки: %s", url)
        return []
    time.sleep(REQUEST_DELAY_SEC)
    return get_models_from_make_page(html, url, make)


def fetch_car_specs(make: str, model: str, car_page_url: str) -> Optional[CarSpecs]:
    """
    Загружает страницу автомобиля и возвращает CarSpecs.
    """
    session = _session()
    html = _get_url(session, car_page_url)
    if not html:
        return None
    return parse_specs_from_car_page(html, make, model, car_page_url)


def find_model_by_name(make: str, model_query: str) -> Optional[dict]:
    """
    Ищет среди моделей марки ту, что совпадает с model_query (например 'TT RS').
    Возвращает первый подходящий элемент из списка {url, name}.
    """
    models = fetch_models_for_make(make)
    if not models:
        return None
    query = model_query.strip().lower()
    for m in models:
        if query in m["name"].lower():
            return m
    # Точное совпадение по нормализованному имени
    for m in models:
        if _normalize_model(model_query).lower() == m["name"].strip().lower():
            return m
    return models[0] if models else None
