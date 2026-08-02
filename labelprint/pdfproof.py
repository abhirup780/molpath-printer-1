"""Render an actual-size PDF proof of the sheet.

Written as a minimal PDF generator rather than pulling in reportlab: it keeps
the app dependency-light, and it means a proof containing patient data is
produced entirely locally.

Label geometry and field positions are exact vectors at true size, so a proof
printed at 100% can be laid against the real stock to check alignment. Text is
indicative: the ZD230 uses a bold condensed face, so glyphs here are condensed
to the same width budget the app fits against.
"""

from __future__ import annotations

from pathlib import Path

from .config import Config
from .zpl import LabelText, feeds

PT_PER_MM = 72.0 / 25.4
A4 = (595.28, 841.89)

# Helvetica advance widths per 1000 em, ASCII 32..126.
_HELV = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278,
    278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584,
    584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556,
    833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278,
    278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222,
    500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500,
    500, 334, 260, 334, 584,
]


def _text_width(text: str, size: float) -> float:
    total = sum(_HELV[ord(c) - 32] if 32 <= ord(c) <= 126 else 556 for c in text)
    return total * size / 1000.0


def _esc(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


class _Page:
    """Collects PDF content-stream operators, in top-left millimetre coords."""

    def __init__(self, height_pt: float) -> None:
        self.h = height_pt
        self.ops: list[str] = []

    def _y(self, y_mm: float) -> float:
        return self.h - y_mm * PT_PER_MM

    def rect(self, x_mm, y_mm, w_mm, h_mm, fill=None, stroke=None, lw=0.4):
        x, w = x_mm * PT_PER_MM, w_mm * PT_PER_MM
        h = h_mm * PT_PER_MM
        y = self._y(y_mm) - h
        if fill:
            self.ops.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg")
        if stroke:
            self.ops.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG")
            self.ops.append(f"{lw:.2f} w")
        op = "B" if (fill and stroke) else ("f" if fill else "S")
        self.ops.append(f"{x:.3f} {y:.3f} {w:.3f} {h:.3f} re {op}")

    def text(self, x_mm, y_mm, text, size_pt, gray=0.0, align="l",
             max_width_mm: float | None = None):
        """y_mm is the text baseline, measured from the top of the page.

        `max_width_mm` condenses the glyphs to fit rather than overflowing. The
        ZD230's face is bold *condensed*, so Helvetica at its natural width
        overstates how much room the text needs; squeezing it to the width the
        app budgeted against is the honest approximation.
        """
        width = _text_width(text, size_pt)
        squeeze = 100.0
        if max_width_mm and width > max_width_mm * PT_PER_MM:
            squeeze = 100.0 * max_width_mm * PT_PER_MM / width
            width = max_width_mm * PT_PER_MM

        x = x_mm * PT_PER_MM
        if align == "c":
            x -= width / 2
        elif align == "r":
            x -= width
        self.ops.append(
            f"BT {gray:.3f} g /F1 {size_pt:.2f} Tf {squeeze:.2f} Tz "
            f"{x:.3f} {self._y(y_mm):.3f} Td ({_esc(text)}) Tj ET"
        )

    def line(self, x_mm, y_mm, w_mm, gray=0.75, dash=True):
        self.ops.append(f"{gray:.3f} G 0.3 w" + (" [1.2 1.2] 0 d" if dash else ""))
        y = self._y(y_mm)
        self.ops.append(f"{x_mm * PT_PER_MM:.3f} {y:.3f} m "
                        f"{(x_mm + w_mm) * PT_PER_MM:.3f} {y:.3f} l S")
        if dash:
            self.ops.append("[] 0 d")

    def stream(self) -> str:
        return "\n".join(self.ops)


def _draw_label(page: _Page, label: LabelText | None, cfg: Config,
                x_mm: float, y_mm: float) -> None:
    """One sticker, its top-left corner at (x_mm, y_mm)."""
    w, h = cfg.sticker_width_mm, cfg.sticker_height_mm
    if label is None:
        page.text(x_mm + w / 2, y_mm + h / 2 + 1.0, "blank", 5.5, gray=0.72,
                  align="c")
        return

    d2mm = 1.0 / cfg.dots_per_mm
    pad = cfg.mm(cfg.pad_mm) * d2mm
    usable_mm = cfg.usable_w_dots * d2mm

    name_y = cfg.name_y + (cfg.name_h_max - label.name_h) // 2
    id_y = cfg.id_y + (cfg.id_h_max - label.id_h) // 2

    # ^FO places the top of the cell; PDF text sits on its baseline, so drop by
    # the character height.
    page.text(x_mm + pad, y_mm + (name_y + label.name_h) * d2mm, label.name,
              label.name_h * d2mm * PT_PER_MM, max_width_mm=usable_mm)
    page.text(x_mm + pad, y_mm + (id_y + label.id_h) * d2mm, label.sex_age,
              label.id_h * d2mm * PT_PER_MM, max_width_mm=usable_mm * 0.35)
    page.text(x_mm + pad + usable_mm, y_mm + (id_y + label.id_h) * d2mm,
              label.prno, label.id_h * d2mm * PT_PER_MM, align="r",
              max_width_mm=usable_mm * 0.62)


def _build_pdf(pages: list[_Page], size: tuple[float, float]) -> bytes:
    objects: list[bytes] = []

    def add(body: str) -> None:
        objects.append(body.encode("latin-1"))

    font_id = 3 + 2 * len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    add("<< /Type /Catalog /Pages 2 0 R >>")
    add(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
    for i, page in enumerate(pages):
        add(f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {size[0]:.2f} {size[1]:.2f}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {4 + 2 * i} 0 R >>")
        data = page.stream()
        add(f"<< /Length {len(data)} >>\nstream\n{data}\nendstream")
    add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        "/Encoding /WinAnsiEncoding >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode("latin-1")
    return bytes(out)


def render(slots: list[LabelText | None], cfg: Config, path: str | Path,
           heading: str = "Eppendorf tube labels") -> Path:
    """Write an actual-size proof of the batch, laid out as it will print."""
    sheet = feeds(slots, cfg)
    filled = sum(1 for s in slots if s is not None)
    blanks = len(sheet) * cfg.per_feed - filled

    margin_x, top = 18.0, 20.0
    d2mm = 1.0 / cfg.dots_per_mm
    feed_stride = cfg.label_height_mm + cfg.feed_gap_mm
    sheet_w = cfg.total_width_dots * d2mm

    usable_h = A4[1] / PT_PER_MM - top - 34.0
    per_page = max(1, int(usable_h // feed_stride))

    pages: list[_Page] = []
    index = 0
    while index < len(sheet):
        page = _Page(A4[1])
        pages.append(page)
        page.text(margin_x, top - 8, heading, 11.5)
        page.text(margin_x, top - 2.5,
                  f"{cfg.sticker_width_mm:g} x {cfg.label_height_mm:g} mm label, "
                  f"{cfg.columns} across, cut into {cfg.rows} x "
                  f"{cfg.sticker_height_mm:g} mm  |  {filled} sticker(s)"
                  + (f" + {blanks} blank" if blanks else "")
                  + f", {len(sheet)} feed(s) of {cfg.per_feed}"
                    f"  |  ZD230 @ {cfg.dpi} dpi  |  actual size", 7.5, gray=0.42)

        y = top
        for feed in sheet[index:index + per_page]:
            # Liner behind the whole feed. The columns are separate labels with
            # backing paper showing between them, so this must be drawn first
            # and only the labels themselves painted white on top.
            page.rect(margin_x - 1.5, y - 1.2, sheet_w + 3.0,
                      cfg.label_height_mm + 2.4, fill=(0.87, 0.89, 0.91))

            for col in range(cfg.columns):
                cx = margin_x + cfg.sticker_origin(col)[0] * d2mm
                page.rect(cx, y, cfg.sticker_width_mm, cfg.label_height_mm,
                          fill=(1, 1, 1), stroke=(0.66, 0.71, 0.76), lw=0.4)
                for r in range(1, cfg.rows):   # the slit - a cut, not a gap
                    page.line(cx, y + r * (cfg.sticker_height_mm + cfg.row_gap_mm),
                              cfg.sticker_width_mm)

            for slot in range(cfg.per_feed):
                ox, oy = cfg.sticker_origin(slot)
                _draw_label(page, feed[slot] if slot < len(feed) else None,
                            cfg, margin_x + ox * d2mm, y + oy * d2mm)
            y += feed_stride
        index += per_page

        ruler = y - cfg.feed_gap_mm + 8.0
        page.rect(margin_x, ruler, cfg.sticker_width_mm, 0.5, fill=(0.2, 0.2, 0.2))
        page.text(margin_x, ruler + 4.5,
                  f"The bar above must measure {cfg.sticker_width_mm:g} mm. "
                  f"If it does not, reprint at 100% / 'Actual size'.", 7.0, gray=0.42)
        page.text(margin_x, ruler + 9.5,
                  "Outlines and field positions are exact; the dashed line is the "
                  "cut. Text is indicative: the printer's face is narrower.",
                  7.0, gray=0.55)

    path = Path(path)
    path.write_bytes(_build_pdf(pages, A4))
    return path
