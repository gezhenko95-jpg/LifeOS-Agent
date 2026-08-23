# Иллюстрации к скинам — пошаговая инструкция

Скин — вторая ось оформления. Первая (акцентная тема) меняет только
цвет. Скин меняет характер: шрифт, форму рамок, тени — это CSS, — плюс
набор картинок, которые CSS нарисовать не может. Этот файл про картинки.

**Статус на 23.08 (ночь):** 29 из 30 картинок сгенерированы, сжаты
(ресайз + квантизация палитры — `pngquant` на машине не установлен,
использован эквивалент на Pillow, см. `scripts/process_skin_images.py`)
и подключены в CSS всех четырёх скинов. Единственное, что осталось —
**одна перегенерация**: `graffiti/logo.png` пришёл с текстом
`LIFEOS TRACKER` вместо одного слова `LIFEOS` — нарушение промпта (там
прямо написано `No other text besides the word LIFEOS`). Файл удалён
из `app/web/static/skins/graffiti/` до перегенерации — скин graffiti
пока показывает кольцо-лого вместо своего леттеринга (`.brand-mark`,
см. `app/web/static/index.html`).

---

## Единственный оставшийся промпт

### `graffiti/logo.png` (720×200)

Генерировать 3–4 раза и выбирать вариант, где написано **только**
`LIFEOS` — без второго слова, без хвостов текста, без искажённых букв.

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: the single word LIFEOS, spelled exactly L-I-F-E-O-S, as one horizontal graffiti tag with paint drips.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow. No other text besides the word LIFEOS. Centered, even margins.
```

Куда положить и что сделать дальше — `app/web/static/skins/graffiti/
logo.png`, затем в `app/web/static/index.html` найти комментарий
«Лого-леттеринг — граффити-тег вместо кольца» (в блоке
`:root[data-skin="graffiti"]`) и включить `.brand::before` тем же
блоком, что уже есть у groovy/japan/pixel рядом.

---

## Обработка (пайплайн, если появятся ещё картинки)

`pngquant` на этой машине не установлен (`winget` его не нашёл) —
вместо него `scripts/process_skin_images.py` (Pillow: `Image.thumbnail`
+ `Image.quantize(method=FASTOCTREE)`). Запуск:

```bash
cd lifeos-agent
python scripts/process_skin_images.py "<папка со скином>" <имя_скина>
```

Читает целевые размеры из самого скрипта (та же таблица, что была
здесь раньше — empty-состояния 640×400, мотивация 512×512, аватар
256×256, лого 720×200, бейджи 128×128), пишет прямо в
`app/web/static/skins/<имя_скина>/`. Для `pixel` автоматически
использует `NEAREST` вместо `LANCZOS` при ресайзе (иначе размывает
резкие пиксельные грани) и палитру поменьше (48 цветов вместо 128) —
сам стиль ограничен несколькими базовыми цветами.

Если `pngquant` всё же поставите — он даёт заметно лучшее сжатие
(меньше вес при том же качестве, умнее подбирает палитру), но для
прямо сейчас пайплайн на Pillow достаточен: итоговый вес в пределах
той же «реалистичной» оценки, что была у groovy (400–450 КБ на скин),
не в пределах изначальной строгой (≤250 КБ), но это уже было принято
раньше.

---

## Приёмка: проверить перед тем, как класть в `static/`

1. Фон **действительно** прозрачный, а не белый — проверять по альфа-
   каналу (`im.convert("RGBA").getchannel("A").getextrema()`), не на
   глаз: разные просмотрщики рисуют прозрачность по-разному (белым,
   чёрным, шахматкой), глаз обманывает.
2. Внутри нет лишних букв и цифр (кроме шага «лого» — и то только
   слово `LIFEOS`, ничего больше — см. историю с graffiti выше).
3. Читается в реальном размере — открыть уменьшенным, а не любоваться
   в полный рост.
4. Лежит в одном наборе с остальными картинками **этого же** скина —
   манера не должна плыть от промпта к промпту.
