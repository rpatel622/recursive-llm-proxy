"""Graphical bootstrap for Local RLM Cowork.

Release bundles contain a relocatable Python runtime, an offline wheelhouse, the
application, and llama.cpp. Source checkouts retain a managed-venv fallback.
"""

from __future__ import annotations

import json
import os
import shutil
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
except ImportError as exc:  # pragma: no cover - packaging failure
    raise SystemExit("The bundled runtime was built without Tk support") from exc


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path.home() / ".recursive-llm"
VENV_DIR = STATE_DIR / "app-venv"
LOG_DIR = STATE_DIR / "logs"
LOG_FILE = LOG_DIR / "launcher.log"
MANIFEST_FILE = ROOT / "bundle-manifest.json"
WHEELHOUSE = ROOT / "runtime" / "wheelhouse"
UI_URL = "http://127.0.0.1:7860"


def _runtime_python(console: bool = True) -> Path:
    runtime = ROOT / "runtime" / "python"
    if os.name == "nt":
        return runtime / ("python.exe" if console else "pythonw.exe")
    return runtime / "bin" / "python3"


def _venv_python(console: bool = True) -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / ("python.exe" if console else "pythonw.exe")
    return VENV_DIR / "bin" / "python"


def _bundled_llama() -> Optional[Path]:
    names = ["llama-server.exe", "llama-server"]
    for name in names:
        matches = list((ROOT / "runtime" / "llama").rglob(name))
        if matches:
            return matches[0].resolve()
    return None


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _run_logged(command: list[str], *, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        creationflags=_creation_flags(),
    )
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write("\n$ " + " ".join(command) + "\n")
        log.write(result.stdout or "")
    return result


