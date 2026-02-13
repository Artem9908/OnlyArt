"""
Извлечение стиля из референсного постера (размер, палитра) для генерации в том же стиле.
"""
import logging
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# Максимальная сторона постера (чтобы не создавать гигантские файлы)
MAX_SIDE = 2000
MIN_SIDE = 600


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _sample_colors(img: Image.Image, n: int = 50) -> list[tuple[int, int, int]]:
    """Возвращает список RGB из равномерно распределённых пикселей (без белого/очень светлого)."""
    w, h = img.size
    img = img.convert("RGB")
    step = max(1, (w * h) // (n + 1))
    pixels = []
    for i in range(n):
        pos = (i * step) % (w * h)
        x, y = pos % w, pos // w
        r, g, b = img.getpixel((x, y))
        # Пропускаем почти белый (фон текста/бумаги)
        if r + g + b < 240 * 3:
            pixels.append((r, g, b))
    return pixels if pixels else [(10, 10, 10)]


def get_dominant_color(pixels: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    """Условно «доминантный» цвет — медиана по каналам (устойчивее к выбросам)."""
    if not pixels:
        return (10, 10, 10)
    n = len(pixels)
    r = sorted(p[0] for p in pixels)[n // 2]
    g = sorted(p[1] for p in pixels)[n // 2]
    b = sorted(p[2] for p in pixels)[n // 2]
    return (r, g, b)


def get_accent_color(pixels: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    """Акцентный цвет: самый насыщенный (max saturation) среди тёмных пикселей."""
    def sat(r, g, b):
        mx, mn = max(r, g, b), min(r, g, b)
        return (mx - mn) / (mx + 1e-6)
    dark = [p for p in pixels if sum(p) < 180 * 3 and max(p) - min(p) > 20]
    if not dark:
        return (230, 46, 30)  # красный по умолчанию
    return max(dark, key=lambda p: sat(*p))


def load_reference_style(reference_path: Path) -> dict:
    """
    Загружает изображение референса и возвращает словарь:
    width, height (в разумных пределах), color_bg, color_accent, color_main, color_muted (hex).
    """
    img = Image.open(reference_path).convert("RGB")
    w, h = img.size
    # Сохраняем пропорции, ограничиваем по длинной стороне
    if max(w, h) > MAX_SIDE:
        scale = MAX_SIDE / max(w, h)
        w, h = int(w * scale), int(h * scale)
        img = img.resize((w, h), Image.Resampling.LANCZOS)
    elif min(w, h) < MIN_SIDE:
        scale = MIN_SIDE / min(w, h)
        w, h = int(w * scale), int(h * scale)
        img = img.resize((w, h), Image.Resampling.LANCZOS)
    pixels = _sample_colors(img)
    dominant = get_dominant_color(pixels)
    accent = get_accent_color(pixels)
    return {
        "width": w,
        "height": h,
        "color_bg": _rgb_to_hex(*dominant),
        "color_accent": _rgb_to_hex(*accent),
        "color_main": "#ffffff",
        "color_muted": "#888888",
    }
