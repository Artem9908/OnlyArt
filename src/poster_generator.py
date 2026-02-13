"""
Генерация постера автомобиля в стиле референса (AUDI TT RS):
тёмный фон, крупная типографика, блок ключевых характеристик.
"""
import logging
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .catalog_parser import CarSpecs

logger = logging.getLogger(__name__)

# Размер постера (портрет, как типичный референс)
POSTER_W = 1200
POSTER_H = 1600

# Цвета в стиле референса
COLOR_BG = "#0a0a0a"
COLOR_ACCENT = "#e62e1e"  # красный акцент
COLOR_MAIN = "#ffffff"
COLOR_MUTED = "#888888"

# Ключевые поля характеристик для вывода на постер (в порядке приоритета)
SPEC_KEYS_ORDER = [
    "Engine",
    "Displacement",
    "Power",
    "Torque",
    "Top speed",
    "Acceleration 0-60 mph",
    "0-60 mph",
    "0-100 km/h",
    "Drive",
    "Transmission",
    "Engine type",
    "Curb weight",
    "Length",
    "Width",
]

# Алиасы для русских/альтернативных названий
SPEC_ALIASES = {
    "двигатель": "Engine",
    "объём": "Displacement",
    "мощность": "Power",
    "крутящий момент": "Torque",
    "разгон 0-100": "0-100 km/h",
    "привод": "Drive",
    "трансмиссия": "Transmission",
    "вес": "Curb weight",
    "длина": "Length",
    "ширина": "Width",
}


def _find_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Шрифт: системный или встроенный. Fallback на default."""
    candidates = []
    if bold:
        candidates = [
            "arialbd.ttf",
            "Arial Bold.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            "arial.ttf",
            "Arial.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _normalize_spec_key(key: str) -> str:
    k = key.strip()
    for alias, canonical in SPEC_ALIASES.items():
        if alias.lower() in k.lower():
            return canonical
    return k


def _select_specs(specs: dict, max_items: int = 8) -> list[tuple[str, str]]:
    """Выбирает до max_items характеристик для постера."""
    normalized = {_normalize_spec_key(k): v for k, v in specs.items()}
    result = []
    for candidate in SPEC_KEYS_ORDER:
        for k, v in normalized.items():
            if candidate.lower() in k.lower() or k.lower() in candidate.lower():
                result.append((k, v))
                if len(result) >= max_items:
                    return result
                break
    # Добавить любые оставшиеся
    used = {r[0] for r in result}
    for k, v in normalized.items():
        if k not in used and len(result) < max_items:
            result.append((k, v))
    return result


def _draw_text_centered(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
    anchor: str = "mm",
) -> None:
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def generate_poster(specs: CarSpecs, output_path: Optional[Path] = None) -> Path:
    """
    Генерирует постер по данным CarSpecs.
    Стиль референса: тёмный фон, марка сверху, модель по центру, блок характеристик.
    """
    img = Image.new("RGB", (POSTER_W, POSTER_H), COLOR_BG)
    draw = ImageDraw.Draw(img)

    y = 120
    # Марка (мелким капсом сверху)
    make_upper = specs.make.upper()
    font_make = _find_font(42, bold=False)
    _draw_text_centered(draw, (POSTER_W // 2, y), make_upper, font_make, COLOR_MUTED)
    y += 80

    # Модель (крупно по центру)
    model_text = specs.model.upper() if specs.model else specs.full_name.upper()
    font_model = _find_font(120, bold=True)
    _draw_text_centered(draw, (POSTER_W // 2, y), model_text, font_model, COLOR_MAIN)
    y += 180

    # Линия-разделитель (акцент)
    line_y = y
    draw.line([(POSTER_W // 4, line_y), (3 * POSTER_W // 4, line_y)], fill=COLOR_ACCENT, width=3)
    y += 50

    # Блок характеристик
    selected = _select_specs(specs.specs, max_items=8)
    font_label = _find_font(28, bold=False)
    font_value = _find_font(32, bold=True)
    line_height = 52
    left_x = POSTER_W // 4
    right_x = 3 * POSTER_W // 4

    for label, value in selected:
        # Обрезаем длинные значения
        value_short = (value[: 50] + "…") if len(value) > 50 else value
        _draw_text_centered(draw, (left_x, y), label + ":", font_label, COLOR_MUTED, anchor="rm")
        _draw_text_centered(draw, (right_x, y), value_short, font_value, COLOR_MAIN, anchor="lm")
        y += line_height

    if output_path is None:
        output_path = Path("output") / f"{specs.make}_{specs.model.replace(' ', '_')}.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        output_path = output_path.with_suffix(".png")
    img.save(output_path, "PNG", optimize=True)
    logger.info("Постер сохранён: %s", output_path)
    return output_path
