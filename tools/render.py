"""Build the Varrenn passport plate locally with Pillow and NumPy."""

from datetime import date
from functools import lru_cache
from math import cos, pi, sin
from pathlib import Path
from random import Random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ARTWORK = ROOT / "artwork"
FONTS = Path("/usr/share/fonts/truetype")
SCALE = 3
PAGE = (466, 636)
INK = "#203943"
TEAL = "#416e70"
RULE = "#81a09b"
COUNTRY = "XVN"
DOCUMENT = "VN0286417"
SURNAME = "VOSSAIRE"
GIVEN = "ILENNA"
BIRTH = date(1990, 9, 8)
ISSUED = date(2025, 2, 12)
EXPIRES = date(2035, 2, 12)
SEX = "F"
CAPITAL = "MIRREN QUAY"
AUTHORITY = "Civil Registry of Varrenn"
PORTRAIT = ARTWORK / "ilenna-vossaire.jpg"

# Stamp order is left to right within each date, then down the page.
JOURNEY = (
    (date(2025, 4, 17), "VARRENN", "SILL GATE", "DEPARTURE", "07", -4.4),
    (date(2025, 4, 17), "TAVREN", "VELIN PIER", "ARRIVAL", "12", 6.7),
    (date(2025, 4, 19), "TAVREN", "RIVER LOCK", "DEPARTURE", "16", 3.0),
    (date(2025, 4, 19), "ORDEL", "LOAM FERRY", "ARRIVAL", "05", -5.0),
    (date(2025, 4, 22), "ORDEL", "BELL QUAY", "DEPARTURE", "03", -3.6),
    (date(2025, 4, 22), "VARRENN", CAPITAL, "ARRIVAL", "02", 5.4),
)

MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()


def dated(day):
    return f"{day.day:02d} {MONTHS[day.month - 1]} {day.year}"


def mrz_check(field):
    alphabet = "<0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    weights = (7, 3, 1)
    return str(sum(max(0, alphabet.index(char) - 1) * weights[i % 3]
                   for i, char in enumerate(field)) % 10)


def mrz_lines():
    birth = BIRTH.strftime("%y%m%d")
    expiry = EXPIRES.strftime("%y%m%d")
    number = DOCUMENT + mrz_check(DOCUMENT)
    personal = "<" * 14
    personal_field = personal + mrz_check(personal)
    first = f"P<{COUNTRY}{SURNAME}<<{GIVEN}".ljust(44, "<")
    second = f"{number}{COUNTRY}{birth}{mrz_check(birth)}{SEX}{expiry}{mrz_check(expiry)}{personal_field}"
    composite = second[:10] + second[13:20] + second[21:43]
    return first, second + mrz_check(composite)


def validate_document():
    first, second = mrz_lines()
    assert len(first) == len(second) == 44
    assert ISSUED < JOURNEY[0][0] <= JOURNEY[-1][0] < EXPIRES
    location = "VARRENN"
    for departure, arrival in zip(JOURNEY[::2], JOURNEY[1::2]):
        assert departure[1] == location and departure[3] == "DEPARTURE"
        assert departure[0] == arrival[0] and arrival[3] == "ARRIVAL"
        location = arrival[1]
    assert location == "VARRENN"
    assert [event[0] for event in JOURNEY] == sorted(event[0] for event in JOURNEY)


def pixels(*coords):
    return tuple(round(value * SCALE) for value in coords)


def canvas(size, fill=(0, 0, 0, 0)):
    return Image.new("RGBA", pixels(*size), fill)


@lru_cache
def face(kind, size):
    files = {
        "serif": "dejavu/DejaVuSerif.ttf",
        "sans": "ubuntu/UbuntuSans[wdth,wght].ttf",
        "medium": "ubuntu/UbuntuSans[wdth,wght].ttf",
        "bold": "ubuntu/UbuntuSans[wdth,wght].ttf",
        "mono": "ubuntu/UbuntuSansMono[wght].ttf",
        "italic": "ubuntu/UbuntuSans-Italic[wdth,wght].ttf",
    }
    font = ImageFont.truetype(FONTS / files[kind], round(size * SCALE))
    if kind in {"medium", "bold"}:
        font.set_variation_by_axes([100, {"medium": 620, "bold": 760}[kind]])
    return font