class Launcher:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Local RLM Cowork")
        self.root.geometry("610x360")
        self.root.resizable(False, False)
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.log_handle = None
        self.bundled = MANIFEST_FILE.is_file() and _runtime_python().is_file()

        tk.Label(self.root, text="Local RLM Cowork", font=("TkDefaultFont", 18, "bold")).pack(
            pady=(24, 6)
        )
        subtitle = "Private local AI in your browser"
        if self.bundled:
            subtitle += " · bundled edition"
        tk.Label(self.root, text=subtitle, font=("TkDefaultFont", 11)).pack()

        self.status = tk.StringVar(value="Ready")
        tk.Label(
            self.root,
            textvariable=self.status,
            wraplength=540,
            justify="center",
        ).pack(pady=22)

        self.details = tk.StringVar(value=self._bundle_details())
        tk.Label(
            self.root,
            textvariable=self.details,
            wraplength=540,
            justify="center",
            fg="#555555",
        ).pack()

        buttons = tk.Frame(self.root)
        buttons.pack(pady=22)
        self.start_button = tk.Button(
            buttons,
            text="Open Local RLM" if self.bundled else "Set up and open",
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

        utility = tk.Frame(self.root)
        utility.pack()
        tk.Button(
            utility,
            text="Repair installation",
            relief="flat",
            command=self.repair,
        ).grid(row=0, column=0, padx=12)
        tk.Button(
            utility,
            text="Open diagnostics",
            relief="flat",
            command=self.open_logs,
        ).grid(row=0, column=1, padx=12)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _bundle_details(self) -> str:
        if not self.bundled:
            return "Source mode: a private environment will be created on first launch."
        try:
            manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
            return (
                f"Bundle {manifest.get('version', 'development')} · "
                f"Python {manifest.get('python_version', 'bundled')} · "
                f"llama.cpp {manifest.get('llama_release', 'bundled')}"
            )
        except Exception:
            return "Bundled runtime detected"

    def set_status(self, message: str) -> None:
        self.root.after(0, self.status.set, message)

    def fail(self, message: str) -> None:
        self.set_status(message)
        self.root.after(0, lambda: self.start_button.config(state="normal"))
        self.root.after(0, lambda: messagebox.showerror("Local RLM Cowork", message))

    def start(self) -> None:
        self.start_button.config(state="disabled")
        threading.Thread(target=self._bootstrap, daemon=True).start()

    def _select_python(self) -> Path:
        if self.bundled:
            python = _runtime_python()
            if not python.is_file():
                raise RuntimeError("The bundled Python runtime is missing. Download a fresh bundle.")
            return python

        if sys.version_info < (3, 11):
            raise RuntimeError("Python 3.11 or newer is required for source-mode setup.")
        if not _venv_python().exists():
            self.set_status("Preparing the private application environment…")
            venv.EnvBuilder(with_pip=True).create(VENV_DIR)
        return _venv_python()

    def _verify_runtime(self, python: Path) -> None:
        self.set_status("Checking the local application…")
        result = _run_logged(
            [
                str(python),
                "-c",
                "import gradio, open_webui, rlm_proxy; print('runtime-ok')",
            ],
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "The local application is incomplete. Press Repair installation, then try again."
            )

    def _install_source_mode(self, python: Path) -> None:
        self.set_status("Installing or updating Local RLM Cowork…")
        result = _run_logged(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-e",
                f"{ROOT}[proxy,ui,cowork]",
            ]
        )
        if result.returncode != 0:
            raise RuntimeError("Setup could not finish. Open diagnostics for details.")

    def _bootstrap(self) -> None:
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            python = self._select_python()
            if not self.bundled:
                self._install_source_mode(python)
            self._verify_runtime(python)

            if _port_open("127.0.0.1", 7860):
                self.set_status("Local RLM is already running.")
                self.root.after(0, lambda: self.open_button.config(state="normal"))
                webbrowser.open(UI_URL)
                return

            self.set_status("Starting the local control screen…")
            self.log_handle = LOG_FILE.open("ab")
            executable = python
            if os.name == "nt":
                no_console = _runtime_python(False) if self.bundled else _venv_python(False)
                if no_console.exists():
                    executable = no_console

            env = dict(os.environ)
            llama = _bundled_llama()
            if llama is not None:
                env["RLM_BUNDLED_LLAMA_SERVER"] = str(llama)

            self.process = subprocess.Popen(
                [str(executable), "-m", "rlm_proxy.ui"],
                cwd=str(ROOT),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=self.log_handle,
                stderr=subprocess.STDOUT,
                creationflags=_creation_flags(),
            )

            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError("The control screen stopped. Open diagnostics for details.")
                if _port_open("127.0.0.1", 7860):
                    self.set_status("Ready. Choose a GGUF model and start the complete stack.")
                    self.root.after(0, lambda: self.open_button.config(state="normal"))
                    self.root.after(0, lambda: self.stop_button.config(state="normal"))
                    webbrowser.open(UI_URL)
                    return
                time.sleep(0.5)
            raise RuntimeError("The control screen took too long to start.")
        except Exception as exc:
            self.fail(str(exc))

    def repair(self) -> None:
        self.start_button.config(state="disabled")
        threading.Thread(target=self._repair, daemon=True).start()

    def _repair(self) -> None:
        try:
            self.stop()
            if self.bundled:
                python = _runtime_python()
                if not WHEELHOUSE.is_dir():
                    raise RuntimeError("Offline repair files are missing. Download a fresh bundle.")
                self.set_status("Repairing the bundled application from local files…")
                result = _run_logged(
                    [
                        str(python),
                        "-m",
                        "pip",
                        "install",
                        "--no-index",
                        "--find-links",
                        str(WHEELHOUSE),
                        "--force-reinstall",
                        "recursive-llm[proxy,ui,cowork]",
                    ]
                )
                if result.returncode != 0:
                    raise RuntimeError("Repair failed. Open diagnostics or download a fresh bundle.")
            else:
                if VENV_DIR.exists():
                    shutil.rmtree(VENV_DIR)
                python = self._select_python()
                self._install_source_mode(python)
            self._verify_runtime(python)
            self.set_status("Repair completed. Press Open Local RLM.")
            self.root.after(0, lambda: messagebox.showinfo("Local RLM Cowork", "Repair completed."))
        except Exception as exc:
            self.fail(str(exc))
        finally:
            self.root.after(0, lambda: self.start_button.config(state="normal"))

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
        self.set_status("Stopped")
        self.root.after(0, lambda: self.stop_button.config(state="disabled"))
        self.root.after(0, lambda: self.open_button.config(state="disabled"))
        self.root.after(0, lambda: self.start_button.config(state="normal"))

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
