"""On-screen approximation of the sheet as it will come off the printer.

Sticker outlines and field positions are exact; text is a screen font rather
than the printer's, so treat it as indicative. Nothing leaves the machine.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from .config import Config
from .zpl import LabelText, feeds

PAPER = "#ffffff"
INK = "#111111"
EDGE = "#aab3bb"
CUT = "#cfd6dc"
BACKING = "#e6eaee"
BLANK_TEXT = "#b3bcc4"


def _font(px: float) -> tkfont.Font:
    return tkfont.Font(family="Helvetica", size=-max(6, round(px)))


def _shrink_to_fit(canvas: tk.Canvas, item: int, max_px: float, px: float) -> None:
    """Condense the screen font until the string fits, mirroring the auto-fit
    the ZPL generator does with the printer's narrower condensed face."""
    while px > 6:
        x0, _, x1, _ = canvas.bbox(item)
        if x1 - x0 <= max_px:
            return
        px -= 0.5
        canvas.itemconfigure(item, font=_font(px))


def draw(canvas: tk.Canvas, slots: list[LabelText | None], cfg: Config,
         target_width_px: int = 640) -> None:
    canvas.delete("all")
    scale = max(0.5, target_width_px / cfg.total_width_dots)

    def s(dots: float) -> float:
        return dots * scale

    sheet = feeds(slots, cfg) if slots else [[None] * cfg.per_feed]
    feed_stride = s(cfg.feed_h_dots) + s(cfg.mm(cfg.feed_gap_mm))
    height = feed_stride * len(sheet) + 8
    canvas.configure(bg=BACKING, highlightthickness=0,
                     scrollregion=(0, 0, s(cfg.total_width_dots) + 8, height))

    for f, feed in enumerate(sheet):
        top = 4 + f * feed_stride

        # Each column is a separate 38 x 25 mm label with liner showing between
        # them, so draw the labels individually rather than one wide block.
        for col in range(cfg.columns):
            cx = 4 + s(cfg.sticker_origin(col)[0])
            canvas.create_rectangle(cx, top, cx + s(cfg.sticker_w_dots),
                                    top + s(cfg.feed_h_dots),
                                    fill=PAPER, outline=EDGE)
            for r in range(1, cfg.rows):
                # The slit: no space across it, so draw a cut line not a gap.
                cy = top + s(r * (cfg.sticker_h_dots + cfg.mm(cfg.row_gap_mm)))
                canvas.create_line(cx, cy, cx + s(cfg.sticker_w_dots),
                                   cy, fill=CUT, dash=(3, 2))

        for index in range(cfg.per_feed):
            ox, oy = cfg.sticker_origin(index)
            x0, y0 = 4 + s(ox), top + s(oy)
            w, h = s(cfg.sticker_w_dots), s(cfg.sticker_h_dots)

            label = feed[index] if index < len(feed) else None
            if label is None:
                canvas.create_text(x0 + w / 2, y0 + h / 2, text="blank",
                                   font=_font(s(16)), fill=BLANK_TEXT)
                continue

            pad = s(cfg.mm(cfg.pad_mm))
            usable = s(cfg.usable_w_dots)
            name_y = cfg.name_y + (cfg.name_h_max - label.name_h) // 2
            id_y = cfg.id_y + (cfg.id_h_max - label.id_h) // 2

            px = s(label.name_h)
            item = canvas.create_text(x0 + pad, y0 + s(name_y), text=label.name,
                                      anchor="nw", font=_font(px), fill=INK)
            _shrink_to_fit(canvas, item, usable, px)

            px = s(label.id_h)
            item = canvas.create_text(x0 + pad, y0 + s(id_y), text=label.sex_age,
                                      anchor="nw", font=_font(px), fill=INK)
            _shrink_to_fit(canvas, item, usable * 0.35, px)

            px = s(label.id_h)
            item = canvas.create_text(x0 + pad + usable, y0 + s(id_y),
                                      text=label.prno, anchor="ne",
                                      font=_font(px), fill=INK)
            _shrink_to_fit(canvas, item, usable * 0.62, px)
