#!/usr/bin/env python3
"""
Авто-постеры: парсинг automobile-catalog.com → генерация постера.

Запуск:
    python main.py --brand Audi --model "TT RS"
    python main.py -b BMW -m M3 -o output/bmw_m3.png
"""
import argparse
import logging
import sys
from pathlib import Path

from src.catalog_parser import (
    CarSpecs,
    fetch_car_specs,
    fetch_models_for_make,
    find_model_by_name,
)
from src.config import OUTPUT_DIR
from src.poster_generator import generate_poster

# ─── Логирование ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("main")


# ─── Демо-данные (fallback, когда сайт недоступен) ────────
# Реальные характеристики популярных автомобилей для качественных постеров.

DEMO_SPECS_DB: dict[tuple[str, str], dict[str, str]] = {
    ("audi", "tt rs"): {
        "Engine": "2.5L TFSI 5-cyl Turbo",
        "Power": "400 HP @ 5,850 rpm",
        "Torque": "354 lb-ft @ 1,700 rpm",
        "0-60 mph": "3.6 s",
        "Top Speed": "174 mph",
        "Drivetrain": "Quattro AWD",
        "Transmission": "7-speed S tronic DCT",
    },
    ("bmw", "m3"): {
        "Engine": "3.0L S58 Twin-Turbo I6",
        "Power": "473 HP @ 6,250 rpm",
        "Torque": "406 lb-ft @ 2,750 rpm",
        "0-60 mph": "3.8 s",
        "Top Speed": "180 mph",
        "Drivetrain": "M xDrive AWD",
        "Transmission": "8-speed M Steptronic",
    },
    ("porsche", "911 turbo"): {
        "Engine": "3.7L Twin-Turbo Flat-6",
        "Power": "572 HP @ 6,750 rpm",
        "Torque": "553 lb-ft @ 2,500 rpm",
        "0-60 mph": "2.7 s",
        "Top Speed": "198 mph",
        "Drivetrain": "AWD",
        "Transmission": "8-speed PDK",
    },
    ("porsche", "911 turbo s"): {
        "Engine": "3.8L Twin-Turbo Flat-6",
        "Power": "640 HP @ 6,750 rpm",
        "Torque": "590 lb-ft @ 2,500 rpm",
        "0-60 mph": "2.6 s",
        "Top Speed": "205 mph",
        "Drivetrain": "AWD",
        "Transmission": "8-speed PDK",
    },
    ("nissan", "gt-r nismo"): {
        "Engine": "3.8L VR38DETT V6 Twin-Turbo",
        "Power": "600 HP @ 6,800 rpm",
        "Torque": "481 lb-ft @ 3,600 rpm",
        "0-60 mph": "2.5 s",
        "Top Speed": "205 mph",
        "Drivetrain": "ATTESA E-TS AWD",
        "Transmission": "6-speed Dual-Clutch",
    },
    ("nissan", "gt-r"): {
        "Engine": "3.8L VR38DETT V6 Twin-Turbo",
        "Power": "565 HP @ 6,800 rpm",
        "Torque": "467 lb-ft @ 3,300 rpm",
        "0-60 mph": "2.9 s",
        "Top Speed": "196 mph",
        "Drivetrain": "ATTESA E-TS AWD",
        "Transmission": "6-speed Dual-Clutch",
    },
    ("mercedes-benz", "amg gt"): {
        "Engine": "4.0L V8 Biturbo",
        "Power": "523 HP @ 6,250 rpm",
        "Torque": "494 lb-ft @ 1,900 rpm",
        "0-60 mph": "3.7 s",
        "Top Speed": "193 mph",
        "Drivetrain": "RWD",
        "Transmission": "7-speed AMG DCT",
    },
    ("lamborghini", "huracan"): {
        "Engine": "5.2L V10 NA",
        "Power": "631 HP @ 8,000 rpm",
        "Torque": "417 lb-ft @ 6,500 rpm",
        "0-60 mph": "2.9 s",
        "Top Speed": "202 mph",
        "Drivetrain": "AWD",
        "Transmission": "7-speed LDF DCT",
    },
    ("ferrari", "488"): {
        "Engine": "3.9L V8 Twin-Turbo",
        "Power": "661 HP @ 8,000 rpm",
        "Torque": "561 lb-ft @ 3,000 rpm",
        "0-60 mph": "2.85 s",
        "Top Speed": "205 mph",
        "Drivetrain": "RWD",
        "Transmission": "7-speed F1 DCT",
    },
    ("toyota", "supra"): {
        "Engine": "3.0L B58 Turbo I6",
        "Power": "382 HP @ 5,800 rpm",
        "Torque": "368 lb-ft @ 1,800 rpm",
        "0-60 mph": "3.9 s",
        "Top Speed": "155 mph",
        "Drivetrain": "RWD",
        "Transmission": "8-speed Auto",
    },
}

