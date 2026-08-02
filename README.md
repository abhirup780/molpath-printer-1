# Molecular Pathology — Eppendorf Tube Label Printer

Prints patient identification stickers on a **Zebra ZD230**, for labelling
Eppendorf tubes.

## The media

The liner carries **38 × 25 mm labels, 2 across**. Each label is slit
horizontally across its middle into two **12.5 mm** stickers, with **no gap** at
the cut. The gap sensor only sees the 25 mm pitch between whole labels, so:

```
one feed  =  one 38 × 25 mm label, 2 across
          =  2 columns × 2 slit halves
          =  4 stickers
```

**Batches therefore round up to a multiple of 4.** The slots fill in reading
order — top-left, top-right, then the two halves below.

If your stock differs, `columns`, `rows`, `sticker_width_mm` and
`sticker_height_mm` in `config.json` describe it; everything else follows.

Each sticker carries two lines, no barcode:

```
SMT. SPECIMEN PATIENT
F/66            PR9000001
```

Name on top, sex/age bottom‑left, PR number bottom‑right. Patient details are
fetched live from `viewBookingHeader` by Sales ID.

**Nothing can overflow.** Both lines are auto‑sized: they shrink until they fit
the printable width. A typical name prints at 3.8 mm tall, a long one at 3.0 mm,
and only a name over ~32 characters gets shortened at all.

---

## Batches

You build a list, then print it in one go. Any mix works:

- 1 sticker each for 4 different PR numbers
- 3 of one PR and 1 of another
- 2 each for 2 PRs
- deliberate blanks anywhere in the list

Since **one feed prints 4 stickers**, a batch rounds up to a multiple of 4 and
the app fills the leftover slots with **blanks** rather than anything else.
Print 1 sticker and you get 1 label plus 3 blanks; print 5 and you get 5 plus 3.
Blanks come out genuinely empty, so there is no risk of a stray sticker carrying
the previous patient's details.

You can also add blanks on purpose with the **Add blank** button.

## Installing on the lab PC

Copy this whole folder to the PC that has the ZD230, then:

| Run | What it does |
|---|---|
| **`1 - Setup.bat`** | installs the two Python libraries and puts a **Tube Label Printer** shortcut on the Desktop |
| **`2 - Check Setup.bat`** | checks Python, the config, the booking server and the printer, and tells you plainly whether the PC is ready |
| **`Label Printer.bat`** | starts the app (same as the Desktop shortcut) |

Python 3.10+ must be installed first — from python.org, ticking **Add Python to
PATH** on the installer's first screen. `1 - Setup.bat` says so if it is missing.

### The booking server address

**It is not in the source code, on purpose.** The endpoint returns patient
demographics, so its address does not travel with the repository.

The first time you start the app it asks for the address and saves it to
**`config.local.json`**, which is gitignored and stays on that PC. Change it
later with **Tools → Booking server URL…**.

If you would rather set it up before first launch, copy
`config.local.example.json` to `config.local.json` and fill in `api_url`.
Setting `MOLPATH_API_URL` in the environment overrides both.

Settings load in this order, each overriding the last:

| | |
|---|---|
| `config.json` | tracked — label geometry, fonts, layout. Same on every PC |
| `config.local.json` | untracked — booking server URL, which printer, TCP host |
| `MOLPATH_API_URL` | environment override for the server URL |

This also means **Tools → Choose printer** no longer dirties the tracked file,
so you can `git pull` updates in the lab without conflicts.

`2 - Check Setup.bat --test-print` also sends one real feed, so you can confirm
end to end before letting anyone use it. Add `--sales-id PR…` with any real
Sales ID to check a live patient lookup too — the checker deliberately hard‑codes
no real PR number, so it tests only that the server answers unless you give it one.

### The driver

You need the **ZDesigner ZD230 — ZPL** driver, which is what the ZD230 ships
with by default. The queue is usually named something like
`ZDesigner ZD230-203dpi ZPL`.

The app does **not** render through the driver. It opens the queue in Windows
RAW mode and sends ZPL commands straight through to the printer, so driver page
sizes, margins and orientation settings are irrelevant and cannot break the
layout. That is why the driver variant is the one thing that matters:

- a driver name containing **ZPL** — correct, nothing to do
- a driver name containing **EPL** — wrong language; reinstall choosing ZPL.
  `2 - Check Setup.bat` flags this explicitly
- **300 dpi** in the name — set `"dpi": 300` in `config.json`

If the ZD230 is on the network or Wi‑Fi, you can skip the driver entirely: set
`"output_mode": "tcp"` and `"tcp_host": "<printer IP>"` in `config.json`.

### First run

1. Start the app. It auto‑detects the Zebra queue; if there are several, use
   **Tools → Choose printer…** once and it is remembered.
2. **Tools → Calibrate media** — the printer feeds a few blank labels while it
   learns the 25 mm gap. Do this once when the stock is first loaded, and again
   if you ever change label rolls.
3. **Tools → Print test label** — prints one feed with all four positions
   filled, so you can check alignment everywhere at once.
4. If it is off, adjust `column_gap_mm` / `left_margin_mm` / `top_margin_mm` in
   `config.json` and use **Tools → Reload config.json**.

