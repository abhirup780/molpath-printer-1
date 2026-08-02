"""Configuration loading.

Settings come from two files, in this order:

  config.json         tracked in git - label geometry, fonts, layout. Safe to
                      share, identical on every machine.
  config.local.json   NOT tracked - this site's booking server URL, which
                      printer to use, and anything else specific to one PC.

`MOLPATH_API_URL` in the environment overrides the booking server URL again,
which is handy for a test instance.

Keeping the server URL out of git is deliberate: the booking endpoint returns
patient demographics, so its address should not travel with the source code.

Media model
-----------
The liner carries 38 x 25 mm labels, 2 across. Each label is slit horizontally
across its middle into two 12.5 mm stickers with **no gap** at the cut. The gap
sensor only sees the 25 mm pitch between labels, so:

    one feed = one 38 x 25 mm label, 2 across
             = 2 columns x 2 slit halves
             = 4 stickers

which is why batches round up to a multiple of four.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
LOCAL_PATH = ROOT / "config.local.json"

# Settings that belong to one site or one PC, never to the repository.
SITE_KEYS = ("api_url", "printer_name", "output_mode", "tcp_host", "tcp_port")


@dataclass
class Config:
    # --- data source -------------------------------------------------------
    api_url: str = ""              # set in config.local.json, never in git
    api_timeout_s: float = 20.0

    # --- media geometry (millimetres unless noted) --------------------------
    dpi: int = 203                  # ZD230 is 203 dpi; use 300 for the 300 dpi model
    sticker_width_mm: float = 38.0
    sticker_height_mm: float = 12.5  # one slit half
    columns: int = 2                # stickers across the liner
    rows: int = 2                   # slit halves per label, down
    column_gap_mm: float = 2.0      # gap between the columns
    row_gap_mm: float = 0.0         # the horizontal cut - no space across it
    feed_gap_mm: float = 2.0        # gap between labels; PDF proof only, the
                                    # printer finds this itself with the sensor
    left_margin_mm: float = 0.0     # shift everything right if column 1 clips
    top_margin_mm: float = 0.0      # shift everything down
    pad_mm: float = 2.0             # quiet margin inside each sticker

    # --- text layout (dots, relative to the top of each sticker) ------------
    # Both lines auto-shrink within their h_min..h_max range until they fit the
    # printable width, so text can never overflow.
    name_y: int = 11
    name_h_max: int = 28
    name_h_min: int = 15
    id_y: int = 54
    id_h_max: int = 32
    id_h_min: int = 16
    font_w_ratio: float = 0.55      # character width as a fraction of height
    id_gap_chars: int = 2           # minimum gap between "F/66" and the PR number

    # --- content rules ------------------------------------------------------
    age_style: str = "years"        # "years" = strict Y only; "smart" = M/D under 1y
    default_qty: int = 1            # stickers added per Sales ID
    pad_with_blanks: bool = True    # fill the last feed so the next batch is clean

    # --- printer ------------------------------------------------------------
    output_mode: str = "windows"    # "windows" | "tcp" | "file"
    printer_name: str = ""          # blank = auto-detect a Zebra queue
    tcp_host: str = ""
    tcp_port: int = 9100
    file_path: str = "out.zpl"
    darkness: int | None = None     # ^MD, 0..30; None leaves the printer setting
    print_speed: int | None = None  # ^PR, in ips; None leaves the printer setting
    media_tracking: str | None = "Y"   # ^MN: "Y" gap/web sensing, None to omit
    label_length_dots: int | None = None  # ^LL; None lets the sensor decide
    tear_offset: int | None = None     # ~TA, dots; nudge where the media stops

    # ------------------------------------------------------------- geometry
    @property
    def dots_per_mm(self) -> float:
        return self.dpi / 25.4

    def mm(self, value: float) -> int:
        return round(value * self.dots_per_mm)

    @property
    def sticker_w_dots(self) -> int:
        return self.mm(self.sticker_width_mm)

    @property
    def sticker_h_dots(self) -> int:
        return self.mm(self.sticker_height_mm)

    @property
    def per_feed(self) -> int:
        """Stickers printed per media feed - 4 on the standard 2-across stock."""
        return max(1, self.columns * self.rows)

    @property
    def label_height_mm(self) -> float:
        """Height of the whole label the sensor advances by (25 mm)."""
        return self.rows * self.sticker_height_mm + (self.rows - 1) * self.row_gap_mm

    @property
    def feed_h_dots(self) -> int:
        return (self.rows * self.sticker_h_dots
                + (self.rows - 1) * self.mm(self.row_gap_mm))

    @property
    def total_width_dots(self) -> int:
        gaps = (self.columns - 1) * self.mm(self.column_gap_mm)
        return self.mm(self.left_margin_mm) + self.columns * self.sticker_w_dots + gaps

    def sticker_origin(self, index: int) -> tuple[int, int]:
        """Top-left dot of sticker `index` within a feed, filled in reading
        order: top-left, top-right, then the two halves below."""
        row, col = divmod(index, self.columns)
        x = (self.mm(self.left_margin_mm)
             + col * (self.sticker_w_dots + self.mm(self.column_gap_mm)))
        y = (self.mm(self.top_margin_mm)
             + row * (self.sticker_h_dots + self.mm(self.row_gap_mm)))
        return x, y

    @property
    def usable_w_dots(self) -> int:
        return self.sticker_w_dots - 2 * self.mm(self.pad_mm)


def _read(path: Path, known: set[str]) -> dict:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if k in known}


def load(path: Path | None = None, local_path: Path | None = None) -> Config:
    """config.json, then config.local.json on top, then the environment."""
    known = {f.name for f in fields(Config)}
    data = _read(path or CONFIG_PATH, known)
    data.update(_read(local_path or LOCAL_PATH, known))

    from_env = os.environ.get("MOLPATH_API_URL")
    if from_env:
        data["api_url"] = from_env
    return Config(**data)


def save_local(cfg: Config, path: Path | None = None) -> Path:
    """Write only this PC's settings, leaving the tracked config.json alone."""
    path = path or LOCAL_PATH
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            existing = {}
    existing.update({key: getattr(cfg, key) for key in SITE_KEYS})
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return path