def type_at(draw, x, y, value, size, color=INK, kind="sans", align="l", tracking=0):
    font = face(kind, size)
    start_x, start_y = pixels(x, y)
    if tracking == 0:
        draw.text((start_x, start_y), value, font=font, fill=color, anchor=align + "s")
        return
    widths = [font.getlength(letter) + tracking * SCALE for letter in value]
    length = sum(widths) - tracking * SCALE
    start_x -= {"l": 0, "m": length / 2, "r": length}[align]
    for letter, advance in zip(value, widths):
        draw.text((start_x, start_y), letter, font=font, fill=color, anchor="ls")
        start_x += advance


def line(draw, points, color, width=0.65):
    draw.line([pixels(*point) for point in points], fill=color, width=max(1, round(width * SCALE)))


def box(draw, coords, fill=None, stroke=None, width=0.65, radius=0):
    if radius:
        draw.rounded_rectangle(pixels(*coords), radius=radius * SCALE, fill=fill, outline=stroke,
                               width=max(1, round(width * SCALE)))
    else:
        draw.rectangle(pixels(*coords), fill=fill, outline=stroke, width=max(1, round(width * SCALE)))


def oval(draw, coords, stroke, width=0.65):
    draw.ellipse(pixels(*coords), outline=stroke, width=max(1, round(width * SCALE)))


def rosette(draw, x, y, rx, ry, rings, color, petals=12, angle=0):
    """Interlace wave-modulated rings, with a second harmonic in each strand."""
    theta = np.linspace(0, 2 * pi, 385)
    for i in range(rings):
        offset = i * 0.33
        radius = 0.73 + 0.14 * cos(offset) + 0.102 * np.cos(petals * theta + offset)
        radius += 0.038 * np.sin((petals * 2) * theta - offset)
        a = rx * radius * np.cos(theta)
        b = ry * radius * np.sin(theta)
        points = zip(x + a * cos(angle) - b * sin(angle), y + a * sin(angle) + b * cos(angle))
        line(draw, points, color, 0.34)


def tides(draw, x0, x1, y, count, spacing, color, amplitude=8, wavelength=84, phase=0):
    for index in range(count):
        points = []
        for x in range(int(x0), int(x1) + 1, 2):
            offset = phase + index * 0.145
            height = amplitude * sin(x / wavelength + offset)
            height += amplitude * 0.47 * sin(x / (wavelength * 0.44) - offset * 0.55)
            points.append((x, y + index * spacing + height))
        line(draw, points, color, 0.34)


def crest(draw, x, y, size, color, ring=False):
    def place(points):
        return [(x + a * size, y + b * size) for a, b in points]

    if ring:
        oval(draw, (x - size * 0.54, y - size * 0.54, x + size * 0.54, y + size * 0.54), color, 0.85)
        oval(draw, (x - size * 0.46, y - size * 0.46, x + size * 0.46, y + size * 0.46), color, 0.45)
    line(draw, place([(-.34, 0), (.34, 0)]), color, size * .026)
    for direction in (-1, 1):
        for width in (0.27, 0.155):
            points = [(width * cos(t), direction * width * 0.90 * sin(t))
                      for t in np.linspace(0, pi, 45)]
            line(draw, place(points), color, size * .033)
    for cx in (-.34, .34):
        draw.ellipse(pixels(x + (cx - .023) * size, y - .023 * size,
                            x + (cx + .023) * size, y + .023 * size), fill=color)


