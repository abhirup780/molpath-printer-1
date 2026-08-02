"""Label content rules and ZPL II generation.

Two text lines per sticker, no barcode:

    SMT. SPECIMEN PATIENT          <- name, auto-sized to fit
    F/66            PR9000001      <- sex/age at the left, PR number at the right

Both lines shrink within a configured size range until they fit the printable
width, so text can never overflow the sticker or collide with the next column.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .api import Booking
from .config import Config

HONORIFICS = (
    "SMT.", "SMT", "SHRI.", "SHRI", "SRI.", "SRI", "MR.", "MR", "MRS.", "MRS",
    "MS.", "MS", "MISS", "MASTER", "MSTR.", "MSTR", "BABY", "B/O", "DR.", "DR",
    "PROF.", "PROF",
)

GENDER_CODES = {"FEMALE": "F", "F": "F", "MALE": "M", "M": "M"}


@dataclass
class LabelText:
    """One sticker's worth of content, already sized to fit."""
    name: str
    sex_age: str            # "F/66"
    prno: str               # "PR9000001"
    name_h: int = 24
    name_w: int = 13
    id_h: int = 34
    id_w: int = 19
    name_truncated: bool = False

    @property
    def summary(self) -> str:
        return f"{self.name} {self.sex_age} {self.prno}".strip()


def gender_code(gender: str) -> str:
    return GENDER_CODES.get(gender.strip().upper(), "O")


def age_text(booking: Booking, style: str = "years") -> str:
    """Strict "years" prints the year count only, as specified. "smart" avoids
    labelling a neonate as "0" by falling back to months, then days."""
    if style == "smart" and booking.age_year == 0:
        if booking.age_month > 0:
            return f"{booking.age_month}M"
        return f"{booking.age_day}D"
    return str(booking.age_year)


def _strip_honorific(name: str) -> str:
    parts = name.split()
    if len(parts) > 1 and parts[0].upper() in HONORIFICS:
        return " ".join(parts[1:])
    return name


def _fit(chars: int, cfg: Config, h_max: int, h_min: int) -> tuple[int, int]:
    """Largest (height, width) in the range whose cells fit the usable width."""
    for h in range(h_max, h_min - 1, -1):
        w = max(1, round(h * cfg.font_w_ratio))
        if chars * w <= cfg.usable_w_dots:
            return h, w
    return h_min, max(1, round(h_min * cfg.font_w_ratio))


