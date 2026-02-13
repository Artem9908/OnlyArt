#!/usr/bin/env python3
"""
Авто-постеры: парсинг automobile-catalog.com и генерация постеров.
Запуск: python main.py --brand Audi [--model "TT RS"] [--output output/poster.png]
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

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("main")


# Демо-данные для случая, когда сайт недоступен (проверка пайплайна)
DEMO_SPECS = CarSpecs(
    make="Audi",
    model="TT RS",
    full_name="Audi TT RS",
    specs={
        "Engine": "2.5 TFSI 5-cylinder",
        "Displacement": "2,480 cc",
        "Power": "400 hp",
        "Torque": "354 lb-ft",
        "0-60 mph": "3.6 s",
        "Top speed": "174 mph",
        "Drive": "Quattro AWD",
        "Transmission": "7-speed S tronic",
    },
)


def run(brand: str, model: str | None, output: Path | None) -> Path:
    """
    Основной сценарий: найти модель → загрузить характеристики → сгенерировать постер.
    При недоступности сайта использует демо-данные.
    """
    brand = brand.strip()
    if not brand:
        raise ValueError("Укажите марку (--brand)")

    logger.info("Марка: %s", brand)
    if model:
        logger.info("Модель: %s", model)

    car_specs: CarSpecs | None = None

    if model:
        # Поиск страницы модели по имени
        model_link = find_model_by_name(brand, model)
        if model_link:
            car_specs = fetch_car_specs(brand, model, model_link["url"])
            if car_specs and not car_specs.specs:
                car_specs.specs = DEMO_SPECS.specs  # подставить ключевые поля для постера
        if not car_specs:
            logger.warning(
                "Не удалось загрузить данные с сайта. Используются демо-данные для %s %s.",
                brand,
                model,
            )
            car_specs = CarSpecs(
                make=brand,
                model=model,
                full_name=f"{brand} {model}",
                specs=DEMO_SPECS.specs,
            )
    else:
        # Только марка — берём первую доступную модель или демо
        models = fetch_models_for_make(brand)
        if models:
            first = models[0]
            car_specs = fetch_car_specs(brand, first["name"], first["url"])
        if not car_specs or not car_specs.specs:
            logger.warning(
                "Не удалось загрузить данные с сайта. Используются демо-данные для %s TT RS.",
                brand,
            )
            car_specs = CarSpecs(
                make=brand,
                model="TT RS",
                full_name=f"{brand} TT RS",
                specs=DEMO_SPECS.specs,
            )
    assert car_specs is not None
    out_path = output or (OUTPUT_DIR / f"{car_specs.make}_{car_specs.model.replace(' ', '_')}.png")
    return generate_poster(car_specs, out_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Генерация постеров автомобилей по данным automobile-catalog.com",
    )
    parser.add_argument(
        "--brand",
        "-b",
        required=True,
        help="Марка автомобиля (например: Audi, BMW)",
    )
    parser.add_argument(
        "--model",
        "-m",
        default=None,
        help='Модель/модификация (например: "TT RS"). Необязательно.',
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Путь к выходному файлу (PNG/JPG). По умолчанию: output/Марка_Модель.png",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Подробный вывод (DEBUG)",
    )
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    try:
        path = run(args.brand, args.model, args.output)
        print(f"Готово. Постер: {path.resolve()}")
    except Exception as e:
        logger.exception("Ошибка: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
