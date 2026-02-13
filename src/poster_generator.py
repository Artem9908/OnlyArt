"""
Генерация постера автомобиля в стиле референса (AUDI TT RS).

Два режима макета:
  1. С фотографией авто (парсинг с сайта или AI-генерация)
  2. Только типографика (fallback)

Стиль: тёмный фон, крупная типографика, красные акценты,
угловые метки, блок характеристик.
"""
import logging
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont

from .catalog_parser import CarSpecs
from .reference_style import load_reference_style

logger = logging.getLogger(__name__)

# ─── Размеры постера ──────────────────────────────────────
POSTER_W = 1080
POSTER_H = 1350

# ─── Цветовая палитра ────────────────────────────────────
COLOR_BG = "#0a0a0a"
COLOR_ACCENT = "#c0392b"
COLOR_PRIMARY = "#ffffff"
COLOR_SECONDARY = "#999999"
COLOR_MUTED = "#444444"
COLOR_SEPARATOR = "#1a1a1a"

# ─── Приоритет характеристик ──────────────────────────────
SPEC_DISPLAY_ORDER = [
    "Engine", "Power", "Torque", "0-60 mph", "0-100 km/h",
    "Top Speed", "Drivetrain", "Transmission", "Displacement", "Curb weight",
]

SPEC_ALIASES: dict[str, str] = {
    "engine type": "Engine", "motor": "Engine",
    "max power": "Power", "maximum power": "Power", "power output": "Power",
    "max torque": "Torque", "maximum torque": "Torque",
    "maximum speed": "Top Speed", "top speed": "Top Speed", "vmax": "Top Speed",
    "gearbox": "Transmission", "gear box": "Transmission",
    "driven wheels": "Drivetrain", "drive": "Drivetrain", "drive type": "Drivetrain",
    "kerb weight": "Curb weight", "weight": "Curb weight",
    "engine displacement": "Displacement", "capacity": "Displacement",
    "acceleration 0-100": "0-100 km/h", "0-100": "0-100 km/h",
    "acceleration 0-60": "0-60 mph", "0-62 mph": "0-60 mph",
    # Russian
    "двигатель": "Engine", "мощность": "Power", "крутящий момент": "Torque",
    "максимальная скорость": "Top Speed", "привод": "Drivetrain",
    "трансмиссия": "Transmission", "объём": "Displacement", "вес": "Curb weight",
}

_CSS_NOISE = frozenset({
    "margin", "padding", "display", "font-", "color:", "border",
    "position", "background", "text-align", "overflow", "line-height",
    "z-index", "opacity", "visibility", "cursor", "transform",
    "transition", "animation", "flex", "grid", "outline",
    "list-style", "vertical-align", "white-space", "word-",
    "letter-spacing", "text-decoration", "text-transform", "box-",
    "float", "clear", "content:", "appearance",
    "{", "}", ";", "!important", "::", "@media", "@font", "url(",
    ".h1", ".h2", ".h3", ".h4", "rem;", "rem}", "em;", "px;", "px}",
    "rgba", "rgb(", "hsl", "var(--",
    "cloudflare", "javascript", "stylesheet", "recaptcha",
    "http://", "https://", ".css", ".js", ".php",
    "cookie", "captcha", "noscript",
})


def _is_noise(text: str) -> bool:
    t = text.lower().strip()
    if not t or len(t) > 120:
        return True
    return any(p in t for p in _CSS_NOISE)


# ─── Шрифты ──────────────────────────────────────────────

