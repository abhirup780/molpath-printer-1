"""Pre-flight check for the lab PC.

Run this first on any machine the app is installed on. It reports what is
present, what is missing, and - most importantly - whether the Zebra queue that
Windows has installed is one that accepts raw ZPL.

    python -m labelprint.doctor
    python -m labelprint.doctor --test-print
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

OK, WARN, BAD = "  [ok]  ", "  [!!]  ", "  [XX]  "

problems: list[str] = []
warnings: list[str] = []


def ok(msg: str) -> None:
    print(OK + msg)


def warn(msg: str, fix: str = "") -> None:
    print(WARN + msg)
    warnings.append(msg + (f"  ->  {fix}" if fix else ""))


def bad(msg: str, fix: str = "") -> None:
    print(BAD + msg)
    problems.append(msg + (f"  ->  {fix}" if fix else ""))


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


# --------------------------------------------------------------------------
def check_python() -> None:
    section("Python")
    version = sys.version_info
    if version >= (3, 10):
        ok(f"Python {version.major}.{version.minor}.{version.micro}")
    else:
        bad(f"Python {version.major}.{version.minor} is too old",
            "install Python 3.10 or newer")

    for module, hint in (("requests", "pip install requests"),
                         ("tkinter", "reinstall Python with the tcl/tk option")):
        try:
            __import__(module)
            ok(f"{module} available")
        except ImportError:
            bad(f"{module} is missing", hint)

    if sys.platform == "win32":
        try:
            import win32print  # noqa: F401
            ok("pywin32 available (needed to print via a Windows queue)")
        except ImportError:
            bad("pywin32 is missing", "pip install pywin32")


def check_config():
    section("Configuration")
    from . import config
    if not config.CONFIG_PATH.exists():
        warn("config.json not found; built-in defaults will be used",
             "the app writes one when you pick a printer")
        return config.Config()
    try:
        cfg = config.load()
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        bad(f"config.json is not valid: {exc}", "fix the file or delete it")
        return config.Config()

    ok(f"config.json loaded from {config.CONFIG_PATH}")
    if config.LOCAL_PATH.exists():
        ok(f"local settings from {config.LOCAL_PATH.name}")
    else:
        warn(f"{config.LOCAL_PATH.name} not found - this PC has no booking "
             "server or printer set yet",
             "start the app once; it asks and writes the file for you")
    ok(f"sticker {cfg.sticker_width_mm:g} x {cfg.sticker_height_mm:g} mm, "
       f"{cfg.columns} across x {cfg.rows} down = {cfg.per_feed} per feed")
    ok(f"label the sensor advances by: {cfg.label_height_mm:g} mm "
       f"({cfg.feed_h_dots} dots at {cfg.dpi} dpi)")
    ok(f"print width {cfg.total_width_dots} dots "
       f"({cfg.total_width_dots / cfg.dots_per_mm:.1f} mm)")

    if cfg.total_width_dots > 832:
        bad(f"print width {cfg.total_width_dots} dots exceeds the ZD230 head (832)",
            "reduce sticker_width_mm or column_gap_mm")
    if cfg.id_y + cfg.id_h_max > cfg.sticker_h_dots:
        bad("the second text line falls outside the sticker",
            "reduce id_y or id_h_max in config.json")
    if cfg.name_y + cfg.name_h_max > cfg.id_y:
        bad("the two text lines overlap", "increase id_y in config.json")
    return cfg


def check_api(cfg, sales_id: str | None) -> None:
    section("Booking server")
    import requests

    from . import api

    if not cfg.api_url:
        bad("the booking server address is not set on this PC",
            "start the app - it asks on first run - or copy "
            "config.local.example.json to config.local.json and fill in api_url")
        return

    if sales_id:
        try:
            booking = api.fetch(sales_id, cfg)
            ok(f"reached {cfg.api_url}")
            ok(f"lookup {sales_id}: {booking.patientname} / {booking.gender} / "
               f"{booking.age_year}y")
        except api.BookingError as exc:
            warn(f"lookup failed: {exc}",
                 "check the network, proxy or firewall from this PC")
        return

    # No ID given, so test reachability rather than a specific booking - a
    # dummy ID that returns "no booking" still proves the server answers, and
    # no real patient number has to be baked into the code.
    try:
        resp = requests.get(cfg.api_url, params={"SalesID": "PR0000000"},
                            timeout=cfg.api_timeout_s)
    except requests.exceptions.RequestException as exc:
        warn(f"cannot reach {cfg.api_url}: {exc}",
             "check the network, proxy or firewall from this PC")
        return

    if resp.status_code >= 500:
        warn(f"{cfg.api_url} answered HTTP {resp.status_code}",
             "the booking server may be down; try again shortly")
    else:
        ok(f"reached {cfg.api_url} (HTTP {resp.status_code})")
        ok("pass --sales-id <ID> to also test a real patient lookup")


def check_printer(cfg, test_print: bool) -> None:
    section("Printer")
    from . import output

    if cfg.output_mode == "tcp":
        ok(f"configured for network printing at {cfg.tcp_host}:{cfg.tcp_port}")
        if not cfg.tcp_host:
            bad("tcp_host is empty", "set the printer's IP address in config.json")
        return
    if cfg.output_mode == "file":
        warn(f"output_mode is 'file' - jobs go to {cfg.file_path}, not a printer",
             'set "output_mode": "windows" when you are ready to print')
        return

    printers = output.list_printers()
    if not printers:
        bad("Windows reports no printers at all", "install the ZD230 driver")
        return
    print(f"         {len(printers)} print queue(s) installed")

    zebras = [p for p in printers
              if any(h in p.lower() for h in output.ZEBRA_HINTS)]
    if not zebras:
        bad("no Zebra queue found",
            "install the ZDesigner ZD230 driver, or use output_mode 'tcp'")
        for name in printers:
            print(f"           - {name}")
        return

    for name in zebras:
        ok(f"Zebra queue: {name}")
        lowered = name.lower()
        if "epl" in lowered:
            bad(f"'{name}' looks like an EPL driver; this app sends ZPL",
                "install the ZDesigner ZD230 *ZPL* driver instead")
        if "300" in lowered and cfg.dpi != 300:
            warn(f"'{name}' mentions 300 dpi but config.json says {cfg.dpi}",
                 'set "dpi": 300 in config.json')
        if "203" in lowered and cfg.dpi != 203:
            warn(f"'{name}' mentions 203 dpi but config.json says {cfg.dpi}",
                 'set "dpi": 203 in config.json')

    selected = cfg.printer_name or zebras[0]
    if cfg.printer_name and cfg.printer_name not in printers:
        bad(f"config.json points at '{cfg.printer_name}', which is not installed",
            "run the app and use Tools -> Choose printer")
    else:
        ok(f"will print to: {selected}"
           + ("" if cfg.printer_name else "  (auto-detected)"))

    if test_print:
        from . import zpl
        from .api import Booking
        sample = zpl.build(
            Booking(salesid="PR0000000", patientname="TEST ALIGNMENT",
                    gender="Other", age_year=0, age_month=0, age_day=0), cfg)
        try:
            print("         " + output.send(
                zpl.batch([sample] * cfg.per_feed, cfg), cfg))
            ok(f"test page sent - expect one feed with {cfg.per_feed} stickers")
        except output.PrintError as exc:
            bad(f"test print failed: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check this PC's setup.")
    parser.add_argument("--test-print", action="store_true",
                        help="also send one test feed to the printer")
    parser.add_argument("--sales-id", metavar="ID",
                        help="also look this Sales ID up, to test end to end")
    args = parser.parse_args(argv)

    print("Tube Label Printer - setup check")
    print(f"running from {Path(__file__).resolve().parent.parent}")

    check_python()
    if problems:
        print("\nStopping: fix the Python problems above first.")
        return 1
    cfg = check_config()
    check_api(cfg, args.sales_id)
    check_printer(cfg, args.test_print)

    section("Result")
    if problems:
        print("NOT READY - fix these:")
        for item in problems:
            print(f"  * {item}")
    elif warnings:
        print("READY, with notes:")
        for item in warnings:
            print(f"  * {item}")
    else:
        print("READY. Everything checks out.")
        if not args.test_print:
            print("Run with --test-print to send a real test feed.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
