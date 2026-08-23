"""
Обработка сырых картинок скинов из генератора: ресайз под целевой размер
+ сжатие палитры, аналог `pngquant` (не установлен на этой машине —
см. HANDOFF.md, «Технические нюансы»). Используется один раз, не часть
приложения — держится в scripts/, не в app/.

Запуск:
    python scripts/process_skin_images.py <исходная_папка> <skin_name>

Пример:
    python scripts/process_skin_images.py "../../Стили/GRAFFITI" graffiti
"""

import sys
from pathlib import Path

from PIL import Image

# (макс. ширина, макс. высота) — «вписать» с сохранением пропорций,
# не растянуть. Источник — designs/002-skin-illustration-prompts.md,
# таблица "Куда класть и в каком виде".
TARGET_BOX = {
    "empty-tasks.png": (640, 400),
    "empty-habits.png": (640, 400),
    "empty-goals.png": (640, 400),
    "empty-shelf.png": (640, 400),
    "empty-finance.png": (640, 400),
    "hero-finance.png": (640, 400),
    "motivation.png": (512, 512),
    "avatar.png": (256, 256),
    "logo.png": (720, 200),
    "badge-100.png": (128, 128),
    "badge-300.png": (128, 128),
    "badge-600.png": (128, 128),
    "badge-1000.png": (128, 128),
}

# pixel-скин обязан остаться резким (см. designs/002: "пиксель-арт нельзя
# масштабировать сглаживанием") — NEAREST вместо LANCZOS при ресайзе,
# меньше цветов в палитре (сам стиль ограничен 4-6 базовыми цветами).
_PIXEL_RESAMPLE = Image.NEAREST
_DEFAULT_RESAMPLE = Image.LANCZOS
_PIXEL_COLORS = 48
_DEFAULT_COLORS = 128


def process_one(src: Path, dest: Path, is_pixel_skin: bool) -> int:
    box = TARGET_BOX.get(src.name)
    if box is None:
        raise ValueError(f"Неизвестное имя файла, нет целевого размера: {src.name}")

    im = Image.open(src).convert("RGBA")
    resample = _PIXEL_RESAMPLE if is_pixel_skin else _DEFAULT_RESAMPLE
    im.thumbnail(box, resample)

    colors = _PIXEL_COLORS if is_pixel_skin else _DEFAULT_COLORS
    quantized = im.quantize(colors=colors, method=Image.FASTOCTREE)

    dest.parent.mkdir(parents=True, exist_ok=True)
    quantized.save(dest, optimize=True)
    return dest.stat().st_size


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    src_dir = Path(sys.argv[1])
    skin_name = sys.argv[2]
    is_pixel_skin = skin_name == "pixel"

    dest_dir = (
        Path(__file__).parent.parent / "app" / "web" / "static" / "skins" / skin_name
    )

    total = 0
    count = 0
    for src in sorted(src_dir.glob("*.png")):
        dest = dest_dir / src.name
        size = process_one(src, dest, is_pixel_skin)
        total += size
        count += 1
        print(f"{src.name:20s} -> {size / 1024:6.1f} КБ")

    print(f"\n{count} файлов, {total / 1024:.1f} КБ итого -> {dest_dir}")


if __name__ == "__main__":
    main()
