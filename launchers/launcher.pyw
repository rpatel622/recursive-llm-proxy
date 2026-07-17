"""Graphical bootstrap for Local RLM Cowork.

This file is intentionally runnable with pythonw so first-time setup does not
require a terminal. It creates a private virtual environment, installs the
browser stack, starts the Gradio control surface, and opens it in the browser.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import venv
import webbrowser
from pathlib import Path
from typing import Optional

try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError as exc:  # pragma: no cover - platform packaging issue
    raise SystemExit("Python was installed without Tk support") from exc


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path.home() / ".recursive-llm"
VENV_DIR = STATE_DIR / "app-venv"
LOG_DIR = STATE_DIR / "logs"
LOG_FILE = LOG_DIR / "launcher.log"
UI_URL = "http://127.0.0.1:7860"


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "pythonw.exe"
    return VENV_DIR / "bin" / "python"


def _venv_console_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


class Launcher:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Local RLM Cowork")
        self.root.geometry("560x300")
        self.root.resizable(False, False)
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.log_handle = None

        tk.Label(
            self.root,
            text="Local RLM Cowork",
            font=("TkDefaultFont", 18, "bold"),
        ).pack(pady=(24, 6))
        tk.Label(
            self.root,
            text="Private local AI in your browser",
            font=("TkDefaultFont", 11),
        ).pack()

        self.status = tk.StringVar(value="Ready to set up")
        tk.Label(
            self.root,
            textvariable=self.status,
            wraplength=500,
            justify="center",
        ).pack(pady=24)

        self.progress = tk.Label(self.root, text="")
        self.progress.pack()

        buttons = tk.Frame(self.root)
        buttons.pack(pady=22)
        self.start_button = tk.Button(
            buttons,
            text="Set up and open",
            width=18,
            command=self.start,
        )
        self.start_button.grid(row=0, column=0, padx=6)
        self.open_button = tk.Button(
            buttons,
            text="Open browser",
            width=14,
            state="disabled",
            command=lambda: webbrowser.open(UI_URL),
        )
        self.open_button.grid(row=0, column=1, padx=6)
        self.stop_button = tk.Button(
            buttons,
            text="Stop",
            width=10,
            state="disabled",
            command=self.stop,
        )
        self.stop_button.grid(row=0, column=2, padx=6)

        tk.Button(
            self.root,
            text="Open diagnostics folder",
            relief="flat",
            command=self.open_logs,
        ).pack()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def set_status(self, message: str) -> None:
        self.root.after(0, self.status.set, message)

    def fail(self, message: str) -> None:
        self.set_status(message)
        self.root.after(0, lambda: self.start_button.config(state="normal"))
        self.root.after(0, lambda: messagebox.showerror("Local RLM Cowork", message))

    def start(self) -> None:
        self.start_button.config(state="disabled")
        threading.Thread(target=self._bootstrap, daemon=True).start()

    def _bootstrap(self) -> None:
        try:
            if sys.version_info < (3, 11):
                raise RuntimeError(
                    "Python 3.11 or newer is required. Install it from python.org, "
                    "then double-click this launcher again."
                )
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            STATE_DIR.mkdir(parents=True, exist_ok=True)

            if not _venv_console_python().exists():
                self.set_status("Preparing the private app environment…")
                venv.EnvBuilder(with_pip=True).create(VENV_DIR)

            python = _venv_console_python()
            self.set_status("Installing or updating Local RLM Cowork…")
            install = subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "-e",
                    f"{ROOT}[proxy,ui,cowork]",
                ],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=1800,
            )
            LOG_FILE.write_text(install.stdout or "", encoding="utf-8")
            if install.returncode != 0:
                raise RuntimeError(
                    "Setup could not finish. Open the diagnostics folder for details."
                )

            if _port_open("127.0.0.1", 7860):
                self.set_status("Local RLM Cowork is already running.")
                self.root.after(0, lambda: self.open_button.config(state="normal"))
                webbrowser.open(UI_URL)
                return

            self.set_status("Starting the setup screen…")
            self.log_handle = LOG_FILE.open("ab")
            executable = _venv_python()
            if not executable.exists():
                executable = python
            creationflags = 0
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.process = subprocess.Popen(
                [str(executable), "-m", "rlm_proxy.ui"],
                cwd=str(ROOT),
                stdin=subprocess.DEVNULL,
                stdout=self.log_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )

            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError(
                        "The setup screen stopped unexpectedly. Open diagnostics for details."
                    )
                if _port_open("127.0.0.1", 7860):
                    self.set_status(
                        "Ready. Choose your GGUF model, then press Start complete stack."
                    )
                    self.root.after(0, lambda: self.open_button.config(state="normal"))
                    self.root.after(0, lambda: self.stop_button.config(state="normal"))
                    webbrowser.open(UI_URL)
                    return
                time.sleep(0.5)
            raise RuntimeError("The setup screen took too long to start.")
        except Exception as exc:
            self.fail(str(exc))

    def stop(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
        self.process = None
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None
        self.status.set("Stopped")
        self.stop_button.config(state="disabled")
        self.open_button.config(state="disabled")
        self.start_button.config(state="normal")

    def open_logs(self) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(LOG_DIR))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(LOG_DIR)])
        else:
            subprocess.Popen(["xdg-open", str(LOG_DIR)])

    def close(self) -> None:
        self.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    Launcher().run()