def build(booking: Booking, cfg: Config) -> LabelText:
    name = re.sub(r"\s+", " ", booking.patientname).strip().upper()
    sex_age = f"{gender_code(booking.gender)}/{age_text(booking, cfg.age_style)}"
    prno = booking.salesid.strip().upper()

    # Line 2 first: the PR number and sex/age are both non-negotiable, so they
    # set the floor. They share one line with a minimum gap between them.
    id_chars = len(sex_age) + cfg.id_gap_chars + len(prno)
    id_h, id_w = _fit(id_chars, cfg, cfg.id_h_max, cfg.id_h_min)

    # Line 1: shrink to fit, and only clip if the smallest size still overflows.
    name_h, name_w = _fit(len(name), cfg, cfg.name_h_max, cfg.name_h_min)
    budget = max(1, cfg.usable_w_dots // name_w)
    truncated = False
    if len(name) > budget:
        name = _strip_honorific(name)
        truncated = True
        name_h, name_w = _fit(len(name), cfg, cfg.name_h_max, cfg.name_h_min)
        budget = max(1, cfg.usable_w_dots // name_w)
    if len(name) > budget:
        name = name[:budget].rstrip()

    return LabelText(name=name, sex_age=sex_age, prno=prno, name_h=name_h,
                     name_w=name_w, id_h=id_h, id_w=id_w,
                     name_truncated=truncated)


def _fd(text: str) -> str:
    """^ ~ and \\ are control characters inside a ^FD block."""
    return text.replace("^", " ").replace("~", " ").replace("\\", " ")


def _one_label(label: LabelText, cfg: Config, x0: int, y0: int) -> str:
    pad = cfg.mm(cfg.pad_mm)
    usable = cfg.usable_w_dots
    x = x0 + pad

    # Centre each line inside the vertical band reserved for it, so a shrunken
    # line does not sit hard against the top of its band.
    name_y = y0 + cfg.name_y + (cfg.name_h_max - label.name_h) // 2
    id_y = y0 + cfg.id_y + (cfg.id_h_max - label.id_h) // 2

    return "\n".join([
        f"^FO{x},{name_y}^A0N,{label.name_h},{label.name_w}"
        f"^FB{usable},1,0,L,0^FD{_fd(label.name)}^FS",
        f"^FO{x},{id_y}^A0N,{label.id_h},{label.id_w}"
        f"^FB{usable},1,0,L,0^FD{_fd(label.sex_age)}^FS",
        f"^FO{x},{id_y}^A0N,{label.id_h},{label.id_w}"
        f"^FB{usable},1,0,R,0^FD{_fd(label.prno)}^FS",
    ])


def form(slots: list[LabelText | None], cfg: Config, quantity: int = 1) -> str:
    """One ZPL form = one media feed = one 38 x 25 mm label, 2 across.

    That label is slit horizontally into two 12.5 mm halves, so a feed carries
    `cfg.per_feed` (normally 4) stickers, filled in reading order.

    A None slot is deliberately left blank: nothing is printed there, so the
    sticker comes out clean rather than carrying anyone else's details.
    """
    out = ["^XA", "^CI28", f"^PW{cfg.total_width_dots}", "^LH0,0", "^LS0", "^MMT"]
    if cfg.media_tracking:
        out.append(f"^MN{cfg.media_tracking}")
    if cfg.label_length_dots is not None:
        out.append(f"^LL{cfg.label_length_dots}")
    if cfg.darkness is not None:
        out.append(f"^MD{cfg.darkness}")
    if cfg.print_speed is not None:
        out.append(f"^PR{cfg.print_speed}")

    for index, label in enumerate(slots[:cfg.per_feed]):
        if label is not None:
            x, y = cfg.sticker_origin(index)
            out.append(_one_label(label, cfg, x, y))

    out.append(f"^PQ{quantity},0,0,N")
    out.append("^XZ")
    return "\n".join(out) + "\n"


def pad_slots(slots: list[LabelText | None], cfg: Config,
              pad: bool = True) -> list[LabelText | None]:
    """Round the batch up to a whole number of feeds with blank stickers."""
    remainder = len(slots) % cfg.per_feed
    if pad and remainder:
        slots = slots + [None] * (cfg.per_feed - remainder)
    return slots


def feeds(slots: list[LabelText | None], cfg: Config) -> list[list[LabelText | None]]:
    """Split the batch into feeds of `cfg.per_feed` stickers."""
    n = cfg.per_feed
    padded = slots + [None] * ((-len(slots)) % n)
    return [padded[i:i + n] for i in range(0, len(padded), n)]


def batch(slots: list[LabelText | None], cfg: Config) -> str:
    """ZPL for a whole mixed batch, in the order given.

    Identical consecutive feeds collapse into one form with ^PQ, so eight
    stickers for one patient go out as a single form with a quantity of two.
    """
    if not any(slot is not None for slot in slots):
        return ""

    parts = []
    if cfg.tear_offset is not None:
        parts.append(f"~TA{cfg.tear_offset:03d}\n")

    pending: str | None = None
    count = 0
    for feed in feeds(slots, cfg):
        body = form(feed, cfg, quantity=1)
        if body == pending:
            count += 1
            continue
        if pending is not None:
            parts.append(pending.replace("^PQ1,0,0,N", f"^PQ{count},0,0,N"))
        pending, count = body, 1
    if pending is not None:
        parts.append(pending.replace("^PQ1,0,0,N", f"^PQ{count},0,0,N"))
    return "".join(parts)
