"""Command-line entry point, for testing and for scripted/batch use.

Each item is a Sales ID with an optional sticker count after a colon; use
"blank" or "blank:N" to place deliberate blanks.

    python -m labelprint.cli PR9000001                      # 1 sticker, dry run
    python -m labelprint.cli PR9000001:3 PR9000002 -p       # mixed batch, print
    python -m labelprint.cli PR9000001:1 blank:3 -p         # 1 label, 3 blanks
    python -m labelprint.cli PR9000001:8 --pdf              # actual-size proof
"""

from __future__ import annotations

import argparse
import sys

from . import api, config, output, pdfproof, zpl


def _parse_item(text: str) -> tuple[str, int]:
    sales_id, _, qty = text.partition(":")
    if qty and not qty.isdigit():
        raise SystemExit(f"error: '{text}' - the count after ':' must be a number")
    return sales_id.strip(), max(1, int(qty or 1))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print Eppendorf tube labels.",
        epilog="Items look like PR9000001, PR9000001:3, blank, or blank:2.")
    parser.add_argument("items", nargs="*", metavar="ID[:COUNT]")
    parser.add_argument("-p", "--print", dest="do_print", action="store_true",
                        help="actually send the job to the printer")
    parser.add_argument("--zpl", action="store_true", help="print the ZPL to stdout")
    parser.add_argument("--pdf", nargs="?", const="proof.pdf", metavar="PATH",
                        help="write an actual-size PDF proof (default proof.pdf)")
    parser.add_argument("--printers", action="store_true",
                        help="list Windows print queues and exit")
    args = parser.parse_args(argv)

    cfg = config.load()
    if args.printers:
        for name in output.list_printers():
            print(name)
        return 0
    if not args.items:
        parser.error("give at least one Sales ID")

    slots: list[zpl.LabelText | None] = []
    for raw in args.items:
        sales_id, qty = _parse_item(raw)
        if sales_id.lower() == "blank":
            slots.extend([None] * qty)
            print(f"  {qty} x blank")
            continue
        try:
            booking = api.fetch(sales_id, cfg)
        except api.BookingError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        label = zpl.build(booking, cfg)
        slots.extend([label] * qty)
        note = "  (name shortened)" if label.name_truncated else ""
        print(f"  {qty} x {label.prno}  {label.name} {label.sex_age}{note}")

    slots = zpl.pad_slots(slots, cfg, cfg.pad_with_blanks)
    filled = sum(1 for s in slots if s is not None)
    blanks = len(slots) - filled
    print(f"  -> {filled} sticker(s)" + (f" + {blanks} blank" if blanks else "")
          + f", {len(slots) // cfg.per_feed} feed(s) of {cfg.per_feed}")

    if args.pdf:
        print(f"  -> proof: {pdfproof.render(slots, cfg, args.pdf)}")

    data = zpl.batch(slots, cfg)
    if args.zpl:
        print("\n" + data)
    if args.do_print:
        try:
            print(output.send(data, cfg))
        except output.PrintError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