# Дефолтные спеки (если марка/модель не в базе)
_DEFAULT_DEMO = {
    "Engine": "Turbocharged",
    "Power": "300+ HP",
    "Torque": "300+ lb-ft",
    "0-60 mph": "4.5 s",
    "Top Speed": "155 mph",
    "Drivetrain": "AWD",
    "Transmission": "Automatic",
}


def _get_demo_specs(make: str, model: str) -> dict[str, str]:
    """Подбирает демо-данные по марке и модели (нечёткое совпадение)."""
    mk = make.strip().lower()
    md = model.strip().lower()

    # Точное совпадение
    if (mk, md) in DEMO_SPECS_DB:
        return DEMO_SPECS_DB[(mk, md)]

    # Частичное совпадение модели
    for (db_mk, db_md), specs in DEMO_SPECS_DB.items():
        if db_mk == mk and (db_md in md or md in db_md):
            return specs

    # Частичное совпадение марки
    for (db_mk, db_md), specs in DEMO_SPECS_DB.items():
        if mk in db_mk or db_mk in mk:
            return specs

    return _DEFAULT_DEMO


# ─── Основная логика ─────────────────────────────────────

def run(brand: str, model: str | None, output: Path | None) -> Path:
    """
    Найти модель → загрузить характеристики → сгенерировать постер.
    При недоступности сайта — использует демо-данные.
    """
    brand = brand.strip()
    if not brand:
        raise ValueError("Укажите марку (--brand)")

    logger.info("Марка: %s", brand)
    if model:
        logger.info("Модель: %s", model)

    car_specs: CarSpecs | None = None

    if model:
        # Поиск страницы модели
        model_link = find_model_by_name(brand, model)
        if model_link:
            car_specs = fetch_car_specs(brand, model, model_link["url"])
            # Если парсинг не дал характеристик — подставляем демо
            if car_specs and not car_specs.specs:
                car_specs.specs = _get_demo_specs(brand, model)

        if not car_specs:
            logger.warning(
                "Сайт недоступен → демо-данные для %s %s.", brand, model,
            )
            car_specs = CarSpecs(
                make=brand,
                model=model,
                full_name=f"{brand} {model}",
                specs=_get_demo_specs(brand, model),
            )
    else:
        # Только марка — берём первую модель или демо
        models = fetch_models_for_make(brand)
        if models:
            first = models[0]
            car_specs = fetch_car_specs(brand, first["name"], first["url"])
        if not car_specs or not car_specs.specs:
            fallback_model = "TT RS" if brand.lower() == "audi" else "Sport"
            logger.warning(
                "Сайт недоступен → демо-данные для %s %s.", brand, fallback_model,
            )
            car_specs = CarSpecs(
                make=brand,
                model=fallback_model,
                full_name=f"{brand} {fallback_model}",
                specs=_get_demo_specs(brand, fallback_model),
            )

    safe_model = car_specs.model.replace(" ", "_").replace("/", "_")
    out_path = output or (OUTPUT_DIR / f"{car_specs.make}_{safe_model}.png")
    return generate_poster(car_specs, out_path)


# ─── CLI ──────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Генерация постеров автомобилей по данным automobile-catalog.com",
    )
    parser.add_argument(
        "--brand", "-b", required=True,
        help="Марка автомобиля (например: Audi, BMW, Porsche)",
    )
    parser.add_argument(
        "--model", "-m", default=None,
        help='Модель/модификация (например: "TT RS", "M3"). Необязательно.',
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Путь к выходному файлу (PNG/JPG). По умолчанию: output/<Марка>_<Модель>.png",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Подробный вывод (DEBUG)",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        path = run(args.brand, args.model, args.output)
        print(f"\nГотово! Постер: {path.resolve()}")
    except Exception as e:
        logger.exception("Ошибка: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