def paper(right=False):
    width, height = pixels(*PAGE)
    xx = np.arange(width, dtype=np.float32)[None, :] / SCALE
    yy = np.arange(height, dtype=np.float32)[:, None] / SCALE
    rng = np.random.default_rng(518 if right else 231)
    noise = rng.normal(0, 0.64, (height, width))
    clouds = np.asarray(Image.fromarray(rng.integers(110, 145, (32, 24), dtype=np.uint8))
                        .resize((width, height), Image.Resampling.BICUBIC), dtype=np.float32)
    drift = (clouds - 127) * 0.21 + noise
    blue_field = np.exp(-((xx - (354 if right else 92)) / 256) ** 2 - ((yy - 320) / 220) ** 2)
    gold_field = np.exp(-((xx - (120 if right else 330)) / 180) ** 2 - ((yy - 200) / 175) ** 2)
    rgb = np.empty((height, width, 3), dtype=np.uint8)
    for i, (base, blue, gold) in enumerate(zip((243, 238, 218), (-13, -1, 7), (6, 2, -5))):
        rgb[:, :, i] = np.clip(base + blue_field * blue + gold_field * gold + drift, 0, 255)
    layer = Image.fromarray(rgb).convert("RGBA")
    flecks = canvas(PAGE)
    draw = ImageDraw.Draw(flecks)
    random = Random(209 if right else 789)
    for i in range(860):
        x, y = random.uniform(0, PAGE[0]), random.uniform(0, PAGE[1])
        dx, dy = random.uniform(0.35, 3.0), random.uniform(-1.1, 1.1)
        color = (65, 121, 118, random.randint(8, 39)) if i % 4 else (158, 86, 62, 38)
        line(draw, [(x, y), (x + dx * 0.55, y + dy * 0.23), (x + dx, y + dy)], color, 0.3)
    return Image.alpha_composite(layer, flecks)


def security_ground(page, right=False):
    layer = canvas(PAGE)
    draw = ImageDraw.Draw(layer)
    tides(draw, 12, 454, 40, 18, 4.3, (70, 130, 130, 48), amplitude=14, wavelength=67)
    tides(draw, 12, 454, 455, 22, 5.3, (73, 132, 120, 45), amplitude=20, wavelength=72, phase=1.7)
    if right:
        for y in range(135, 538, 86):
            tides(draw, 28, 443, y, 9, 3.9, (72, 129, 125, 29), amplitude=13,
                  wavelength=58, phase=y * .016)
        rosette(draw, 245, 314, 214, 176, 23, (100, 132, 112, 37), petals=10, angle=-0.13)
        rosette(draw, 242, 314, 165, 210, 17, (148, 112, 69, 33), petals=8)
        crest(draw, 245, 312, 146, (96, 128, 119, 27), True)
    else:
        rosette(draw, 126, 287, 150, 182, 22, (70, 128, 121, 41), petals=11)
        rosette(draw, 322, 349, 140, 139, 16, (135, 110, 62, 36), petals=9, angle=0.3)
        tides(draw, 14, 451, 238, 28, 3.8, (61, 125, 130, 33), amplitude=22, wavelength=75)
    for x in (12, 16, 449, 453):
        line(draw, [(x, 22), (x, 614)], (85, 131, 125, 67), .38)
    for x in (16, 450):
        for y in range(33, 610, 11):
            line(draw, [(x - 2, y - 1.7), (x, y), (x + 2, y - 1.7)], (72, 113, 111, 58), .4)
    return Image.alpha_composite(page, layer)


def top_rule(draw, start, end, y):
    line(draw, [(start, y), (end, y)], TEAL, 1.25)
    line(draw, [(start, y + 3.6), (end, y + 3.6)], RULE, 0.42)


def field(draw, x, y, caption, value, size=16):
    type_at(draw, x, y, caption, 8.35, TEAL, "medium", tracking=.34)
    type_at(draw, x, y + 20, value, size, INK, "medium", tracking=.28)


