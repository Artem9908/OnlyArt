"""
Поиск фотографий автомобилей.

Стратегия:
  1. Фото с сайта automobile-catalog.com (если парсер нашёл URL)
  2. Поиск через Bing Images (без API ключа)
  3. Генерация через OpenAI DALL-E (если OPENAI_API_KEY задан)
  4. None (постер без фото)
"""
import logging
import re
from io import BytesIO
from typing import Optional
from urllib.parse import quote_plus

import requests
from PIL import Image

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Минимальные размеры (отсекаем иконки/превью)
_MIN_W = 300
_MIN_H = 180


def download_image(url: str) -> Optional[Image.Image]:
    """Скачивает изображение по URL, возвращает PIL Image или None."""
    try:
        r = requests.get(url, timeout=15, headers=_HEADERS, stream=True)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGB")
        if img.width < _MIN_W or img.height < _MIN_H:
            return None
        return img
    except Exception as e:
        logger.debug("Cannot download %s: %s", url[:80], e)
        return None


# ─── 1. Фото с сайта (URL из парсера) ────────────────────

def from_catalog_url(image_url: Optional[str]) -> Optional[Image.Image]:
    """Скачать фото по URL, извлечённому парсером."""
    if not image_url:
        return None
    img = download_image(image_url)
    if img:
        logger.info("Car image from catalog: %dx%d", img.width, img.height)
    return img


# ─── 2. Поиск через Bing Images ──────────────────────────

def _extract_bing_image_urls(html: str) -> list[str]:
    """Извлекает URL изображений из HTML страницы Bing Images."""
    urls: list[str] = []

    # Bing хранит полные URL в атрибуте murl
    murl_pattern = re.compile(r'murl[&quot;:"\s]+?(https?://[^"&\s]+\.(?:jpg|jpeg|png|webp))', re.I)
    for m in murl_pattern.finditer(html):
        url = m.group(1)
        if url not in urls:
            urls.append(url)

    # Запасной: src из img тегов
    if not urls:
        src_pattern = re.compile(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', re.I)
        for m in src_pattern.finditer(html):
            url = m.group(1)
            if "bing" not in url.lower() and "microsoft" not in url.lower():
                if url not in urls:
                    urls.append(url)

    return urls[:10]


def from_bing_search(make: str, model: str) -> Optional[Image.Image]:
    """Ищет фото авто через Bing Images (без API ключа)."""
    query = f"{make} {model} car photo HD"
    search_url = f"https://www.bing.com/images/search?q={quote_plus(query)}&first=1"

    try:
        r = requests.get(search_url, timeout=15, headers=_HEADERS)
        r.raise_for_status()
        urls = _extract_bing_image_urls(r.text)
        logger.debug("Bing image search: found %d candidates", len(urls))

        for url in urls:
            img = download_image(url)
            if img and img.width >= _MIN_W:
                logger.info("Car image from Bing: %dx%d", img.width, img.height)
                return img
    except Exception as e:
        logger.warning("Bing image search failed: %s", e)

    return None


# ─── 3. Поиск через DuckDuckGo ───────────────────────────

def from_duckduckgo_search(make: str, model: str) -> Optional[Image.Image]:
    """Поиск фото через DuckDuckGo (запасной вариант)."""
    query = f"{make} {model} car"
    try:
        # Получаем vqd token
        token_url = f"https://duckduckgo.com/?q={quote_plus(query)}&iax=images&ia=images"
        r = requests.get(token_url, timeout=10, headers=_HEADERS)
        vqd_match = re.search(r"vqd=['\"]([^'\"]+)['\"]", r.text)
        if not vqd_match:
            return None
        vqd = vqd_match.group(1)

        # Запрос изображений
        api_url = (
            f"https://duckduckgo.com/i.js?l=us-en&o=json&q={quote_plus(query)}"
            f"&vqd={vqd}&f=,,,,,&p=1"
        )
        r2 = requests.get(api_url, timeout=10, headers=_HEADERS)
        data = r2.json()
        results = data.get("results", [])

        for result in results[:5]:
            img_url = result.get("image")
            if img_url:
                img = download_image(img_url)
                if img and img.width >= _MIN_W:
                    logger.info("Car image from DuckDuckGo: %dx%d", img.width, img.height)
                    return img
    except Exception as e:
        logger.debug("DuckDuckGo search failed: %s", e)

    return None


# ─── 4. Генерация через OpenAI DALL-E ────────────────────

def from_openai_dalle(make: str, model: str) -> Optional[Image.Image]:
    """Генерация фото через DALL-E (если OPENAI_API_KEY задан)."""
    try:
        from .config import OPENAI_API_KEY
        if not OPENAI_API_KEY:
            return None

        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        prompt = (
            f"Professional automotive studio photograph of a {make} {model}, "
            f"side 3/4 view, dark moody background, dramatic studio lighting, "
            f"high-end car photography, ultra detailed, 8k quality"
        )
        logger.info("Generating car image with DALL-E for %s %s...", make, model)
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1792x1024",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        img = download_image(image_url)
        if img:
            logger.info("AI-generated image: %dx%d", img.width, img.height)
        return img
    except ImportError:
        logger.debug("openai package not installed")
        return None
    except Exception as e:
        logger.warning("DALL-E generation failed: %s", e)
        return None


# ─── Главная функция ─────────────────────────────────────

def find_car_image(
    make: str,
    model: str,
    catalog_image_url: Optional[str] = None,
) -> Optional[Image.Image]:
    """
    Последовательно пробует все стратегии:
    1. Фото с сайта каталога
    2. Bing Images
    3. DuckDuckGo Images
    4. OpenAI DALL-E
    """
    # 1. С сайта каталога
    img = from_catalog_url(catalog_image_url)
    if img:
        return img

    # 2. Bing Images
    img = from_bing_search(make, model)
    if img:
        return img

    # 3. DuckDuckGo
    img = from_duckduckgo_search(make, model)
    if img:
        return img

    # 4. AI
    img = from_openai_dalle(make, model)
    if img:
        return img

    logger.warning("No car image found for %s %s", make, model)
    return None
