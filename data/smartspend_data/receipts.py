"""Render receipt dicts to photo-like JPEGs for Gemini multimodal parsing."""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_FONT_CANDIDATES = [
    "DejaVuSansMono.ttf", "consola.ttf", "cour.ttf", "LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "C:/Windows/Fonts/consola.ttf",
]


def _font(size: int) -> ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


WIDTH = 42  # characters per receipt line


def _lines(r: dict) -> list[tuple[str, bool]]:
    def row(left: str, right: str) -> str:
        return left[: WIDTH - len(right) - 1].ljust(WIDTH - len(right)) + right

    out = [(r["merchant_name"].upper().center(WIDTH), True)]
    if r.get("address"):
        out.append((r["address"].center(WIDTH), False))
    out += [("", False), (row(r["receipt_date"], r["receipt_time"]), False), ("-" * WIDTH, False)]
    for li in r["line_items"]:
        desc = li["description"] if li["quantity"] == 1 else f'{li["quantity"]} @ {li["unit_price"]:.2f} {li["description"]}'
        out.append((row(desc, f'{li["amount"]:.2f}'), False))
    out += [("-" * WIDTH, False), (row("SUBTOTAL", f'{r["subtotal"]:.2f}'), False), (row("TAX", f'{r["tax"]:.2f}'), False)]
    if r.get("tip"):
        out.append((row("TIP", f'{r["tip"]:.2f}'), False))
    out += [
        (row("TOTAL", f'{r["total"]:.2f}'), False),
        ("", False),
        (row("VISA ************" + r["card_last4"], f'{r["total"]:.2f}'), False),
        ("", False),
        ("THANK YOU FOR SHOPPING!".center(WIDTH), False),
    ]
    return out


def render(r: dict, path: Path, *, seed: int = 0) -> None:
    rng = random.Random(seed)
    font, bold = _font(18), _font(22)
    lines = _lines(r)
    line_h = 26
    w, h = 560, 60 + line_h * len(lines)
    paper = Image.new("RGB", (w, h), (250, 248, 240))
    draw = ImageDraw.Draw(paper)
    y = 30
    for text, strong in lines:
        draw.text((24, y), text, fill=(30, 30, 30), font=bold if strong else font)
        y += line_h

    # Make it look photographed: background, slight rotation, blur, JPEG.
    canvas = Image.new("RGB", (w + 120, h + 120), (rng.randint(90, 130),) * 3)
    canvas.paste(paper, (60, 60))
    canvas = canvas.rotate(rng.uniform(-2.0, 2.0), resample=Image.BICUBIC, fillcolor=(100, 100, 100))
    canvas = canvas.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.2, 0.7)))
    canvas.save(path, "JPEG", quality=rng.randint(70, 88))