def draw_portrait(page):
    with Image.open(PORTRAIT) as source:
        photo = portrait_ink(source.convert("RGB"))
    photo = ImageOps.fit(photo, pixels(159, 204), Image.Resampling.LANCZOS)
    page.alpha_composite(photo.convert("RGBA"), pixels(31, 192))
    layer = canvas(PAGE)
    draw = ImageDraw.Draw(layer)
    for y in range(194, 396, 3):
        line(draw, [(31, y), (189, y - .9)], (38, 69, 72, 13), .33)
    box(draw, (31, 192, 190, 396), stroke=(35, 63, 60, 168), width=.72)
    for x in (29, 192):
        for y in (190, 398):
            dx, dy = (-1 if x > 100 else 1), (-1 if y > 300 else 1)
            line(draw, [(x + 8 * dx, y), (x, y), (x, y + 8 * dy)], (41, 79, 72, 220), 1.15)
    tides(draw, 31, 208, 356, 14, 2.85, (194, 227, 207, 117), amplitude=7, wavelength=39, phase=.4)
    crest(draw, 167, 371, 37, (222, 241, 219, 154), True)
    return Image.alpha_composite(page, layer)


def portrait_ink(photo):
    luminance = ImageOps.grayscale(photo)
    cool = ImageOps.colorize(luminance, "#203139", "#e9e3cf")
    return Image.blend(cool, photo, 0.30)


def ghost_portrait(page):
    with Image.open(PORTRAIT) as original:
        image = ImageOps.fit(original.convert("L"), pixels(48, 61), Image.Resampling.LANCZOS)
    grain = ImageOps.invert(image).point(lambda v: round(max(0, v - 24) * 0.63))
    for y in range(grain.height):
        if y % 6 in (3, 4, 5):
            grain.paste(0, (0, y, grain.width, y + 1))
    copy = Image.new("RGBA", grain.size, "#486f6d")
    copy.putalpha(grain)
    page.alpha_composite(copy, pixels(377, 491))


