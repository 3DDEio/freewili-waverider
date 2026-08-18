#!/usr/bin/env python3
"""WaveRider one-click installer for FreeWili 2."""

from __future__ import annotations

import queue
import sys
import threading
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tkinter as tk
from tkinter import messagebox, ttk

from installer.device_install import find_main_ports, install_waverider


BG = "#07151b"
CARD = "#0d222a"
EDGE = "#21404b"
TEXT = "#e8f4f7"
MUTED = "#8ca8b2"
CYAN = "#43d9c0"
BLUE = "#3195d8"
GREEN = "#41d486"
YELLOW = "#f7c84b"
RED = "#ff6b6b"


class InstallerApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("WaveRider Installer")
        self.root.geometry("860x690")
        self.root.minsize(760, 620)
        self.root.configure(bg=BG)
        self.devices: dict[str, str] = {}
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False
        self._build_ui()
        self.root.after(80, self._drain_events)
        self.root.after(120, self.refresh_devices)

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=BG, padx=24, pady=20)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer,
            text="WAVERIDER",
            font=("Menlo", 28, "bold"),
            fg=TEXT,
            bg=BG,
        ).pack(anchor="w")
        tk.Label(
            outer,
            text="ONE-CLICK INSTALLER  •  FREEWILI 2",
            font=("Menlo", 11),
            fg=CYAN,
            bg=BG,
        ).pack(anchor="w", pady=(1, 14))

        card = tk.Frame(
            outer,
            bg=CARD,
            highlightbackground=EDGE,
            highlightthickness=1,
            padx=16,
            pady=14,
        )
        card.pack(fill="x")
        tk.Label(
            card,
            text="DEVICE",
            font=("Menlo", 9, "bold"),
            fg=MUTED,
            bg=CARD,
        ).grid(row=0, column=0, sticky="w")

        self.device_var = tk.StringVar()
        self.device_box = ttk.Combobox(
            card,
            textvariable=self.device_var,
            state="readonly",
            font=("Menlo", 11),
            width=58,
        )
        self.device_box.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.refresh_button = tk.Button(
            card,
            text="Refresh",
            command=self.refresh_devices,
            bg="#16333d",
            fg=TEXT,
            activebackground="#204957",
            activeforeground=TEXT,
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
        )
        self.refresh_button.grid(row=1, column=1, padx=(10, 0), pady=(6, 0))
        card.columnconfigure(0, weight=1)

        self.device_status = tk.Label(
            card,
            text="Looking for a connected FreeWili 2…",
            font=("Menlo", 9),
            fg=YELLOW,
            bg=CARD,
            anchor="w",
        )
        self.device_status.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        details = tk.Frame(outer, bg=BG, pady=14)
        details.pack(fill="x")
        self._detail(details, 0, "1", "Apps menu", "Installs Apps → Radio → WaveRider")
        self._detail(details, 1, "2", "CM0 receiver", "Installs RTL-SDR services with rollback")
        self._detail(details, 2, "3", "Safe handoff", "Does not replace Main or Display firmware")

        progress_card = tk.Frame(
            outer,
            bg=CARD,
            highlightbackground=EDGE,
            highlightthickness=1,
            padx=16,
            pady=13,
        )
        progress_card.pack(fill="x")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "WaveRider.Horizontal.TProgressbar",
            troughcolor="#112a33",
            background=CYAN,
            borderwidth=0,
        )
        self.progress_value = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(
            progress_card,
            variable=self.progress_value,
            maximum=100,
            style="WaveRider.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x")
        self.step = tk.Label(
            progress_card,
            text="Ready for device check",
            font=("Menlo", 10),
            fg=MUTED,
            bg=CARD,
            anchor="w",
        )
        self.step.pack(fill="x", pady=(8, 0))

        log_card = tk.Frame(
            outer,
            bg=CARD,
            highlightbackground=EDGE,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        log_card.pack(fill="both", expand=True, pady=(14, 12))
        tk.Label(
            log_card,
            text="INSTALL LOG",
            font=("Menlo", 9, "bold"),
            fg=MUTED,
            bg=CARD,
        ).pack(anchor="w", padx=4)
        self.log = tk.Text(
            log_card,
            height=10,
            bg=CARD,
            fg=MUTED,
            insertbackground=TEXT,
            font=("Menlo", 9),
            bd=0,
            wrap="word",
            state="disabled",
        )
        self.log.pack(fill="both", expand=True, pady=(6, 0))

        actions = tk.Frame(outer, bg=BG)
        actions.pack(fill="x")
        tk.Label(
            actions,
            text="Keep both SD cards installed and connect the FreeWili USB cable.",
            font=("Menlo", 9),
            fg=MUTED,
            bg=BG,
        ).pack(side="left")
        self.install_button = tk.Button(
            actions,
            text="Install WaveRider",
            command=self.start_install,
            bg=CYAN,
            fg="#031013",
            activebackground=GREEN,
            activeforeground="#031013",
            disabledforeground="#587078",
            disabledbackground="#183139",
            font=("Menlo", 11, "bold"),
            bd=0,
            padx=20,
            pady=11,
            cursor="hand2",
            state="disabled",
        )
        self.install_button.pack(side="right")

    def _detail(self, parent: tk.Widget, column: int, number: str, title: str, body: str) -> None:
        frame = tk.Frame(parent, bg=BG)
        frame.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 8, 0))
        parent.columnconfigure(column, weight=1)
        tk.Label(
            frame,
            text=number,
            font=("Menlo", 13, "bold"),
            fg=CYAN,
            bg=BG,
        ).pack(side="left", padx=(0, 9))
        copy = tk.Frame(frame, bg=BG)
        copy.pack(side="left", fill="x", expand=True)
        tk.Label(copy, text=title, font=("Menlo", 10, "bold"), fg=TEXT, bg=BG).pack(anchor="w")
        tk.Label(copy, text=body, font=("Menlo", 8), fg=MUTED, bg=BG, wraplength=210, justify="left").pack(anchor="w")

    def refresh_devices(self) -> None:
        if self.running:
            return
        self.device_status.configure(text="Looking for a connected FreeWili 2…", fg=YELLOW)
        self.install_button.configure(state="disabled")
        try:
            found = find_main_ports()
        except Exception as error:
            self.devices = {}
            self.device_box.configure(values=[])
            self.device_status.configure(text=str(error), fg=RED)
            self._append_log(str(error))
            return
        self.devices = dict(found)
        labels = list(self.devices)
        self.device_box.configure(values=labels)
        if labels:
            self.device_var.set(labels[0])
            self.device_status.configure(
                text=f"Ready: {len(labels)} FreeWili device{'s' if len(labels) != 1 else ''} found",
                fg=GREEN,
            )
            self.install_button.configure(state="normal")
        else:
            self.device_var.set("")
            self.device_status.configure(
                text="No FreeWili 2 found. Connect its USB cable, then click Refresh.",
                fg=YELLOW,
            )

    def start_install(self) -> None:
        label = self.device_var.get()
        port = self.devices.get(label)
        if not port or self.running:
            return
        if not messagebox.askyesno(
            "Install WaveRider",
            "Install or update WaveRider on the selected FreeWili 2?\n\n"
            "This updates the WaveRider Apps-menu file and CM0 receiver service. "
            "It does not replace stock Main or Display firmware.",
        ):
            return
        self.running = True
        self.progress_value.set(0)
        self.step.configure(text="Starting installation", fg=TEXT)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.install_button.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        threading.Thread(target=self._install_worker, args=(port,), daemon=True).start()

    def _install_worker(self, port: str) -> None:
        try:
            install_waverider(
                ROOT,
                port,
                progress=lambda value, message: self.events.put(
                    ("progress", (value, message))
                ),
                log=lambda message: self.events.put(("log", message)),
            )
        except Exception as error:
            self.events.put(("log", traceback.format_exc()))
            self.events.put(("error", str(error)))
        else:
            self.events.put(("done", None))

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                value, message = payload
                self.progress_value.set(value)
                self.step.configure(text=message, fg=TEXT)
            elif kind == "log":
                self._append_log(str(payload))
            elif kind == "error":
                self.running = False
                self.step.configure(text=f"Installation stopped: {payload}", fg=RED)
                self.refresh_button.configure(state="normal")
                self.install_button.configure(state="normal" if self.devices else "disabled")
                messagebox.showerror(
                    "WaveRider installation stopped",
                    f"{payload}\n\nNothing replaces stock firmware. See the install log for details.",
                )
            elif kind == "done":
                self.running = False
                self.progress_value.set(100)
                self.step.configure(text="WaveRider is installed and ready", fg=GREEN)
                self.refresh_button.configure(state="normal")
                self.install_button.configure(state="normal")
                messagebox.showinfo(
                    "WaveRider installed",
                    "WaveRider is ready. Return to the FreeWili home screen and open "
                    "Apps → Radio → WaveRider. The first receiver startup can take a short while.",
                )
        self.root.after(80, self._drain_events)

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    InstallerApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
