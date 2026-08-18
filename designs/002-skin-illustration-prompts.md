# Иллюстрации к скинам — пошаговая инструкция

Скин — вторая ось оформления. Первая (акцентная тема) меняет только
цвет. Скин меняет характер: шрифт, форму рамок, тени — это CSS, — плюс
набор картинок, которые CSS нарисовать не может. Этот файл про картинки.

Скины: `groovy`, `japan`, `graffiti`, `pixel`.

---

## Что генерируем, а что не генерируем

| Что | Как делается | Почему так |
|---|---|---|
| Крупные иллюстрации (пустые состояния, аватар, лого, бейджи) | **Генератор картинок**, промпты ниже | Показываются на 128–640px, растр уместен |
| Иконки интерфейса (16 глифов) | **Рисуются в коде как SVG** | Живут на 12–16px, растр там разваливается в кашу |
| Волны, радуги, подтёки, рамки | **CSS-градиенты и псевдоэлементы** | Резче, легче, красятся темой |

Про иконки отдельно: нынешний набор потому и нечитаемый, что глифы
рисовались под 24px, а показываются на 12. Генератор эту проблему не
решает, а усугубляет — он не умеет в пиксельную сетку. Свой набор под
каждый скин (16 × 4 = 64 глифа) делается правкой кода, не этим файлом.

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
   словами: от этого генератор и плывёт от картинки к картинке.
5. **Начинать с того скина, которым реально будете пользоваться.**
   Одиннадцать картинок × четыре скина — это 44 генерации.

---

## Куда класть и в каком виде

Складывать в `app/web/static/skins/<skin>/` под именами из шагов.

| Параметр | Значение |
|---|---|
| Формат | PNG-24 с альфа-каналом, потом прогнать через `pngquant` |
| Пустые состояния (шаги 1–4) | 640×400 |
| Мотивация (шаг 5) | 512×512 |
| Аватар (шаг 6) | 256×256 |
| Лого (шаг 7) | 720×200 |
| Бейджи (шаги 8–11) | 128×128 |
| Вес одного файла | ≤ 40 КБ |
| Вес скина целиком | ≤ 250 КБ |

**Вес — не придирка.** `index.html` уже 115 КБ, пиксельный шрифт ещё 30,
и всё грузится с нашего сервера в Нидерландах: внешние CDN из России не
работают (проверено дважды, см. `HANDOFF.md`), разложить по чужим
хостингам нельзя. Отсюда правило в коде: **ассеты скина грузятся лениво**,
только когда скин выбран. Человек на стандартном скине не должен
скачивать граффити.

---

# СКИН 1: `groovy` (ретро-груви)

Одиннадцать шагов. Каждый промпт — целиком готовый, копировать от начала
до конца, ничего не дописывать.

### Шаг 1 — `empty-tasks.png` (640×400)

```
1970s retro groovy illustration. Thick uniform rounded outlines, bubbly organic shapes. Palette: coral red, sunset orange, golden yellow, sage green, periwinkle blue, dusty lavender. Flat fills, occasional simple two-stop gradients. Cheerful, optimistic, slightly naive. Small four-pointed sparkles scattered around the subject.

Subject: a clipboard with a checklist.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 2 — `empty-habits.png` (640×400)

```
1970s retro groovy illustration. Thick uniform rounded outlines, bubbly organic shapes. Palette: coral red, sunset orange, golden yellow, sage green, periwinkle blue, dusty lavender. Flat fills, occasional simple two-stop gradients. Cheerful, optimistic, slightly naive. Small four-pointed sparkles scattered around the subject.

Subject: a rainbow arc between two smiling clouds.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 3 — `empty-goals.png` (640×400)

```
1970s retro groovy illustration. Thick uniform rounded outlines, bubbly organic shapes. Palette: coral red, sunset orange, golden yellow, sage green, periwinkle blue, dusty lavender. Flat fills, occasional simple two-stop gradients. Cheerful, optimistic, slightly naive. Small four-pointed sparkles scattered around the subject.

Subject: a mountain peak with a flag planted on top.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 4 — `empty-shelf.png` (640×400)

```
1970s retro groovy illustration. Thick uniform rounded outlines, bubbly organic shapes. Palette: coral red, sunset orange, golden yellow, sage green, periwinkle blue, dusty lavender. Flat fills, occasional simple two-stop gradients. Cheerful, optimistic, slightly naive. Small four-pointed sparkles scattered around the subject.