def signature(draw, x, y):
    # A short digitized flourish, drawn as cubic pen strokes.
    strokes = [
        ((0, 16), (8, 11), (14, -12), (18, -14)),
        ((18, -14), (27, -20), (18, 5), (10, 14)),
        ((10, 14), (4, 21), (25, 17), (31, 5)),
        ((31, 5), (36, -3), (27, 20), (36, 11)),
        ((36, 11), (47, 0), (36, 21), (48, 11)),
        ((48, 11), (53, 3), (50, 18), (61, 11)),
        ((61, 11), (69, -8), (79, 19), (85, 5)),
        ((86, 0), (93, 16), (92, 18), (98, -1)),
        ((98, -1), (113, -24), (102, 13), (111, 11)),
        ((111, 11), (125, -2), (111, 24), (132, 9)),
        ((9, 20), (42, 16), (101, 24), (135, 10)),
    ]
    for points in strokes:
        a, b, c, d = np.array(points)
        t = np.linspace(0, 1, 31)[:, None]
        pts = (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t ** 2 * c + t ** 3 * d
        line(draw, pts + (x, y), "#354a50", .88)


def harbor_engraving(page, x, y):
    """Engrave the registry's quays and their reflection above the OCR field."""
    layer = canvas(PAGE)
    draw = ImageDraw.Draw(layer)
    water = (55, 114, 114, 90)
    crest_ink = (51, 102, 107, 131)
    rand = Random(73)
    skyline = [(5, 19, 14), (27, 24, 25), (53, 17, 16), (72, 33, 28), (109, 18, 16),
               (129, 33, 21), (166, 38, 29), (210, 24, 17), (242, 27, 26), (274, 20, 17)]
    for at, w, h in skyline:
        left = x + at
        ceiling = y - h
        gable = ceiling - w * .28
        line(draw, [(left, y), (left, ceiling), (left + w / 2, gable),
                    (left + w, ceiling), (left + w, y)], crest_ink, .66)
        for offset in range(2, w - 1, 3):
            elevation = max(ceiling, gable + abs(offset - w / 2) * .55)
            line(draw, [(left + offset, elevation + 1.45), (left + offset, y)], water, .33)
        for offset in range(5, w - 2, 7):
            for level in range(5, h - 4, 7):
                line(draw, [(left + offset, ceiling + level), (left + offset, ceiling + level + 2.4)],
                     crest_ink, .65)
        for offset in range(1, w, 4):
            depth = (1 - abs(2 * offset / w - 1) * .4) * h * .51 + rand.uniform(-3, 3)
            line(draw, [(left + offset, y + 2), (left + offset + rand.uniform(-3, 3), y + depth)],
                 water, .35)
    tower = x + 190
    line(draw, [(tower - 6, y - 27), (tower - 5, y - 48), (tower + 4, y - 48),
                (tower + 6, y - 28)], crest_ink)
    line(draw, [(tower - 7, y - 48), (tower, y - 54), (tower + 6, y - 48)], crest_ink)
    line(draw, [(tower - 6, y - 43), (tower + 5, y - 43)], crest_ink, 1.0)
    line(draw, [(x - 7, y), (x + 305, y)], crest_ink)
    tides(draw, x - 7, x + 315, y + 4, 10, 1.5, (55, 114, 114, 71),
          amplitude=2.7, wavelength=39, phase=0.6)
    return Image.alpha_composite(page, layer)


def left_page():
    page = security_ground(paper())
    page = harbor_engraving(page, 42, 529)
    page = draw_portrait(page)
    ghost_portrait(page)
    draw = ImageDraw.Draw(page)
    type_at(draw, 31, 43, "RÉPUBLIQUE DE VARRENN", 10.1, TEAL, "medium", tracking=1.7)
    type_at(draw, 30, 77, "REPUBLIC OF VARRENN", 25, INK, "serif", tracking=.36)
    type_at(draw, 29, 113, "PASSPORT", 31, INK, "serif", tracking=1.5)
    type_at(draw, 233, 111, "PASSEPORT", 12, TEAL, "medium", tracking=1.6)
    crest(draw, 412, 78, 46, TEAL, True)
    top_rule(draw, 30, 438, 127)

    field(draw, 31, 150, "TYPE", "P", 17)
    field(draw, 121, 150, "CODE / CODE PAYS", COUNTRY, 17)
    field(draw, 279, 150, "PASSPORT NO. / N° DU PASSEPORT", DOCUMENT, 18)

    x = 211
    field(draw, x, 201, "SURNAME / NOM", SURNAME, 20)
    field(draw, x, 246, "GIVEN NAMES / PRÉNOMS", GIVEN, 20)
    field(draw, x, 291, "NATIONALITY / NATIONALITÉ", "VARRENNER", 16.5)
    field(draw, x, 335, "DATE OF BIRTH / NAISSANCE", dated(BIRTH), 15)
    field(draw, 396, 335, "SEX / SEXE", SEX, 15)
    field(draw, x, 379, "PLACE OF BIRTH / LIEU DE NAISSANCE", CAPITAL, 16.5)
    field(draw, x, 423, "ISSUED / DÉLIVRÉ LE", dated(ISSUED), 14.2)
    field(draw, 327, 423, "EXPIRES / EXPIRE LE", dated(EXPIRES), 14.2)
    field(draw, x, 469, "AUTHORITY / AUTORITÉ", AUTHORITY, 14.5)

    type_at(draw, 31, 418, "SIGNATURE OF HOLDER / TITULAIRE", 8.1, TEAL, "medium", tracking=.30)
    signature(draw, 32, 444)
    line(draw, [(31, 465), (180, 465)], RULE, .57)
    type_at(draw, 437, 535, "02", 9, TEAL, "mono", align="r")
    type_at(draw, 31, 550, "VARRENN  ·  MIRREN QUAY  ·  CIVIL REGISTRY", 6.8, TEAL, "medium", tracking=.76)

    box(draw, (0, 558, PAGE[0] - 1, 635), fill="#f4efdc")
    line(draw, [(0, 559), (465, 559)], "#aab9a8", 1.0)
    for y, value in zip((591, 616), mrz_lines()):
        for i, char in enumerate(value):
            type_at(draw, 29 + 9.26 * i, y, char, 15.25, "#182c32", "mono")
    return page


STAMP_INKS = {"VARRENN": (37, 92, 86), "TAVREN": (130, 56, 51), "ORDEL": (82, 63, 109)}
STAMP_NAMES = {"VARRENN": "VARRENN", "TAVREN": "STATE OF TAVREN", "ORDEL": "REPUBLIC OF ORDEL"}


def arrow(draw, x, y, ink, right):
    sign = 1 if right else -1
    line(draw, [(x - 5 * sign, y), (x + 5 * sign, y)], ink, 1.25)
    line(draw, [(x + sign, y - 3.5), (x + 5 * sign, y), (x + sign, y + 3.5)], ink, 1.25)


def stamp(event, number):
    day, country, post, direction, serial, tilt = event
    tint = STAMP_INKS[country]
    ink = (*tint, 238)
    sheet = canvas((204, 112))
    draw = ImageDraw.Draw(sheet)
    if country == "TAVREN":
        oval(draw, (5, 4, 199, 107), ink, 1.85)
        oval(draw, (9, 8, 195, 103), ink, .62)
    elif country == "ORDEL":
        outer = [(17, 5), (186, 5), (197, 15), (197, 94), (186, 104),
                 (17, 104), (7, 94), (7, 15), (17, 5)]
        line(draw, outer, ink, 1.9)
        line(draw, [(15, 43), (189, 43)], ink, .57)
        line(draw, [(15, 74), (189, 74)], ink, .57)
    else:
        box(draw, (6, 6, 198, 104), stroke=ink, radius=8, width=1.85)
        box(draw, (10, 10, 194, 100), stroke=ink, radius=6, width=.48)
        crest(draw, 29, 28, 16, ink, True)
        line(draw, [(15, 42), (189, 42)], ink, .56)
        line(draw, [(15, 74), (189, 74)], ink, .56)

    oval_shift = 3 if country == "TAVREN" else 0
    name_size = 12.5 if country == "TAVREN" else 13.2
    type_at(draw, 102, 27 + oval_shift, STAMP_NAMES[country], name_size, ink, "bold", "m", 1.06)
    type_at(draw, 102, 39 + oval_shift, post, 9.3, ink, "medium", "m", 1.0)
    type_at(draw, 102, 65, dated(day), 20.6, ink, "mono", "m")
    type_at(draw, 102, 89, direction, 13.6, ink, "bold", "m", 1.2)
    arrow(draw, 48, 84, ink, direction == "ARRIVAL")
    type_at(draw, 156, 88, serial, 8.8, ink, "mono", "m")

    # Uneven pressure and tiny skips in the ink, with intact date characters.
    rgba = np.array(sheet)
    height, width = rgba.shape[:2]
    rng = np.random.default_rng(1703 + number)
    texture = np.asarray(Image.fromarray(rng.integers(145, 255, (11, 15), dtype=np.uint8))
                         .resize((width, height), Image.Resampling.BICUBIC))
    pressure = 0.58 + texture.astype(np.float32) / 550
    pressure[rng.random((height, width)) < .017] *= .35
    rgba[:, :, 3] = (rgba[:, :, 3] * pressure).astype(np.uint8)
    return Image.fromarray(rgba).rotate(tilt, Image.Resampling.BICUBIC, expand=True)


def right_page():
    page = security_ground(paper(right=True), right=True)
    draw = ImageDraw.Draw(page)
    type_at(draw, 31, 43, "RÉPUBLIQUE DE VARRENN", 10.1, TEAL, "medium", tracking=1.7)
    type_at(draw, 30, 79, "VISAS", 36, INK, "serif", tracking=2.3)
    type_at(draw, 31, 111, "BORDER CONTROL  /  CONTRÔLE AUX FRONTIÈRES", 10.1, TEAL,
            "medium", tracking=.71)
    crest(draw, 412, 78, 46, TEAL, True)
    top_rule(draw, 30, 438, 127)

    positions = [(126, 207), (332, 204), (136, 326), (331, 322), (126, 443), (331, 447)]
    for number, (event, (x, y)) in enumerate(zip(JOURNEY, positions)):
        mark = stamp(event, number)
        page.alpha_composite(mark, (round(x * SCALE - mark.width / 2),
                                    round(y * SCALE - mark.height / 2)))

    panel = canvas(PAGE)
    draw = ImageDraw.Draw(panel)
    box(draw, (34, 521, 432, 590), fill=(232, 237, 215, 211), stroke=(56, 109, 105, 215), width=1.03)
    box(draw, (38, 525, 428, 586), stroke=(56, 109, 105, 125), width=.39)
    line(draw, [(95, 531), (95, 579)], (56, 109, 105, 146), .7)
    crest(draw, 66, 556, 38, (56, 106, 101, 206), True)
    type_at(draw, 107, 542, "ENTRY ENDORSEMENT / VISA D’ENTRÉE", 8.25, TEAL, "bold", tracking=.75)
    type_at(draw, 416, 542, "ART. 14", 8.6, TEAL, "mono", "r")
    type_at(draw, 107, 561, "ENTRY VIA WATER REFLECTIONS ONLY", 14.4, INK, "bold", tracking=.53)
    type_at(draw, 107, 577, "Bureau de Mirren Quay", 9.3, TEAL, "medium")
    type_at(draw, 416, 577, "22 APR 2025", 9.8, TEAL, "mono", "r")
    type_at(draw, 30, 611, DOCUMENT, 9, TEAL, "mono", tracking=1.0)
    type_at(draw, 438, 611, "03", 9, TEAL, "mono", "r")
    return Image.alpha_composite(page, panel)


def shade_and_trim(page, right):
    frame = np.array(page)
    width, height = PAGE
    x = np.arange(width * SCALE)[None, :] / SCALE
    y = np.arange(height * SCALE)[:, None] / SCALE
    distance = x if right else width - x
    gutter = 0.31 * np.exp(-distance / (11 if right else 9))
    ridge = 0.042 * np.exp(-((distance - 30) / 24) ** 2)
    softer = 0.025 * (y / height) + 0.018 * np.sin((x + y) / 190)
    edge = 0.035 * np.exp(-(width - distance) / 9)
    reflection = 0.00 if right else 0.028 * np.exp(-((y + .51 * x - 283) / 96) ** 2)
    shade = 1.005 - gutter - edge - softer + ridge + reflection
    frame[:, :, :3] = np.clip(frame[:, :, :3] * shade[:, :, None], 0, 255)
    alpha = Image.new("L", page.size)
    corners = (False, True, True, False) if right else (True, False, False, True)
    ImageDraw.Draw(alpha).rounded_rectangle((0, 0, page.width - 1, page.height - 1), 11 * SCALE,
                                           fill=255, corners=corners)
    frame[:, :, 3] = np.asarray(alpha)
    return Image.fromarray(frame)


def warp(page, quad):
    """Find the inverse perspective transform from four corresponding corners."""
    src = [(0, 0), (page.width - 1, 0), (page.width - 1, page.height - 1), (0, page.height - 1)]
    rows, values = [], []
    for dest, (u, v) in zip(quad, src):
        x, y = pixels(*dest)
        rows.extend(((x, y, 1, 0, 0, 0, -u * x, -u * y), (0, 0, 0, x, y, 1, -v * x, -v * y)))
        values.extend((u, v))
    coeffs = np.linalg.solve(rows, values)
    return page.transform(pixels(1024, 1024), Image.Transform.PERSPECTIVE, coeffs,
                          Image.Resampling.BICUBIC)


def desktop():
    rng = np.random.default_rng(397)
    axis = np.arange(1024, dtype=np.float32)
    x, y = axis[None, :], axis[:, None]
    light = 25 * np.exp(-((x - 190) / 790) ** 2 - ((y - 190) / 660) ** 2)
    noise = rng.normal(0, 0.65, (1024, 1024))
    mottling = np.asarray(Image.fromarray(rng.integers(100, 160, (42, 58), dtype=np.uint8))
                         .resize((1024, 1024), Image.Resampling.BICUBIC), dtype=np.float32)
    noise += 0.071 * (mottling - 128)
    base = np.dstack([start + light + noise for start in (33, 46, 50)]).clip(0, 255)
    return Image.fromarray(base.astype(np.uint8)).resize(pixels(1024, 1024), Image.Resampling.BICUBIC).convert("RGBA")


def book_polygon(draw, points, fill):
    draw.polygon([pixels(*point) for point in points], fill=fill)


def physical_book():
    left_quad = [(39, 192), (510, 177), (511, 828), (29, 823)]
    right_quad = [(509.5, 177), (981, 184), (995, 810), (510.5, 828)]
    backdrop = desktop()
    silhouette = [(34, 189), (511, 183), (986, 182), (1002, 810), (1002, 820),
                  (997, 829), (989, 834), (509, 848), (37, 839), (26, 836), (21, 823)]
    for offset_x, offset_y, blur, opacity in ((3, 18, 18, 132), (1, 7, 6, 143), (0, 2, 2, 178)):
        cast = canvas((1024, 1024))
        book_polygon(ImageDraw.Draw(cast), [(x + offset_x, y + offset_y) for x, y in silhouette],
                     (10, 21, 22, opacity))
        backdrop = Image.alpha_composite(backdrop, cast.filter(ImageFilter.GaussianBlur(blur * SCALE)))

    stack = canvas((1024, 1024))
    draw = ImageDraw.Draw(stack)
    book_polygon(draw, silhouette, "#203b3d")
    line(draw, [(24, 809), (24, 827), (31, 834), (506, 845), (988, 832), (997, 826)], "#557776", 1.2)
    colors = ("#908d75", "#b6ad90", "#a4a083", "#cdc1a5", "#ada58c", "#d6c9ac")
    outline = [(34, 197), (510, 183), (985, 187), (999, 812),
               (995, 819), (984, 824), (510, 838), (40, 831), (27, 823)]
    for i, color in enumerate(colors):
        book_polygon(draw, [(x, y - i * 1.82) for x, y in outline], color)
    line(draw, [(37, 834), (509, 842), (990, 828)], "#78908b", .75)
    backdrop = Image.alpha_composite(backdrop, stack)

    left = warp(shade_and_trim(left_page(), False), left_quad)
    right = warp(shade_and_trim(right_page(), True), right_quad)
    backdrop = Image.alpha_composite(Image.alpha_composite(backdrop, left), right)

    binding = canvas((1024, 1024))
    draw = ImageDraw.Draw(binding)
    line(draw, [(509.5, 178), (510.6, 825)], (32, 52, 50, 124), 1.08)
    line(draw, [(511.8, 180), (512.4, 825)], (240, 227, 188, 109), .55)
    for y in (230, 329, 423, 524, 625, 724, 785):
        x = 510 + (y - 176) / 652
        oval(draw, (x - 2.2, y - 1.8, x + 2.4, y + 1.9), (46, 63, 58, 145), .56)
        line(draw, [(x - 1.6, y + .7), (x + .5, y - .7), (x + 2, y + .3)],
             (219, 208, 168, 191), .64)
    return Image.alpha_composite(backdrop, binding)


def main():
    validate_document()
    image = physical_book().convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS)
    target = ARTWORK / "varrenn.png"
    image.save(target, optimize=True)
    print(f"{target.name}: {image.width} × {image.height}, {target.stat().st_size:,} bytes")
    print(*mrz_lines(), sep="\n")


if __name__ == "__main__":
    main()
