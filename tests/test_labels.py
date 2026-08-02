"""Offline checks - no printer and no network needed.

    python tests/test_labels.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labelprint import bulk, zpl
from labelprint.api import Booking
from labelprint.config import Config

failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        failures.append(name)


def booking(name, gender="Female", y=66, m=8, d=5, sid="PR9000001"):
    return Booking(salesid=sid, patientname=name, gender=gender,
                   age_year=y, age_month=m, age_day=d)


def fits(label, cfg):
    """Every line must sit inside the printable width and the sticker height."""
    name_w = len(label.name) * label.name_w
    id_w = (len(label.sex_age) + len(label.prno)) * label.id_w
    bottom = cfg.id_y + (cfg.id_h_max - label.id_h) // 2 + label.id_h
    return (name_w <= cfg.usable_w_dots and id_w <= cfg.usable_w_dots
            and bottom <= cfg.sticker_h_dots)


cfg = Config()

print("geometry")
check("38 mm sticker is 304 dots at 203 dpi", cfg.sticker_w_dots == 304,
      cfg.sticker_w_dots)
check("12.5 mm sticker is 100 dots", cfg.sticker_h_dots == 100, cfg.sticker_h_dots)
check("the label the sensor advances by is 25 mm", cfg.label_height_mm == 25.0,
      cfg.label_height_mm)
check("a feed is 200 dots tall", cfg.feed_h_dots == 200, cfg.feed_h_dots)
check("a feed carries 4 stickers", cfg.per_feed == 4, cfg.per_feed)
check("width fits the ZD230 head (<=832 dots)", cfg.total_width_dots <= 832,
      cfg.total_width_dots)
check("name band does not reach the id band",
      cfg.name_y + cfg.name_h_max <= cfg.id_y,
      f"{cfg.name_y + cfg.name_h_max} > {cfg.id_y}")
check("id band stays inside the sticker",
      cfg.id_y + cfg.id_h_max <= cfg.sticker_h_dots,
      f"{cfg.id_y + cfg.id_h_max} > {cfg.sticker_h_dots}")

print("sticker positions within a feed")
origins = [cfg.sticker_origin(i) for i in range(cfg.per_feed)]
check("filled in reading order", origins == [(0, 0), (320, 0), (0, 100), (320, 100)],
      origins)
check("no space across the cut",
      origins[2][1] - origins[0][1] == cfg.sticker_h_dots)
check("there is a real gap between the columns",
      origins[1][0] - origins[0][0] == cfg.sticker_w_dots + cfg.mm(cfg.column_gap_mm)
      and cfg.mm(cfg.column_gap_mm) > 0,
      f"stride {origins[1][0] - origins[0][0]} vs sticker {cfg.sticker_w_dots} "
      f"+ gap {cfg.mm(cfg.column_gap_mm)}")
check("every sticker sits inside the feed",
      all(x + cfg.sticker_w_dots <= cfg.total_width_dots
          and y + cfg.sticker_h_dots <= cfg.feed_h_dots for x, y in origins))

print("label content")
lbl = zpl.build(booking("SMT. SPECIMEN PATIENT"), cfg)
check("full name kept", lbl.name == "SMT. SPECIMEN PATIENT", repr(lbl.name))
check("sex and age", lbl.sex_age == "F/66", lbl.sex_age)
check("PR number", lbl.prno == "PR9000001", lbl.prno)
check("nothing overflows", fits(lbl, cfg))
check("no truncation needed", not lbl.name_truncated)

check("male maps to M", zpl.build(booking("TEST GAMMA", "Male"), cfg).sex_age == "M/66")
check("unknown gender maps to O",
      zpl.build(booking("TEST GAMMA", "Unknown"), cfg).sex_age == "O/66")

infant = booking("BABY OF TEST", "Male", y=0, m=8, d=5)
check("strict years shows 0", zpl.build(infant, cfg).sex_age == "M/0")
check("smart age shows months for a neonate",
      zpl.build(infant, Config(age_style="smart")).sex_age == "M/8M")

print("auto-fit and truncation")
short = zpl.build(booking("TEST ALPHA"), cfg)
check("short name uses the largest size", short.name_h == cfg.name_h_max,
      short.name_h)
check("long name is set smaller than a short one",
      lbl.name_h < short.name_h, f"{lbl.name_h} vs {short.name_h}")

for sample in ("A", "TEST ALPHA", "SMT. SPECIMEN PATIENT",
               "SHRI. SPECIMEN LONGNAME EXAMPLE PATIENT TESTCASE",
               "MASTER ABCDEFGHIJKLMNOPQRSTUVWXYZ ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    got = zpl.build(booking(sample), cfg)
    check(f"fits: {sample[:34]!r}", fits(got, cfg),
          f"name {len(got.name) * got.name_w}d, id "
          f"{(len(got.sex_age) + len(got.prno)) * got.id_w}d of {cfg.usable_w_dots}d")

longest = zpl.build(booking("SHRI. SPECIMEN LONGNAME EXAMPLE PATIENT TESTCASE"), cfg)
check("very long name is shortened", longest.name_truncated)
check("honorific is dropped first", not longest.name.startswith("SHRI"),
      longest.name)
check("sex/age and PR are never dropped",
      longest.sex_age == "F/66" and longest.prno == "PR9000001")

wide = zpl.build(booking("TEST ALPHA", sid="PRX1234567890123"), cfg)
check("a long PR number still fits", fits(wide, cfg))
check("a long PR number shrinks the id line", wide.id_h < cfg.id_h_max, wide.id_h)

print("batch layout")
a = zpl.build(booking("TEST ALPHA", sid="PR0000001"), cfg)
b = zpl.build(booking("TEST BETA", sid="PR0000002"), cfg)

check("1 sticker pads to a whole feed of 4", len(zpl.pad_slots([a], cfg)) == 4)
check("3 stickers pad to 4", len(zpl.pad_slots([a, b, a], cfg)) == 4)
check("5 stickers pad to 8", len(zpl.pad_slots([a] * 5, cfg)) == 8)
check("a full feed is left alone", len(zpl.pad_slots([a] * 4, cfg)) == 4)
check("padding can be switched off", len(zpl.pad_slots([a], cfg, pad=False)) == 1)

one = zpl.batch(zpl.pad_slots([a], cfg), cfg)
check("1 sticker = 1 feed with 3 blanks", one.count("^XA") == 1)
check("the 3 blank slots really are empty", one.count("PR0000001") == 1, one)

eight = zpl.batch(zpl.pad_slots([a] * 8, cfg), cfg)
check("8 of one patient collapses to one form of quantity 2",
      eight.count("^XA") == 1 and "^PQ2," in eight, eight)

mixed = zpl.batch(zpl.pad_slots([a, b, b, b, a, a, a, a], cfg), cfg)
check("mixed batch emits a form per distinct feed", mixed.count("^XA") == 2, mixed)
check("both patients appear", "PR0000001" in mixed and "PR0000002" in mixed)

explicit = zpl.pad_slots([a] + [None] * 3, cfg)
check("deliberate blanks are kept", explicit == [a, None, None, None])
check("a batch of only blanks prints nothing",
      zpl.batch([None] * 4, cfg) == "")

full = zpl.batch([a, b, a, b], cfg)
placed = [(int(m[1]), int(m[2]))
          for m in re.finditer(r"\^FO(\d+),(\d+)", full)]
pad = cfg.mm(cfg.pad_mm)
check("every field starts at the sticker's left pad",
      {x for x, _ in placed} == {ox + pad for ox, _ in origins},
      sorted({x for x, _ in placed}))
for slot, (ox, oy) in enumerate(origins):
    band = [y for x, y in placed
            if x == ox + pad and oy <= y < oy + cfg.sticker_h_dots]
    # name, sex/age and PR number - the last two share a baseline.
    check(f"slot {slot} at {(ox, oy)} carries its 3 fields on 2 lines",
          len(band) == 3 and len(set(band)) == 2, band)
check("no field escapes the feed",
      all(y + cfg.id_h_max <= cfg.feed_h_dots for _, y in placed))
check("print width is set", f"^PW{cfg.total_width_dots}" in mixed)
check("utf-8 encoding is selected", "^CI28" in mixed)
check("no barcode commands remain", "^BC" not in mixed and "^BY" not in mixed)

dirty = zpl.build(booking("TEST^NAME~X"), cfg)
check("zpl control characters are neutralised",
      "^" not in zpl.batch([dirty, None], cfg).split("^FD")[1].split("^FS")[0])

print("bulk paste")
one_per_line = bulk.parse("PR1000001\nPR1000002\nPR1000003")
check("one per line", one_per_line.ids == ["PR1000001", "PR1000002", "PR1000003"],
      one_per_line.ids)
check("comma separated",
      bulk.parse("PR1000001, PR1000002,PR1000003").ids
      == ["PR1000001", "PR1000002", "PR1000003"])
check("excel column with tabs and blank rows",
      bulk.parse("PR1000001\t\r\n\r\nPR1000002\t").ids
      == ["PR1000001", "PR1000002"])
check("semicolons, pipes and spaces",
      bulk.parse("PR1000001; PR1000002 | PR1000003").ids
      == ["PR1000001", "PR1000002", "PR1000003"])
check("quotes and brackets are separators",
      bulk.parse('"PR1000001",(PR1000002)').ids == ["PR1000001", "PR1000002"])
check("case is normalised", bulk.parse("pr1000001").ids == ["PR1000001"])

table = bulk.parse(
    "SalesID\tPatient\tDate\n"
    "PR1000001\tSPECIMEN ONE\t25-03-2026\n"
    "PR1000002\tSPECIMEN TWO\t25-03-2026\n")
check("a pasted table keeps only the IDs",
      table.ids == ["PR1000001", "PR1000002"], table.ids)
check("headings and names are reported as ignored",
      "SALESID" in table.skipped and "SPECIMEN" in table.skipped, table.skipped)
check("dates are not mistaken for IDs",
      not any(t.startswith("25") for t in table.ids), table.ids)

dupes = bulk.parse("PR1000001 PR1000002 PR1000001 PR1000001")
check("repeats are listed once", dupes.ids == ["PR1000001", "PR1000002"])
check("repeats are counted", dupes.repeated == {"PR1000001": 3}, dupes.repeated)
check("order of first appearance is kept", dupes.ids[0] == "PR1000001")

check("ignored tokens are de-duplicated",
      bulk.parse("Patient Patient PR1000001").skipped == ["PATIENT"])
check("empty input is handled", bulk.parse("").ids == [])
check("text with no IDs is handled", bulk.parse("no ids here!").ids == [])
check("summary reads sensibly", table.summary.startswith("2 Sales ID(s)"),
      table.summary)

check("a broken custom pattern falls back to the default",
      bulk.parse("PR1000001", pattern="[unclosed").ids == ["PR1000001"])
check("a custom pattern is honoured",
      bulk.parse("AB12345 PR1000001", pattern=r"^AB[0-9]+$").ids == ["AB12345"])

print()
if failures:
    print(f"{len(failures)} failed: {', '.join(failures)}")
    raise SystemExit(1)
print("all checks passed")
