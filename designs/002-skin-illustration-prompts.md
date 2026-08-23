# Иллюстрации к скинам — пошаговая инструкция

Скин — вторая ось оформления. Первая (акцентная тема) меняет только
цвет. Скин меняет характер: шрифт, форму рамок, тени — это CSS, — плюс
набор картинок, которые CSS нарисовать не может. Этот файл про картинки.

**Статус на 23.08:** `groovy` (24/24) и базовый набор `japan` (11/11)
уже сгенерированы и лежат в `app/web/static/skins/` — в этом файле их
больше нет, смотреть в `HANDOFF.md`/git-истории, если нужны их промпты.
Ниже — только то, что реально осталось: **graffiti** (11 картинок),
**pixel** (11 картинок), **финансы** (8 картинок — по 2 на каждый из
четырёх скинов, включая уже готовые groovy и japan, у которых этой пары
пока нет). Итого 30 генераций.

---

## Что генерируем, а что не генерируем

| Что | Как делается | Почему так |
|---|---|---|
| Крупные иллюстрации (пустые состояния, аватар, лого, бейджи) | **Генератор картинок**, промпты ниже | Показываются на 128–640px, растр уместен |
| Иконки интерфейса (16 глифов) | **Рисуются в коде как SVG** | Живут на 12–16px, растр там разваливается в кашу |
| Волны, радуги, подтёки, рамки | **CSS-градиенты и псевдоэлементы** | Резче, легче, красятся темой |

Про иконки отдельно: свой набор под скин делается правкой кода
(`app/web/static/index.html`, `PIXEL_GRID`/`ICON_LINE`), не этим файлом.

---

## Перед началом: пять правил

1. **Прозрачный фон обязателен.** Карточка красится акцентной темой
   пользователя (их семь) и живёт в светлом и тёмном режиме. Картинка со
   своим фоном станет квадратом чужого цвета при любой теме, кроме той,
   под которую генерировали.
2. **Никакого текста внутри картинки.** Интерфейс русский, генераторы
   пишут кириллицу с ошибками. Единственное исключение — лого (латиница
   `LIFEOS`), его вычитывать глазами.
3. **Один скин за раз, целиком.** Не «по одной картинке из каждого» —
   иначе наборы расползутся по манере.
4. **Стилевой блок копируется дословно.** Не пересказывать своими
   словами: от этого генератор и плывёт от картинки к картинке. Ниже
   каждый промпт уже собран целиком — копировать блок в тройных кавычках
   от начала до конца, ничего не дописывать и не сокращать.
5. **Порядок: graffiti → pixel → финансы**, или в любом другом — они не
   зависят друг от друга, но внутри одного скина промпты лучше
   генерировать подряд, не перемежая с другим скином (тот же довод, что
   и в правиле 3).

---

## Куда класть и в каком виде

Складывать в `app/web/static/skins/<skin>/` под именами из шагов.

| Параметр | Значение |
|---|---|
| Формат | PNG-24 с альфа-каналом, потом прогнать через `pngquant` |
| Пустые состояния | 640×400 |
| Мотивация | 512×512 |
| Аватар | 256×256 |
| Лого | 720×200 |
| Бейджи | 128×128 |
| Финансовые (пустое состояние + герой) | 640×400 |
| Вес одного файла | ≤ 40 КБ |
| Вес скина целиком | ≤ 250 КБ (у groovy с декором вышло ~450 КБ — это верхняя граница, не ориентир) |

**Вес — не придирка.** Всё грузится с нашего сервера в Нидерландах:
внешние CDN из России не работают (проверено дважды, см. `HANDOFF.md`),
разложить по чужим хостингам нельзя. Отсюда правило в коде: **ассеты
скина грузятся лениво**, только когда скин выбран. Сжатие — `pngquant`,
начинать с тех же параметров, что дали groovy: палитра 200, масштаб 1.0.

---

# GRAFFITI — 11 промптов