Subject: an open book beside a film strip.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 5 — `motivation.png` (512×512)

```
1970s retro groovy illustration. Thick uniform rounded outlines, bubbly organic shapes. Palette: coral red, sunset orange, golden yellow, sage green, periwinkle blue, dusty lavender. Flat fills, occasional simple two-stop gradients. Cheerful, optimistic, slightly naive. Small four-pointed sparkles scattered around the subject.

Subject: a smiling flower character wearing sunglasses, making a peace sign with one leaf hand.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 6 — `avatar.png` (256×256)

```
1970s retro groovy illustration. Thick uniform rounded outlines, bubbly organic shapes. Palette: coral red, sunset orange, golden yellow, sage green, periwinkle blue, dusty lavender. Flat fills, occasional simple two-stop gradients. Cheerful, optimistic, slightly naive.

Subject: a friendly character portrait, head and shoulders, facing forward, with wavy hair and round glasses.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject.
```

### Шаг 7 — `logo.png` (720×200)

Единственный шаг, где текст в картинке разрешён. Генерировать 3–4 раза и
выбирать вариант, где `LIFEOS` написано без ошибок — модели врут в
буквах даже на латинице.

```
1970s retro groovy display lettering. Thick uniform rounded outlines, bubbly organic letterforms, letters bulging and touching each other. Palette: coral red, sunset orange, golden yellow, periwinkle blue. Flat fills. Small four-pointed sparkles around the word.

Subject: the single word LIFEOS, spelled exactly L-I-F-E-O-S, as one horizontal lettering lockup.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow. No other text besides the word LIFEOS. Centered, even margins.
```

### Шаг 8 — `badge-100.png` (128×128)

```
1970s retro groovy illustration. Thick uniform rounded outlines, bubbly organic shapes. Palette: coral red, sunset orange, golden yellow, sage green, periwinkle blue, dusty lavender. Flat fills. Cheerful, slightly naive.

Subject: a single small gemstone, simple faceting.