## Daily use

![The app window](docs/ui.png)

| Step | Action |
|---|---|
| 1 | Scan (or type) the Sales ID |
| 2 | Set **Stickers** if it is not 1 |
| 3 | Press **Enter** — the patient is looked up and added to the batch |
| 4 | Repeat for every sample |
| 5 | Check the sheet preview, then **Print batch** |

Scanning the same PR twice just increases its count rather than adding a second
row. Select a row and use **+1 / −1 / Remove**, or `Delete`, to adjust.
`Ctrl+P` prints, `Esc` returns focus to the Sales ID box. The batch clears
itself after a successful print.

## Command line

Items are `ID`, `ID:COUNT`, `blank`, or `blank:COUNT`.

```
python -m labelprint.cli PR9000001                    # 1 sticker, dry run
python -m labelprint.cli PR9000001:3 PR9000002 -p     # mixed batch, print it
python -m labelprint.cli PR9000001 blank:3 -p         # 1 label, 3 blanks
python -m labelprint.cli PR9000001:8 --pdf            # actual-size PDF proof
python -m labelprint.cli X --printers                 # list Windows queues
```

## PDF proof

**Tools → Save PDF proof…** (or `--pdf`) writes an A4 sheet showing the batch
exactly as it will print, one box per 38 × 25 mm label with a dashed line where
the cut runs. Outlines and field positions are exact vectors at true size, so
printing it at **100% / Actual size** and laying it against the real stock is the
quickest way to check alignment — there is a 38 mm ruler bar on the page to
confirm the scale came out right.

Text in the proof is indicative only: the ZD230's face is narrower than the
Helvetica used in the PDF, so anything that fits in the proof will fit on the
printer. The proof is generated locally, so patient data never leaves the
machine.

## Calibration

All of this lives in `config.json`; **Tools → Reload config.json** picks up edits
without restarting. Layout values are in printer dots — 203 dots/inch, so
1 mm ≈ 8 dots.

| Symptom | Fix |
|---|---|
| Right‑hand sticker cut off or shifted | `column_gap_mm` — the gap between the two columns on your stock |
| Everything too far left or right | `left_margin_mm` |
| Whole feed sits too high or too low | `top_margin_mm` |
| Bottom half creeps up or down relative to the cut | `row_gap_mm` (normally 0 — the cut has no gap) |
| Lines sit too high or too low within a sticker | `name_y`, `id_y` |
| Text generally too small or too large | `name_h_max`, `id_h_max` (dots) |
| Text looks stretched or cramped | `font_w_ratio` — character width as a fraction of height |
| Print too light or too dark | `darkness` (0–30) |
| Printer feeds the wrong distance | `label_length_dots` — normally `null` so the gap sensor decides; 200 forces 25 mm |
| Media stops in the wrong place for tearing | `tear_offset` (dots, may be negative) |
| Stock is not cut in half | `"rows": 1` and `sticker_height_mm: 25` |
| You have the 300 dpi ZD230 | `"dpi": 300` — every mm measurement rescales automatically |
| Don't want the last feed padded | `"pad_with_blanks": false` |

Lowering `font_w_ratio` fits more characters before the name has to shrink;
raising it makes text wider and shrink sooner.

## Name handling

The name is set as large as will fit, stepping down from `name_h_max` to
`name_h_min` dots. If even the smallest size overflows, the honorific
(`SMT.`, `SHRI.`, `MASTER`, …) is dropped first, and only then is the name
clipped. **Sex/age and the PR number are never dropped or shrunk away** — they
set the floor for the second line, which is sized before the name. The ZPL also
carries a hard one‑line `^FB` limit, so the printer itself will not let a field
spill outside its box. When a name has been shortened the app lists it in amber
under the preview.

## Age

`"age_style": "years"` prints the year count only, as specified — so a neonate
reads `M/0`. Set `"age_style": "smart"` and that case becomes `M/8M` or `M/5D`
instead. Everyone one year and older is unaffected either way.

## Testing without a printer

Set `"output_mode": "file"` in `config.json` and jobs are written to `out.zpl`
instead of printed. `python tests/test_labels.py` runs the offline geometry,
slot‑position, auto‑fit, truncation and batch‑layout checks — no printer or
network needed.

## Files

| File | Purpose |
|---|---|
| `config.local.example.json` | template for this PC's booking server and printer |
| `1 - Setup.bat` | one-time install on a new PC |
| `2 - Check Setup.bat` | pre-flight check; run this if anything misbehaves |
| `run.pyw` / `Label Printer.bat` | launchers |
| `labelprint/doctor.py` | the checks behind `2 - Check Setup.bat` |
| `config.json` | everything you might need to calibrate |
| `labelprint/gui.py` | the desktop window and batch list |
| `labelprint/api.py` | booking lookup |
| `labelprint/zpl.py` | label content rules, auto‑fit, ZPL generation |
| `labelprint/preview.py` | on‑screen sheet rendering |
| `labelprint/pdfproof.py` | actual‑size PDF proof |
| `labelprint/output.py` | Windows RAW / TCP 9100 / file output |
| `tests/test_labels.py` | offline checks |