Уличный стиль. Единственный скин, переопределяющий **режим**, а не
только акцент — карточки чёрные, текст светлый (см. примечание в конце
раздела). Складывать в `app/web/static/skins/graffiti/`.

### Шаг 1 — `empty-tasks.png` (640×400)

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: a clipboard with a checklist, checkmarks drawn as rough marker strokes.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 2 — `empty-habits.png` (640×400)

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: a spray paint can with a burst of paint mist.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 3 — `empty-goals.png` (640×400)

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: a target with two arrows in it, paint dripping from the rings.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 4 — `empty-shelf.png` (640×400)

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: an open book beside a film strip.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 5 — `motivation.png` (512×512)

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: a classical marble bust with a spray-painted stripe across the eyes.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 6 — `avatar.png` (256×256)

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: a person in a hood, face in shadow, portrait, head and shoulders, facing forward.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 7 — `logo.png` (720×200)

Единственный шаг, где текст в картинке разрешён. Генерировать 3–4 раза и
выбирать вариант, где `LIFEOS` написано без ошибок — модели врут в
буквах даже на латинице.

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: the single word LIFEOS, spelled exactly L-I-F-E-O-S, as one horizontal graffiti tag with paint drips.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow. No other text besides the word LIFEOS. Centered, even margins.
```

### Шаг 8 — `badge-100.png` (128×128)

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: a single gemstone outlined in marker.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject. Icon-like, readable at small size.
```

### Шаг 9 — `badge-300.png` (128×128)

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: a larger gemstone with a halftone shading pattern.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject. Icon-like, readable at small size.
```

### Шаг 10 — `badge-600.png` (128×128)

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: a five-point crown drawn as a marker doodle.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject. Icon-like, readable at small size.
```

### Шаг 11 — `badge-1000.png` (128×128)

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: a trophy cup with paint dripping down it.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject. Icon-like, readable at small size.
```

> **Про граффити отдельно:** карточки этого скина чёрные, текст светлый
> — в CSS ему нужны собственные `--card-bg` и `--text`, и проверять его
> надо и в светлом, и в тёмном режиме браузера. Иначе у половины
> пользователей будет светлый текст на светлой карточке.

---

# PIXEL — 11 промптов

Пиксель-арт на строгой сетке 32×32. Складывать в
`app/web/static/skins/pixel/`.

### Шаг 1 — `empty-tasks.png` (640×400)

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.

Subject: a clipboard with a checklist.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 2 — `empty-habits.png` (640×400)

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.

Subject: a rainbow arc between two smiling clouds.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 3 — `empty-goals.png` (640×400)

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.

Subject: a mountain peak with a flag planted on top.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 4 — `empty-shelf.png` (640×400)

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.

Subject: an open book beside a film strip.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 5 — `motivation.png` (512×512)

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.

Subject: a capital letter L as a chunky isometric block.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 6 — `avatar.png` (256×256)

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.

Subject: a skull sprite, front view.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 7 — `logo.png` (720×200)

Единственный шаг, где текст в картинке разрешён. Генерировать 3–4 раза и
выбирать вариант, где `LIFEOS` написано без ошибок.

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.

Subject: the single word LIFEOS, spelled exactly L-I-F-E-O-S, in blocky pixel letterforms.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow. No other text besides the word LIFEOS. Centered, even margins.
```

### Шаг 8 — `badge-100.png` (128×128)

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.

Subject: a single small gemstone, simple faceting.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject. Icon-like, readable at small size.
```

### Шаг 9 — `badge-300.png` (128×128)

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.

Subject: a larger gemstone with more facets, radiating sparkle lines.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject. Icon-like, readable at small size.
```

### Шаг 10 — `badge-600.png` (128×128)

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.

Subject: a crown with three points.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject. Icon-like, readable at small size.
```

### Шаг 11 — `badge-1000.png` (128×128)

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.

Subject: a trophy cup with two handles.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject. Icon-like, readable at small size.
```

> **Про пиксель отдельно:** пиксель-арт нельзя масштабировать
> сглаживанием. При показе обязателен `image-rendering: pixelated`,
> иначе вся резкость, ради которой скин делался, размоется.