Flat vector illustration, no photographic texture. Transparent background — no background fill, no card, no frame, no drop shadow behind the subject. No text, no letters, no numbers anywhere in the image. Centered composition, even margins, single subject. Icon-like, readable at small size.
```

### Шаг 9 — `badge-300.png` (128×128)

То же, что шаг 8, но `Subject: a larger gemstone with more facets, radiating
sparkle lines.`

### Шаг 10 — `badge-600.png` (128×128)

То же, что шаг 8, но `Subject: a crown with three points.`

### Шаг 11 — `badge-1000.png` (128×128)

То же, что шаг 8, но `Subject: a trophy cup with two handles.`

> **Про груви отдельно:** цветные волны и радуга во всю ширину карточки
> из референса — **не генерировать**. Это CSS-градиент в псевдоэлементе:
> резче, легче и красится темой.

---

# СКИН 2: `japan` (японская гравюра)

Те же одиннадцать шагов, те же имена файлов и размеры. Меняется первый
абзац промпта и сюжеты. Копировать целиком.

**Стилевой блок (первый абзац каждого промпта):**

```
Japanese woodblock print, ukiyo-e engraving style. Two-color risograph printing: deep indigo blue and vermilion red only. Fine parallel hatching for shading, visible woodgrain texture, slight misregistration between the two color plates. Bold confident linework, flat areas of color, no gradients. Weathered, aged linework.
```

**Техблок (последний абзац каждого промпта):** тот же, что у груви.

| Шаг | Файл | Subject |
|---|---|---|
| 1 | `empty-tasks.png` | `a clipboard with a checklist, beside a bamboo stalk` |
| 2 | `empty-habits.png` | `a crane bird in flight, wings spread` |
| 3 | `empty-goals.png` | `a coiling dragon among stylized clouds` |
| 4 | `empty-shelf.png` | `an open book beside a folding fan` |
| 5 | `motivation.png` | `Mount Fuji with stylized wave clouds at its base` |
| 6 | `avatar.png` | `a samurai warrior portrait, head and shoulders, facing forward` |
| 7 | `logo.png` | `the single word LIFEOS, spelled exactly L-I-F-E-O-S, as one horizontal lettering lockup in carved woodblock letterforms` |
| 8 | `badge-100.png` | `a single cherry blossom` |
| 9 | `badge-300.png` | `a folding fan, open` |
| 10 | `badge-600.png` | `a samurai helmet, front view` |
| 11 | `badge-1000.png` | `Mount Fuji, simplified to an icon` |

> **Про печати-ханко:** красные квадратные печати из референса (整理,
> 継続, 分析) — это **иероглифы внутри картинки**, то есть текст. Модели
> регулярно рисуют несуществующие или неуместные кандзи, и проверить это
> без знания языка нельзя. Если печати нужны — генерировать пустую рамку
> печати, а иероглиф ставить отдельным выверенным SVG.

---

# СКИН 3: `graffiti` (уличный)

**Стилевой блок:**

```
Street graffiti and urban stencil art. Rough spray-paint texture with visible overspray and paint drips running downward. High-contrast palette: electric violet, hot magenta, safety orange, acid yellow. Halftone dot shading. Torn paper and stencil-cut edges. Bold marker outlines, raw and deliberately imperfect, white chalk-like highlights.
```

**Техблок:** тот же.

| Шаг | Файл | Subject |
|---|---|---|
| 1 | `empty-tasks.png` | `a clipboard with a checklist, checkmarks drawn as rough marker strokes` |
| 2 | `empty-habits.png` | `a spray paint can with a burst of paint mist` |
| 3 | `empty-goals.png` | `a target with two arrows in it, paint dripping from the rings` |
| 4 | `empty-shelf.png` | `an open book beside a film strip` |
| 5 | `motivation.png` | `a classical marble bust with a spray-painted stripe across the eyes` |
| 6 | `avatar.png` | `a person in a hood, face in shadow, portrait, head and shoulders, facing forward` |
| 7 | `logo.png` | `the single word LIFEOS, spelled exactly L-I-F-E-O-S, as one horizontal graffiti tag with paint drips` |
| 8 | `badge-100.png` | `a single gemstone outlined in marker` |
| 9 | `badge-300.png` | `a larger gemstone with a halftone shading pattern` |
| 10 | `badge-600.png` | `a five-point crown drawn as a marker doodle` |
| 11 | `badge-1000.png` | `a trophy cup with paint dripping down it` |

> **Про граффити отдельно:** это единственный скин, который
> переопределяет **режим**, а не только акцент — карточки чёрные, текст
> светлый. В CSS ему нужны собственные `--card-bg` и `--text`, и
> проверять его надо и в светлом, и в тёмном режиме браузера. Иначе у
> половины пользователей будет светлый текст на светлой карточке.

---

# СКИН 4: `pixel` (уже в проде)

CSS у этого скина готов, картинок нет. Если решите добавить —
те же одиннадцать шагов.

**Стилевой блок:**

```
Pixel art on a strict 32x32 pixel grid. Hard aliased edges, no anti-aliasing whatsoever. Limited palette: black outlines, cream white, acid lime green, electric violet. Chunky two-pixel-wide outlines. NES-era video game sprite aesthetic. Every edge snaps to the pixel grid.
```

Сюжеты — те же, что у груви (шаги 1–4, 8–11), плюс:

| Шаг | Файл | Subject |
|---|---|---|
| 5 | `motivation.png` | `a capital letter L as a chunky isometric block` |
| 6 | `avatar.png` | `a skull sprite, front view` |
| 7 | `logo.png` | `the single word LIFEOS, spelled exactly L-I-F-E-O-S, in blocky pixel letterforms` |

> **Про пиксель отдельно:** пиксель-арт нельзя масштабировать
> сглаживанием. При показе обязателен `image-rendering: pixelated`,
> иначе вся резкость, ради которой скин делался, размоется.

---

## Приёмка: проверить пять вещей до того, как класть в `static/`

1. Фон **действительно** прозрачный, а не белый. Открыть на тёмной
   подложке и посмотреть.
2. Внутри нет букв и цифр (кроме шага 7).
3. Читается в реальном размере — открыть уменьшенным до 320×200, а не
   любоваться в полный рост.
4. Вес после `pngquant` в рамках таблицы.
5. Лежит в одном наборе с остальными десятью картинками **этого же**
   скина.

Пятый пункт проваливается чаще остальных: генератор плывёт по манере от
запроса к запросу. Лечится тем, что стилевой блок копируется дословно.
Если картинка выбилась — перегенерировать её, а не подгонять соседние.

---

# ДОПОЛНЕНИЕ: декор и герои под дизайн-систему 003

Одиннадцати картинок из основной части не хватает: по
`designs/003-groovy-design-system.md` иллюстрация нужна **в каждой**
карточке, а не только в пустом состоянии. Ниже ещё 13 шагов.

Порядок тот же: копировать промпт целиком, сохранять под именем из
заголовка шага. Всё складывать туда же — `app/web/static/skins/groovy/`.

## Что изменилось в промптах

К стилевому блоку добавлено требование **чёрного контура внутри самой
картинки**. В дизайн-системе обводка — конструкция, а не рамка: если у
рисунка контура нет, он будет выглядеть наклейкой не отсюда рядом с
обведёнными кнопками и карточками.

**Стилевой блок дополнения** (для шагов 12–24):

```
1970s retro groovy illustration. Every shape has a thick uniform black outline, 4 to 6 pixels relative to a 500px wide image. Bubbly organic forms, rounded corners. Palette: coral red, sunset orange, golden yellow, sage green, periwinkle blue, dusty lavender. Flat fills, occasional simple two-stop gradients. Cheerful, optimistic, slightly naive. Sticker-pack aesthetic, like a die-cut vinyl sticker.
```

**Техблок** — тот же, что в основной части.

---

## Герои карточек (шаги 12–14)

Крупные сюжетные картинки, 640×400, показываются на 150–190px.

| Шаг | Файл | Subject |
|---|---|---|
| 12 | `hero-progress.png` | `a striped rocket flying upward past two small clouds, leaving a curly trail` |
| 13 | `hero-weekly.png` | `a bar chart made of rounded candy-colored blocks with a smiling sun above it` |
| 14 | `hero-quick.png` | `an open treasure chest with stars and sparkles floating out of it` |

---

## Угловой декор (шаги 15–22)

Мелкие спрайты, **256×256** каждый (радуга и холм — 512×256). Лежат в
углах карточек и частично выходят за край, поэтому композиция должна
быть смещена к одному краю, а не отцентрована.

**Дописать в техблок для этих восьми:** `Composition anchored to one
edge, not centered — this is a corner sticker that will bleed off the
edge of a card.`

| Шаг | Файл | Размер | Subject |
|---|---|---|---|
| 15 | `decor-flowers-left.png` | 256×256 | `a cluster of three daisies and two leaves, growing from the lower left corner` |
| 16 | `decor-flowers-right.png` | 256×256 | `a cluster of two round flowers and a leafy stem, growing from the lower right corner` |
| 17 | `decor-cloud-small.png` | 256×256 | `a single small puffy cloud with a smiling face` |
| 18 | `decor-cloud-big.png` | 256×256 | `a large puffy cloud, no face, two small sparkles beside it` |
| 19 | `decor-rainbow.png` | 512×256 | `a rainbow arc with a puffy cloud at each end` |
| 20 | `decor-hill.png` | 512×256 | `a rolling grassy hill with two tiny flowers on it` |
| 21 | `decor-mushroom.png` | 256×256 | `a spotted mushroom with a smiling face and two blades of grass` |
| 22 | `decor-stars.png` | 256×256 | `a loose cluster of five four-pointed stars of different sizes` |

---

## Волны-разделители (шаги 23–24)

Широкие полосы вдоль низа карточки, **1024×256**.

**Дописать в техблок для этих двух:** `A horizontal band, full width,
flat on the left and right edges so it can tile. Wave shapes stacked
horizontally.`

| Шаг | Файл | Subject |
|---|---|---|
| 23 | `wave-color.png` | `stacked wavy stripes in coral, orange, gold, green and lavender` |
| 24 | `wave-mono.png` | `stacked wavy stripes in two tones of cream, subtle` |

---

## Микрозвёзды НЕ генерируем

Четырёхлучевые звёздочки и точки по 10–18px рисуются инлайновым SVG:
их по 3–6 на карточку, они одноцветные и должны краситься акцентом
домена. Картинкой это было бы 20 лишних запросов и невозможность
перекрасить.

## Про вес

24 картинки в скине — это уже не 250 КБ. Реалистичная оценка 400–450 КБ.
Мелкий декор жмётся хорошо (1–4 КБ на спрайт), основной вес по-прежнему
на четырёх пустых состояниях и героях. Сжимать той же командой:
палитра 200, масштаб 1.0.
