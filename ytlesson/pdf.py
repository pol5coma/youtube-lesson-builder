"""Turning a rendered lesson page into a PDF.

Conversion goes through a headless Chromium-family browser rather than a
Python rendering library. It adds no dependency to install, and it is the same
engine the page was designed against, so the PDF matches what Cmd+P produces.

Page geometry is not set here — it comes from the `@page` rule in the rendered
stylesheet, so both paths agree.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple

# Headless Chrome writes the PDF and then, in several versions, simply does not
# exit. Waiting on the process is therefore not a usable completion signal, so
# the file itself is watched and the browser stopped once its size has settled.
_POLL_SECONDS = 0.2
_SETTLE_CHECKS = 4


class PdfError(Exception):
    """Raised when a browser was found but the conversion itself failed."""


# Chromium forks, most-likely first. Anything that accepts --print-to-pdf works.
_MAC = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
_WINDOWS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
_ON_PATH = [
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "brave-browser",
    "microsoft-edge",
    "chrome",
]


def _resolve(candidate: str) -> Optional[str]:
    if Path(candidate).is_file() and os.access(candidate, os.X_OK):
        return candidate
    return shutil.which(candidate)


def find_browser(explicit: Optional[str] = None) -> Optional[str]:
    """Locates a usable browser, or returns None so the caller can carry on.

    Missing browsers are not an error: the HTML is still worth having, and
    someone who just cloned the repo should not see a failed run.
    """
    # An explicit --browser is honoured strictly. Silently falling back to a
    # different one would hide a typo in the path they gave.
    if explicit:
        return _resolve(explicit)

    from_env = os.environ.get("CHROME")
    if from_env and _resolve(from_env):
        return _resolve(from_env)

    if sys.platform == "darwin":
        paths = _MAC
    elif sys.platform.startswith("win"):
        paths = _WINDOWS
    else:
        paths = []

    for path in paths:
        if Path(path).is_file():
            return path

    for name in _ON_PATH:
        found = shutil.which(name)
        if found:
            return found

    return None


def _stop(proc: subprocess.Popen) -> str:
    """Ends the browser and returns whatever it said on stderr."""
    if proc.poll() is None:
        proc.terminate()
    try:
        _, err = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        _, err = proc.communicate()
    return (err or "").strip()


def _attempt(argv, pdf_path: Path, timeout: int) -> Tuple[bool, str]:
    """Runs one browser invocation, watching for the PDF to finish being written."""
    if pdf_path.exists():
        pdf_path.unlink()

    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + timeout
    previous, settled = -1, 0
    try:
        while time.monotonic() < deadline:
            size = pdf_path.stat().st_size if pdf_path.is_file() else 0
            settled = settled + 1 if size and size == previous else 0
            previous = size

            if settled >= _SETTLE_CHECKS:
                return True, ""
            if proc.poll() is not None:  # exited on its own; nothing more is coming
                break
            time.sleep(_POLL_SECONDS)
    finally:
        stderr = _stop(proc)

    if pdf_path.is_file() and pdf_path.stat().st_size:
        return True, ""
    tail = stderr.splitlines()
    return False, tail[-1] if tail else f"no PDF after {timeout}s"


def html_to_pdf(
    html_path: Path,
    pdf_path: Path,
    *,
    browser: Optional[str] = None,
    timeout: int = 120,
) -> Path:
    """Renders `html_path` to `pdf_path`, returning the PDF path."""
    exe = browser or find_browser()
    if not exe:
        raise PdfError("no Chromium-family browser found")

    html_path, pdf_path = Path(html_path).resolve(), Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    # A throwaway profile keeps this from colliding with a running Chrome,
    # which would otherwise hand the job to the existing instance and exit.
    with tempfile.TemporaryDirectory(prefix="ytlesson-chrome-") as profile:
        base = [
            exe,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--disable-extensions",
            f"--user-data-dir={profile}",
        ]
        tail = [f"--print-to-pdf={pdf_path}", html_path.as_uri()]

        # --no-pdf-header-footer is current; older builds spell it differently.
        for flag in ("--no-pdf-header-footer", "--print-to-pdf-no-header"):
            ok, why = _attempt(base + [flag] + tail, pdf_path, timeout)
            if ok:
                return pdf_path

    raise PdfError(f"{Path(exe).name} failed to write a PDF: {why}")