def _find_font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    _MAP: dict[str, list[str]] = {
        "light": [
            "C:\\Windows\\Fonts\\segoeuil.ttf",
            "C:\\Windows\\Fonts\\segoeui.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-ExtraLight.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ],
        "regular": [
            "C:\\Windows\\Fonts\\segoeui.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ],
        "semibold": [
            "C:\\Windows\\Fonts\\seguisb.ttf",
            "C:\\Windows\\Fonts\\segoeuib.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
        "bold": [
            "C:\\Windows\\Fonts\\bahnschrift.ttf",
            "C:\\Windows\\Fonts\\segoeuib.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
    }
    for path in _MAP.get(weight, _MAP["regular"]):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ─── Утилиты отрисовки ───────────────────────────────────

def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _draw_spaced_text(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
    spacing: int = 10,
) -> int:
    """Текст с letter-spacing, по центру. Возвращает ширину."""
    if not text:
        return 0
    chars = list(text)
    widths = [draw.textbbox((0, 0), ch, font=font)[2] - draw.textbbox((0, 0), ch, font=font)[0] for ch in chars]
    total = sum(widths) + spacing * max(0, len(chars) - 1)
    cx, cy = center
    x = cx - total // 2
    for i, ch in enumerate(chars):
        draw.text((x, cy), ch, font=font, fill=fill, anchor="lm")
        x += widths[i] + spacing
    return total


def _draw_corners(draw: ImageDraw.ImageDraw, w: int, h: int, color: str, s: float) -> None:
    length = int(35 * s)
    lw = max(2, int(2 * s))
    m = int(30 * s)
    for vx, vy, hx, hy, ex, ey in [
        (m, m, m + length, m, m, m + length),
        (w - m, m, w - m - length, m, w - m, m + length),
        (m, h - m, m + length, h - m, m, h - m - length),
        (w - m, h - m, w - m - length, h - m, w - m, h - m - length),
    ]:
        draw.line([(vx, vy), (hx, hy)], fill=color, width=lw)
        draw.line([(vx, vy), (ex, ey)], fill=color, width=lw)


# ─── Отбор характеристик ─────────────────────────────────

def _normalize_key(key: str) -> str:
    k = key.strip()
    kl = k.lower()
    for alias, canonical in SPEC_ALIASES.items():
        if alias in kl:
            return canonical
    return k


def _select_specs(raw: dict, max_items: int = 7) -> list[tuple[str, str]]:
    clean: dict[str, str] = {}
    for k, v in raw.items():
        if _is_noise(k) or _is_noise(v):
            continue
        key = _normalize_key(k)
        val = v.strip()
        if 2 <= len(key) <= 50 and 1 <= len(val) <= 100:
            clean[key] = val

    result: list[tuple[str, str]] = []
    used: set[str] = set()
    for target in SPEC_DISPLAY_ORDER:
        tl = target.lower()
        for k, v in clean.items():
            if k not in used and (tl in k.lower() or k.lower() in tl):
                result.append((target, v))
                used.add(k)
                break
        if len(result) >= max_items:
            return result
    for k, v in clean.items():
        if k not in used and len(result) < max_items:
            result.append((k, v))
            used.add(k)
    return result


# ─── Загрузка фото авто ──────────────────────────────────

def _get_car_image(specs: CarSpecs) -> Optional[Image.Image]:
    """
    Получает фото авто через image_finder:
    каталог -> Bing -> DuckDuckGo -> DALL-E -> None.
    """
    from .image_finder import find_car_image
    return find_car_image(specs.make, specs.model, specs.image_url)


def _prepare_car_image(
    car_img: Image.Image,
    poster_w: int,
    bg_color: str,
    max_h: int = 400,
    fade_px: int = 60,
) -> tuple[Image.Image, int]:
    """
    Ресайз фото + градиентное затухание сверху/снизу
    для бесшовного перехода в тёмный фон постера.
    Возвращает (подготовленное изображение, его высоту).
    """
    # Ресайз: вписать в 90% ширины постера, ограничить высоту
    target_w = int(poster_w * 0.92)
    ratio = target_w / car_img.width
    target_h = int(car_img.height * ratio)

    if target_h > max_h:
        target_h = max_h
        ratio = max_h / car_img.height
        target_w = int(car_img.width * ratio)

    car_img = car_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # Холст (ширина постера × высота фото) с фоном
    from PIL import ImageColor
    bg_rgb = ImageColor.getrgb(bg_color)
    canvas = Image.new("RGB", (poster_w, target_h), bg_rgb)
    x_off = (poster_w - target_w) // 2
    canvas.paste(car_img, (x_off, 0))

    # Градиентная маска (затухание сверху и снизу)
    bg_layer = Image.new("RGB", (poster_w, target_h), bg_rgb)
    mask = Image.new("L", (poster_w, target_h), 255)
    mask_draw = ImageDraw.Draw(mask)

    for y_off in range(min(fade_px, target_h)):
        alpha = int(255 * y_off / fade_px)
        mask_draw.line([(0, y_off), (poster_w, y_off)], fill=alpha)

    for y_off in range(max(0, target_h - fade_px), target_h):
        alpha = int(255 * (target_h - y_off) / fade_px)
        mask_draw.line([(0, y_off), (poster_w, y_off)], fill=alpha)

    result = Image.composite(canvas, bg_layer, mask)
    return result, target_h


# ─── Стиль из референса ──────────────────────────────────

def _load_style(ref_path: Optional[Path]) -> dict[str, Any]:
    if ref_path and ref_path.exists():
        try:
            style = load_reference_style(ref_path)
            logger.info("Style from reference: %s", ref_path.name)
            return style
        except Exception as e:
            logger.warning("Cannot load reference: %s", e)
    return {
        "width": POSTER_W,
        "height": POSTER_H,
        "color_bg": COLOR_BG,
        "color_accent": COLOR_ACCENT,
        "color_main": COLOR_PRIMARY,
        "color_muted": COLOR_SECONDARY,
    }


# ─── Генерация постера ───────────────────────────────────

def generate_poster(
    specs: CarSpecs,
    output_path: Optional[Path] = None,
    reference_path: Optional[Path] = None,
) -> Path:
    """
    Генерирует постер автомобиля.

    Два режима макета:
      - С фотографией: заголовок -> фото -> характеристики
      - Без фото: заголовок -> развёрнутые характеристики
    """
    from .config import REFERENCE_IMAGE

    ref = reference_path or REFERENCE_IMAGE
    style = _load_style(ref)

    w: int = style.get("width", POSTER_W)
    h: int = style.get("height", POSTER_H)
    bg = style.get("color_bg", COLOR_BG)
    accent = style.get("color_accent", COLOR_ACCENT)
    primary = style.get("color_main", COLOR_PRIMARY)
    secondary = style.get("color_muted", COLOR_SECONDARY)

    s = min(w / 1080, h / 1350)

    # ── Попытка получить фото авто ───────────────────────
    car_image = _get_car_image(specs)

    # ── Холст ────────────────────────────────────────────
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)

    # ── Тонкий диагональный паттерн на фоне ──────────────
    pattern_color = "#0e0e0e"
    step = int(80 * s)
    for i in range(-h, w + h, step):
        draw.line([(i, 0), (i + h, h)], fill=pattern_color, width=1)

    # ── Угловые акценты ──────────────────────────────────
    _draw_corners(draw, w, h, accent, s)

    # ── Марка (letter-spaced) ────────────────────────────
    y = int(110 * s)
    font_brand = _find_font(int(28 * s), "light")
    _draw_spaced_text(draw, (w // 2, y), specs.make.upper(), font_brand, secondary, int(14 * s))

    # ── Модель (крупно) ──────────────────────────────────
    y += int(75 * s)
    model_text = (specs.model or specs.full_name).upper()
    font_size = int(96 * s)
    font_model = _find_font(font_size, "bold")
    while _text_width(draw, model_text, font_model) > w * 0.85 and font_size > 40:
        font_size -= 4
        font_model = _find_font(font_size, "bold")

    # Мягкое красное свечение
    glow_color = "#1a0505"
    gr = max(2, int(3 * s))
    for dx in range(-gr, gr + 1):
        for dy in range(-gr, gr + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((w // 2 + dx * 2, y + dy * 2), model_text, font=font_model, fill=glow_color, anchor="mm")
    draw.text((w // 2, y), model_text, font=font_model, fill=primary, anchor="mm")

    # ── Красная полоса ───────────────────────────────────
    y += int(70 * s)
    bar_w = int(w * 0.40)
    bar_h = max(3, int(3 * s))
    bx = (w - bar_w) // 2
    draw.rectangle([(bx, y), (bx + bar_w, y + bar_h)], fill=accent)
    y += int(20 * s)

    # ═══════════════════════════════════════════════════════
    # РЕЖИМ 1: С фото авто
    # ═══════════════════════════════════════════════════════
    if car_image is not None:
        y += int(15 * s)

        # Подготовка и вставка фото
        max_img_h = int(380 * s)
        prepared, img_h = _prepare_car_image(car_image, w, bg, max_h=max_img_h, fade_px=int(50 * s))
        img.paste(prepared, (0, y))
        y += img_h + int(15 * s)

        # Тонкая красная линия под фото
        thin_w = int(w * 0.30)
        draw = ImageDraw.Draw(img)  # refresh after paste
        draw.line([((w - thin_w) // 2, y), ((w + thin_w) // 2, y)], fill=accent, width=max(1, int(2 * s)))
        y += int(25 * s)

        # Характеристики (компактнее, до 5 штук)
        selected = _select_specs(specs.specs, max_items=5)
        n = len(selected) or 1
        bottom_reserved = int(65 * s)
        available = h - y - bottom_reserved
        row_h = min(int(90 * s), available // n)

        font_label = _find_font(int(16 * s), "light")
        font_value = _find_font(int(26 * s), "semibold")

        for i, (label, value) in enumerate(selected):
            draw.text((w // 2, y), label.upper(), font=font_label, fill=secondary, anchor="mm")
            y += int(25 * s)
            val = (value[:42] + "...") if len(value) > 42 else value
            draw.text((w // 2, y), val, font=font_value, fill=primary, anchor="mm")
            y += int(32 * s)
            if i < n - 1:
                sep = int(30 * s)
                draw.line([(w // 2 - sep, y), (w // 2 + sep, y)], fill=COLOR_SEPARATOR, width=1)
                y += row_h - int(57 * s)

    # ═══════════════════════════════════════════════════════
    # РЕЖИМ 2: Без фото (только типографика)
    # ═══════════════════════════════════════════════════════
    else:
        y += int(35 * s)

        # Заголовок секции
        font_section = _find_font(int(14 * s), "light")
        _draw_spaced_text(draw, (w // 2, y), "SPECIFICATIONS", font_section, COLOR_MUTED, int(8 * s))
        y += int(55 * s)

        # Характеристики (развёрнуто, до 7 штук)
        selected = _select_specs(specs.specs, max_items=7)
        n = len(selected) or 1
        bottom_reserved = int(80 * s)
        available = h - y - bottom_reserved
        row_h = min(int(120 * s), available // n)

        font_label = _find_font(int(18 * s), "light")
        font_value = _find_font(int(30 * s), "semibold")

        for i, (label, value) in enumerate(selected):
            draw.text((w // 2, y), label.upper(), font=font_label, fill=secondary, anchor="mm")
            y += int(30 * s)
            val = (value[:42] + "...") if len(value) > 42 else value
            draw.text((w // 2, y), val, font=font_value, fill=primary, anchor="mm")
            y += int(38 * s)
            if i < n - 1:
                sep = int(35 * s)
                draw.line([(w // 2 - sep, y), (w // 2 + sep, y)], fill=COLOR_SEPARATOR, width=1)
                y += row_h - int(68 * s)

    # ── Нижняя полоска ───────────────────────────────────
    thin_w = int(w * 0.20)
    footer_y = h - int(65 * s)
    draw.line([((w - thin_w) // 2, footer_y), ((w + thin_w) // 2, footer_y)], fill=COLOR_SEPARATOR, width=1)

    # ── Источник ─────────────────────────────────────────
    font_src = _find_font(int(12 * s), "light")
    draw.text((w // 2, h - int(42 * s)), "automobile-catalog.com", font=font_src, fill=COLOR_MUTED, anchor="mm")

    # ── Сохранение ───────────────────────────────────────
    if output_path is None:
        safe_model = specs.model.replace(" ", "_").replace("/", "_")
        output_path = Path("output") / f"{specs.make}_{safe_model}.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        output_path = output_path.with_suffix(".png")
    img.save(output_path, "PNG", optimize=True)
    mode = "with car image" if car_image else "text-only"
    logger.info("Poster saved (%s): %s (%dx%d)", mode, output_path, w, h)
    return output_path
