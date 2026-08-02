"""Desktop front end.

Built around a batch list rather than a single patient: scan a Sales ID, set how
many stickers that sample needs, add it, repeat for as many patients as you
like, then print the lot in one go. Blank stickers can be added deliberately,
and the last row is padded with blanks so the next batch starts on a fresh row.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import api, config, output, pdfproof, preview, zpl

BG = "#f4f6f8"


def _enable_dpi_awareness() -> None:
    """Lab PCs are often at 125-150% display scaling. Without this Windows
    bitmap-stretches the window and the text goes blurry; with it, Tk gets real
    pixels and we scale the fonts ourselves."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # system DPI aware
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


@dataclass
class QueueItem:
    qty: int
    label: zpl.LabelText | None = None          # None = deliberate blank
    booking: api.Booking | None = field(default=None, repr=False)

    @property
    def is_blank(self) -> bool:
        return self.label is None


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = config.load()
        self.queue: list[QueueItem] = []

        self.title("Molecular Pathology - Tube Label Printer")
        self.configure(bg=BG)

        # Scale the whole interface with the display, so it stays readable at
        # 100%, 125% or 150% without anyone having to change Windows settings.
        self.ui = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self.tk.call("tk", "scaling", self.winfo_fpixels("1i") / 72.0)

        # Row height does not follow the font automatically, so short lab PCs
        # end up with clipped, overlapping list rows.
        line = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        ttk.Style(self).configure("Treeview", rowheight=line + int(8 * self.ui))

        # Never open larger than the screen - a 1080p PC at 150% scaling has
        # far less room than the scaled-up ideal size.
        max_w = self.winfo_screenwidth() - int(60 * self.ui)
        max_h = self.winfo_screenheight() - int(110 * self.ui)
        width = min(int(820 * self.ui), max_w)
        height = min(int(800 * self.ui), max_h)
        self.minsize(min(int(700 * self.ui), max_w), min(int(520 * self.ui), max_h))
        self.geometry(f"{width}x{height}+{int(20 * self.ui)}+{int(20 * self.ui)}")

        self._build_menu()
        self._build_widgets()
        self._refresh_target()
        self._refresh()
        if not self.cfg.api_url:
            self.after(200, lambda: self._choose_api(first_run=True))
        self.after(100, lambda: self.sales_entry.focus_set())

    # ---------------------------------------------------------------- layout
    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        tools = tk.Menu(menu, tearoff=0)
        tools.add_command(label="Booking server URL...", command=self._choose_api)
        tools.add_command(label="Choose printer...", command=self._choose_printer)
        tools.add_command(label="Reload config.json", command=self._reload_config)
        tools.add_separator()
        tools.add_command(label="Calibrate media", command=self._calibrate)
        tools.add_command(label="Print test label", command=self._print_test)
        tools.add_command(label="Save PDF proof...", command=self._save_pdf)
        tools.add_command(label="Show ZPL for this batch", command=self._show_zpl)
        menu.add_cascade(label="Tools", menu=tools)
        self.config(menu=menu)

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        # --- add row --------------------------------------------------------
        top = tk.Frame(self, bg=BG)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))

        tk.Label(top, text="Sales ID", bg=BG, font=("Segoe UI", 10)).pack(side="left")
        self.sales_var = tk.StringVar()
        self.sales_entry = tk.Entry(top, textvariable=self.sales_var, width=16,
                                    font=("Consolas", 15))
        self.sales_entry.pack(side="left", padx=(8, 8))
        self.sales_entry.bind("<Return>", lambda _e: self._add())

        tk.Label(top, text="Stickers", bg=BG, font=("Segoe UI", 10)).pack(side="left")
        self.qty_var = tk.StringVar(value=str(self.cfg.default_qty))
        ttk.Spinbox(top, from_=1, to=99, width=4, textvariable=self.qty_var,
                    font=("Consolas", 13)).pack(side="left", padx=(6, 10))

        self.add_btn = tk.Button(top, text="Add to list", width=11,
                                 font=("Segoe UI", 9, "bold"), command=self._add)
        self.add_btn.pack(side="left")
        tk.Button(top, text="Add blank", width=10,
                  command=self._add_blank).pack(side="left", padx=(6, 0))

        self.lookup_var = tk.StringVar(value="Scan or type a Sales ID, then press Enter.")
        tk.Label(self, textvariable=self.lookup_var, bg=BG, anchor="w",
                 font=("Segoe UI", 9), fg="#4a5560").grid(
            row=1, column=0, sticky="ew", padx=12)

        # --- batch list -----------------------------------------------------
        list_frame = tk.LabelFrame(self, text=" Batch ", bg=BG, padx=8, pady=6)
        list_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=6)
        list_frame.columnconfigure(0, weight=1)

        cols = ("qty", "prno", "name", "sexage")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=7)
        for key, text, width, anchor in (
            ("qty", "Stickers", 80, "center"), ("prno", "PR No", 130, "w"),
            ("name", "Patient", 330, "w"), ("sexage", "Sex/Age", 90, "center"),
        ):
            self.tree.heading(key, text=text)
            self.tree.column(key, width=int(width * self.ui), anchor=anchor)
        self.tree.grid(row=0, column=0, sticky="ew")
        self.tree.bind("<Delete>", lambda _e: self._remove())

        side = tk.Frame(list_frame, bg=BG)
        side.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        for text, cmd in (("+1", lambda: self._bump(1)), ("-1", lambda: self._bump(-1)),
                          ("Remove", self._remove), ("Clear all", self._clear)):
            tk.Button(side, text=text, width=9, command=cmd).pack(pady=2)

        self.summary_var = tk.StringVar()
        tk.Label(self, textvariable=self.summary_var, bg=BG, anchor="w",
                 font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="sw",
                                                     padx=18, pady=(0, 0))

        # --- preview --------------------------------------------------------
        prev_frame = tk.LabelFrame(self, text=" Sheet preview (as it will print) ",
                                   bg=BG, padx=8, pady=8)
        prev_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=6)
        prev_frame.columnconfigure(0, weight=1)
        prev_frame.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(prev_frame, width=int(650 * self.ui),
                                height=int(200 * self.ui), highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(prev_frame, orient="vertical", command=self.canvas.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.bind("<Configure>", lambda _e: self._render_preview())

        self.warn_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.warn_var, bg=BG, fg="#a35400", anchor="w",
                 font=("Segoe UI", 9)).grid(row=4, column=0, sticky="ew", padx=12)

        # --- actions --------------------------------------------------------
        bottom = tk.Frame(self, bg=BG)
        bottom.grid(row=5, column=0, sticky="ew", padx=10, pady=(2, 8))
        self.print_btn = tk.Button(bottom, text="Print batch", width=16, height=1,
                                   state="disabled", font=("Segoe UI", 11, "bold"),
                                   command=self._print)
        self.print_btn.pack(side="left")
        tk.Button(bottom, text="Save PDF proof", width=15,
                  command=self._save_pdf).pack(side="left", padx=8)
        self.bind("<Control-p>", lambda _e: self._print())
        self.bind("<Escape>", lambda _e: self.sales_entry.focus_set())

        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(self, textvariable=self.status_var, bg="#dde3e8", anchor="w",
                 font=("Segoe UI", 9)).grid(row=6, column=0, sticky="ew")

    # ----------------------------------------------------------------- state
    def _slots(self) -> list[zpl.LabelText | None]:
        slots: list[zpl.LabelText | None] = []
        for item in self.queue:
            slots.extend([item.label] * item.qty)
        return zpl.pad_slots(slots, self.cfg, self.cfg.pad_with_blanks)

    def _refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, item in enumerate(self.queue):
            if item.is_blank:
                values = (item.qty, "-", "(blank sticker)", "-")
            else:
                values = (item.qty, item.label.prno, item.label.name,
                          item.label.sex_age)
            self.tree.insert("", "end", iid=str(i), values=values)

        slots = self._slots()
        filled = sum(1 for s in slots if s is not None)
        blanks = len(slots) - filled
        feeds = len(slots) // self.cfg.per_feed
        if filled or blanks:
            text = f"{filled} sticker(s)"
            if blanks:
                text += f" + {blanks} blank"
            self.summary_var.set(f"{text}  =  {feeds} feed(s) of "
                                 f"{self.cfg.per_feed}")
        else:
            self.summary_var.set("")

        truncated = {i.label.name for i in self.queue
                     if i.label is not None and i.label.name_truncated}
        self.warn_var.set(
            "Shortened to fit: " + ", ".join(sorted(truncated)) if truncated else "")

        self.print_btn.configure(state="normal" if filled else "disabled")
        self._render_preview()

    def _render_preview(self) -> None:
        width = self.canvas.winfo_width()
        if width < 50:                      # not laid out yet
            width = int(650 * self.ui)
        # Cap the width so a wide window shows more feeds rather than fewer,
        # enormous ones.
        width = min(width - int(16 * self.ui), int(640 * self.ui))
        preview.draw(self.canvas, self._slots(), self.cfg, target_width_px=width)

    def _refresh_target(self) -> None:
        mode = self.cfg.output_mode
        if mode == "windows":
            try:
                target = output.resolve_printer(self.cfg)
            except output.PrintError:
                target = "no Zebra queue found - set one via Tools"
        elif mode == "tcp":
            target = f"{self.cfg.tcp_host or '(unset)'}:{self.cfg.tcp_port}"
        else:
            target = self.cfg.file_path
        self.status_var.set(f"Ready.   Output: {mode} -> {target}")

    def _qty(self) -> int:
        try:
            return max(1, min(99, int(self.qty_var.get())))
        except ValueError:
            return self.cfg.default_qty

    def _selected(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    # --------------------------------------------------------------- actions
    def _add(self) -> None:
        sid = self.sales_var.get().strip()
        if not sid:
            return
        qty = self._qty()
        self.add_btn.configure(state="disabled")
        self.lookup_var.set(f"Looking up {sid.upper()} ...")

        def work() -> None:
            try:
                booking = api.fetch(sid, self.cfg)
            except api.BookingError as exc:
                self.after(0, lambda: self._add_failed(str(exc)))
                return
            self.after(0, lambda: self._add_done(booking, qty))

        threading.Thread(target=work, daemon=True).start()

    def _add_done(self, booking: api.Booking, qty: int) -> None:
        self.add_btn.configure(state="normal")
        label = zpl.build(booking, self.cfg)

        # Same patient scanned twice: bump the count instead of listing them
        # separately, so the batch stays readable.
        for item in self.queue:
            if item.label is not None and item.label.prno == label.prno:
                item.qty += qty
                break
        else:
            self.queue.append(QueueItem(qty=qty, label=label, booking=booking))

        self.lookup_var.set(f"Added {qty} x {label.prno}  {booking.patientname}  "
                            f"{label.sex_age}")
        self.sales_var.set("")
        self.qty_var.set(str(self.cfg.default_qty))
        self.sales_entry.focus_set()
        self._refresh()

    def _add_failed(self, message: str) -> None:
        self.add_btn.configure(state="normal")
        self.lookup_var.set(message)
        self.sales_entry.focus_set()
        self.sales_entry.selection_range(0, "end")

    def _add_blank(self) -> None:
        self.queue.append(QueueItem(qty=self._qty()))
        self.lookup_var.set(f"Added {self._qty()} blank sticker(s).")
        self.sales_entry.focus_set()
        self._refresh()

    def _bump(self, delta: int) -> None:
        index = self._selected()
        if index is None:
            return
        item = self.queue[index]
        item.qty = max(1, item.qty + delta)
        self._refresh()
        self.tree.selection_set(str(index))

    def _remove(self) -> None:
        index = self._selected()
        if index is None:
            return
        self.queue.pop(index)
        self._refresh()

    def _clear(self) -> None:
        self.queue.clear()
        self.sales_var.set("")
        self.lookup_var.set("Scan or type a Sales ID, then press Enter.")
        self._refresh()
        self.sales_entry.focus_set()

    def _print(self) -> None:
        slots = self._slots()
        filled = sum(1 for s in slots if s is not None)
        if not filled:
            return
        data = zpl.batch(slots, self.cfg)
        try:
            result = output.send(data, self.cfg)
        except output.PrintError as exc:
            self.status_var.set(str(exc))
            messagebox.showerror("Print failed", str(exc))
            return
        feeds = len(slots) // self.cfg.per_feed
        self.status_var.set(
            f"{datetime.now():%H:%M:%S}  Sent {filled} sticker(s) in {feeds} "
            f"feed(s).   {result}")
        self._clear()

    def _calibrate(self) -> None:
        """Make the printer re-learn the media, so it finds the 25 mm gap
        between labels. It feeds a few blank labels doing so."""
        if not messagebox.askokcancel(
                "Calibrate media",
                "The printer will feed several blank labels while it measures "
                "the gap between them.\n\nMake sure labels are loaded, then "
                "click OK."):
            return
        try:
            output.send("~JC\n", self.cfg)
        except output.PrintError as exc:
            messagebox.showerror("Calibration failed", str(exc))
            return
        self.status_var.set("Calibration sent - watch the printer feed labels.")

    def _print_test(self) -> None:
        sample = zpl.build(
            api.Booking(salesid="PR0000000", patientname="TEST ALIGNMENT LABEL",
                        gender="Other", age_year=0, age_month=0, age_day=0),
            self.cfg)
        try:
            output.send(zpl.batch([sample] * self.cfg.per_feed, self.cfg), self.cfg)
        except output.PrintError as exc:
            messagebox.showerror("Print failed", str(exc))
            return
        self.status_var.set("Test label sent.")

    def _save_pdf(self) -> None:
        slots = self._slots()
        if not any(s is not None for s in slots):
            messagebox.showinfo("Empty batch", "Add at least one Sales ID first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save PDF proof", defaultextension=".pdf",
            initialfile=f"labels-{datetime.now():%Y%m%d-%H%M}.pdf",
            filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        out = pdfproof.render(slots, self.cfg, path, heading="Eppendorf tube labels")
        self.status_var.set(f"Proof written to {out}")
        try:
            os.startfile(out)
        except OSError:
            pass

    def _show_zpl(self) -> None:
        slots = self._slots()
        if not any(s is not None for s in slots):
            messagebox.showinfo("Empty batch", "Add at least one Sales ID first.")
            return
        win = tk.Toplevel(self)
        win.title("ZPL")
        text = tk.Text(win, width=74, height=30, font=("Consolas", 9))
        text.pack(fill="both", expand=True)
        text.insert("1.0", zpl.batch(slots, self.cfg))
        text.configure(state="disabled")

    def _choose_api(self, first_run: bool = False) -> None:
        """The booking server address is deliberately not in the source, so it
        is asked for once per PC and kept in the untracked local config."""
        win = tk.Toplevel(self)
        win.title("Booking server")
        win.transient(self)
        win.grab_set()
        message = ("Enter the booking server address for this site.\n"
                   "It is saved to config.local.json on this PC only.")
        if first_run:
            message = "Welcome. " + message
        tk.Label(win, text=message, justify="left").pack(
            padx=14, pady=(14, 8), anchor="w")

        var = tk.StringVar(value=self.cfg.api_url)
        entry = tk.Entry(win, textvariable=var, width=58, font=("Consolas", 10))
        entry.pack(padx=14)
        entry.focus_set()
        tk.Label(win, text="for example  https://server.example/viewBookingHeader",
                 fg="#6a737c").pack(padx=14, pady=(4, 0), anchor="w")

        def apply() -> None:
            url = var.get().strip()
            if url and not url.lower().startswith(("http://", "https://")):
                messagebox.showwarning("Booking server",
                                       "The address should start with http:// "
                                       "or https://", parent=win)
                return
            self.cfg.api_url = url
            config.save_local(self.cfg)
            win.destroy()
            self._refresh_target()

        entry.bind("<Return>", lambda _e: apply())
        tk.Button(win, text="Save", width=12, command=apply).pack(pady=12)
        win.wait_window()

    def _choose_printer(self) -> None:
        printers = output.list_printers()
        if not printers:
            messagebox.showinfo("No printers", "Windows reports no print queues.")
            return
        win = tk.Toplevel(self)
        win.title("Choose printer")
        win.transient(self)
        tk.Label(win, text="Windows print queue to send raw ZPL to:").pack(
            padx=12, pady=(12, 6), anchor="w")
        var = tk.StringVar(value=self.cfg.printer_name or (output.detect_zebra() or ""))
        ttk.Combobox(win, values=printers, textvariable=var, width=52,
                     state="readonly").pack(padx=12)

        def apply() -> None:
            self.cfg.printer_name = var.get()
            self.cfg.output_mode = "windows"
            config.save_local(self.cfg)
            self._refresh_target()
            win.destroy()

        tk.Button(win, text="Use this printer", command=apply).pack(pady=12)

    def _reload_config(self) -> None:
        self.cfg = config.load()
        for item in self.queue:
            if item.booking is not None:
                item.label = zpl.build(item.booking, self.cfg)
        self._refresh_target()
        self._refresh()


def main() -> None:
    _enable_dpi_awareness()
    App().mainloop()
