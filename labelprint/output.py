"""Getting raw ZPL to the printer.

Three routes, because sites differ:
  windows - RAW pass-through to a Windows print queue (needs the ZDesigner or
            Zebra driver installed; the driver must not be a "graphics" one)
  tcp     - straight to port 9100 on a network/Wi-Fi ZD230
  file    - write a .zpl file, for testing without hardware
"""

from __future__ import annotations

import socket
from pathlib import Path

from .config import Config

ZEBRA_HINTS = ("zdesigner", "zebra", "zd230", "zpl", "gk420", "gx420")


class PrintError(Exception):
    pass


def list_printers() -> list[str]:
    try:
        import win32print
    except ImportError:
        return []
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p[2] for p in win32print.EnumPrinters(flags, None, 1)]


def detect_zebra() -> str | None:
    for name in list_printers():
        lowered = name.lower()
        if any(hint in lowered for hint in ZEBRA_HINTS):
            return name
    return None


def resolve_printer(cfg: Config) -> str:
    if cfg.printer_name:
        return cfg.printer_name
    found = detect_zebra()
    if not found:
        raise PrintError(
            "No Zebra print queue found. Set \"printer_name\" in config.json, "
            "or switch \"output_mode\" to \"tcp\" and set the printer's IP."
        )
    return found


def _send_windows(cfg: Config, data: bytes) -> str:
    try:
        import win32print
    except ImportError:
        raise PrintError("pywin32 is not installed. Run: pip install pywin32")

    name = resolve_printer(cfg)
    try:
        handle = win32print.OpenPrinter(name)
    except Exception as exc:
        raise PrintError(f"Cannot open printer '{name}': {exc}")
    try:
        job = win32print.StartDocPrinter(handle, 1, ("Barcode labels", None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, data)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    except Exception as exc:
        raise PrintError(f"Printing to '{name}' failed: {exc}")
    finally:
        win32print.ClosePrinter(handle)
    return f"Sent to '{name}' (job {job})."


def _send_tcp(cfg: Config, data: bytes) -> str:
    if not cfg.tcp_host:
        raise PrintError("Set \"tcp_host\" in config.json to the printer's IP address.")
    try:
        with socket.create_connection((cfg.tcp_host, cfg.tcp_port), timeout=10) as sock:
            sock.sendall(data)
    except OSError as exc:
        raise PrintError(f"Cannot reach {cfg.tcp_host}:{cfg.tcp_port} - {exc}")
    return f"Sent to {cfg.tcp_host}:{cfg.tcp_port}."


def _send_file(cfg: Config, data: bytes) -> str:
    path = Path(cfg.file_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    path.write_bytes(data)
    return f"Written to {path}."


def send(zpl: str, cfg: Config) -> str:
    data = zpl.encode("utf-8")
    mode = (cfg.output_mode or "windows").lower()
    if mode == "windows":
        return _send_windows(cfg, data)
    if mode == "tcp":
        return _send_tcp(cfg, data)
    if mode == "file":
        return _send_file(cfg, data)
    raise PrintError(f"Unknown output_mode '{cfg.output_mode}'.")