---

# ФИНАНСЫ — 8 промптов (все четыре скина)

Ни у одного скина нет картинки под финансовую карточку — домена не
существовало, когда генерировались остальные наборы. Два сюжета на
каждый скин: пустое состояние (список транзакций пуст) и «герой»
карточки — крупная картинка сверху, как `hero-progress`/`hero-weekly`/
`hero-quick` у groovy.

**Слот под них в CSS/разметке ещё не сделан** — картинка и разметка
входят одним изменением. Как картинки будут готовы, подключить и слот,
и файлы разом.

| Файл | Размер | Куда | Показывается |
|---|---|---|---|
| `empty-finance.png` | 640×400 | `skins/<skin>/` | список транзакций пуст |
| `hero-finance.png` | 640×400 | `skins/<skin>/` | шапка карточки «Финансы» |

## Groovy

Стилевой блок — с чёрным контуром внутри самой картинки (та же версия,
что у декора/героев groovy), не базовый: финансовая карточка того же
поколения дизайн-системы 003, что и остальные, ей нужен тот же контур.

```
1970s retro groovy illustration. Every shape has a thick uniform black outline, 4 to 6 pixels relative to a 500px wide image. Bubbly organic forms, rounded corners. Palette: coral red, sunset orange, golden yellow, sage green, periwinkle blue, dusty lavender. Flat fills, occasional simple two-stop gradients. Cheerful, optimistic, slightly naive. Sticker-pack aesthetic, like a die-cut vinyl sticker.

Subject: a piggy bank with one coin floating just above its coin slot, about to drop in.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

```
1970s retro groovy illustration. Every shape has a thick uniform black outline, 4 to 6 pixels relative to a 500px wide image. Bubbly organic forms, rounded corners. Palette: coral red, sunset orange, golden yellow, sage green, periwinkle blue, dusty lavender. Flat fills, occasional simple two-stop gradients. Cheerful, optimistic, slightly naive. Sticker-pack aesthetic, like a die-cut vinyl sticker.

Subject: a rising staircase of stacked coins with a small sprouting plant on the top step.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

## Japan

```
Japanese woodblock print, ukiyo-e engraving style. Two-color risograph printing: deep indigo blue and vermilion red only. Fine parallel hatching for shading, visible woodgrain texture, slight misregistration between the two color plates. Bold confident linework, flat areas of color, no gradients. Weathered, aged linework.

Subject: a piggy bank with one coin floating just above its coin slot, about to drop in.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

```
Japanese woodblock print, ukiyo-e engraving style. Two-color risograph printing: deep indigo blue and vermilion red only. Fine parallel hatching for shading, visible woodgrain texture, slight misregistration between the two color plates. Bold confident linework, flat areas of color, no gradients. Weathered, aged linework.

Subject: a rising staircase of stacked coins with a small sprouting plant on the top step.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

## Graffiti

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: a piggy bank with one coin floating just above its coin slot, about to drop in.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.

Subject: a rising staircase of stacked coins with a small sprouting plant on the top step.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

## Pixel

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.

Subject: a piggy bank with one coin floating just above its coin slot, about to drop in.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.

Subject: a rising staircase of stacked coins with a small sprouting plant on the top step.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

---

## Приёмка: проверить пять вещей до того, как класть в `static/`

1. Фон **действительно** прозрачный, а не белый. Открыть на тёмной
   подложке и посмотреть.
2. Внутри нет букв и цифр (кроме шага «лого»).
3. Читается в реальном размере — открыть уменьшенным до 320×200, а не
   любоваться в полный рост.
4. Вес после `pngquant` в рамках таблицы.
5. Лежит в одном наборе с остальными картинками **этого же** скина —
   манера не должна плыть от промпта к промпту.

Пятый пункт проваливается чаще остальных: генератор плывёт по манере от
запроса к запросу. Лечится тем, что стилевой блок копируется дословно.
Если картинка выбилась — перегенерировать её, а не подгонять соседние.
