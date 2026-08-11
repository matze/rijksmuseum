# /// script
# requires-python = ">=3.11"
# dependencies = ["websocket-client>=1.7", "requests>=2.31"]
# ///
"""Screenshot the guide at a phone-sized viewport, or at a desktop one.

Headless Chrome clamps its window to a few hundred pixels wide, so the viewport
is set over the DevTools protocol instead — the same emulation the device
toolbar uses. Also reports page errors and any horizontal overflow, which is the
failure a mobile-first layout is most likely to have.

    uv run tools/screenshot.py /            --out setup.png
    uv run tools/screenshot.py / --click '.btn-primary' --scroll 900
    uv run tools/screenshot.py / --width 1440 --height 900 --click '.card'
    uv run tools/screenshot.py / --click '.tile' --hover '.look li:nth-child(1)'
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from enum import StrEnum
from pathlib import Path

import requests
import websocket

#: Any Chromium speaking the DevTools protocol will do — a checkout without one
#: on the path can point $CHROME at the browser it already has.
CHROME = os.environ.get("CHROME", "google-chrome-stable")
DEBUG_PORT = 9222
DEFAULT_VIEWPORT = (390, 844)  # a common phone in CSS pixels
PHONE_LIMIT = 700  # widths under this are captured as a phone, wider ones as a desktop


class Pointer(StrEnum):
    """What the captured window is driven with.

    Headless has no pointing device at all, so `hover` and `pointer` both read
    as none and anything gated on them is invisible to a capture — including,
    on a desktop window, everything that only happens under the cursor. Blink is
    told which it is rather than left to guess: the numbers are its own, hover
    none/hover and pointer none/coarse/fine.
    """

    mouse = "primaryHoverType=2,availableHoverTypes=2,primaryPointerType=4," \
            "availablePointerTypes=4"
    touch = "primaryHoverType=1,availableHoverTypes=1,primaryPointerType=2," \
            "availablePointerTypes=2"


class Chrome:
    def __init__(self, pointer: Pointer, port: int = DEBUG_PORT):
        self.port = port
        # A throwaway profile per run, so a visit started by one screenshot does
        # not resume in the next one and quietly change what is being captured.
        self.profile = tempfile.TemporaryDirectory(prefix="rijks-shot-")
        self.process = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={port}",
             "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
             "--remote-allow-origins=*", f"--blink-settings={pointer.value}",
             # The dev server is on this machine; a system proxy would refuse it.
             "--no-proxy-server",
             "--no-first-run", f"--user-data-dir={self.profile.name}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.socket = websocket.create_connection(self._target(), timeout=30)
        self.next_id = 0

    def _target(self) -> str:
        for _ in range(60):
            try:
                targets = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=2).json()
                pages = [t for t in targets if t["type"] == "page"]

                if pages:
                    return pages[0]["webSocketDebuggerUrl"]
            except requests.RequestException:
                pass

            time.sleep(0.25)

        raise RuntimeError("Chrome did not expose a debugging target")

    def send(self, method: str, **params):
        self.next_id += 1
        self.socket.send(json.dumps({"id": self.next_id, "method": method, "params": params}))

        while True:
            message = json.loads(self.socket.recv())

            if message.get("id") == self.next_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")

                return message.get("result", {})

    def evaluate(self, expression: str):
        result = self.send("Runtime.evaluate", expression=expression,
                           returnByValue=True, awaitPromise=True)

        return result.get("result", {}).get("value")

    def close(self):
        self.socket.close()
        self.process.terminate()
        self.process.wait(timeout=10)
        self.profile.cleanup()


DIAGNOSTICS = """
(() => ({
  innerWidth: window.innerWidth,
  scrollWidth: document.documentElement.scrollWidth,
  overflowing: [...document.querySelectorAll('*')]
    .filter((n) => n.getBoundingClientRect().right > window.innerWidth + 1)
    .slice(0, 8)
    .map((n) => n.tagName.toLowerCase() + (n.className ? '.' + String(n.className).split(' ').join('.') : '')),
}))()
"""


def hover(chrome: Chrome, selector: str, height: int) -> None:
    """Put the pointer over an element, as a pointer rather than as a script.

    A dispatched event would reach a listener but leave `:hover` unset, and half
    of what a hover state looks like is CSS. This moves the mouse itself.
    """
    centre = chrome.evaluate(
        f"(() => {{ const node = document.querySelector({selector!r});"
        f" if (!node) return null;"
        f" const box = node.getBoundingClientRect();"
        f" return {{ x: box.left + box.width / 2, y: box.top + box.height / 2 }}; }})()")

    if not centre:
        print(f"warning: nothing matched {selector}", file=sys.stderr)
        return

    # A rect off the top or bottom of the window still has coordinates, and the
    # pointer would land on whatever is drawn there instead.
    if not 0 <= centre["y"] <= height:
        print(f"warning: {selector} is off the screen at y={centre['y']:.0f}", file=sys.stderr)

    chrome.send("Input.dispatchMouseEvent", type="mouseMoved",
                x=centre["x"], y=centre["y"], buttons=0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", default="/", help="path on the dev server")
    parser.add_argument("--base", default="http://localhost:8137")
    parser.add_argument("--out", default="shot.png")
    parser.add_argument("--width", type=int, default=DEFAULT_VIEWPORT[0])
    parser.add_argument("--height", type=int, default=DEFAULT_VIEWPORT[1])
    parser.add_argument("--full", action="store_true", help="capture the whole page")
    parser.add_argument("--dark", action="store_true", help="emulate a dark colour scheme")
    parser.add_argument("--click", action="append", default=[], help="CSS selector to click")
    parser.add_argument("--hover", help="CSS selector to leave the pointer over")
    parser.add_argument("--scroll", type=int, default=0, help="pixels to scroll before capture")
    parser.add_argument("--revisit", action="store_true",
                        help="reload after the clicks, to check the visit resumes")
    parser.add_argument("--eval", dest="script", help="expression to run and print")
    args = parser.parse_args()

    # A window this wide is a desktop, and emulating one as a phone would both
    # scale the capture past reading size and hand the page a mobile device pixel
    # ratio, which is what picks the file out of a srcset. It also decides what
    # the page is told it is being pointed at with.
    phone = args.width < PHONE_LIMIT
    chrome = Chrome(Pointer.touch if phone else Pointer.mouse)

    try:
        chrome.send("Page.enable")
        chrome.send("Runtime.enable")
        chrome.send("Log.enable")
        chrome.send("Emulation.setDeviceMetricsOverride", width=args.width, height=args.height,
                    deviceScaleFactor=2 if phone else 1, mobile=phone)

        if args.dark:
            chrome.send("Emulation.setEmulatedMedia",
                        features=[{"name": "prefers-color-scheme", "value": "dark"}])

        chrome.send("Page.navigate", url=args.base + args.path)
        time.sleep(2.5)

        for selector in args.click:
            clicked = chrome.evaluate(
                f"(() => {{ const n = document.querySelector({selector!r});"
                f" if (!n) return false; n.click(); return true; }})()")

            if not clicked:
                print(f"warning: nothing matched {selector}", file=sys.stderr)

            time.sleep(1.2)

        if args.revisit:
            chrome.send("Page.navigate", url=args.base + args.path)
            time.sleep(2.5)

        if args.scroll:
            chrome.evaluate(f"window.scrollTo(0, {args.scroll})")
            time.sleep(0.8)

        # After the scrolling, so the element is where it will be in the capture.
        if args.hover:
            hover(chrome, args.hover, args.height)
            time.sleep(0.6)

        # Lazily loaded plates decode after they scroll into view; without this a
        # capture can catch an empty frame and look like a broken image.
        chrome.evaluate(
            "Promise.race(["
            "  Promise.all([...document.images].map((i) => i.decode().catch(() => {}))),"
            "  new Promise((done) => setTimeout(done, 4000)),"
            "]).then(() => true)")
        time.sleep(0.5)

        errors = chrome.evaluate(
            "JSON.stringify(window.__errors || [])")

        diagnostics = chrome.evaluate(DIAGNOSTICS)
        print(f"viewport {diagnostics['innerWidth']}px, "
              f"document {diagnostics['scrollWidth']}px", file=sys.stderr)

        if diagnostics["overflowing"]:
            print(f"overflowing: {', '.join(diagnostics['overflowing'])}", file=sys.stderr)

        if errors and errors != "[]":
            print(f"page errors: {errors}", file=sys.stderr)

        if args.script:
            print(chrome.evaluate(args.script))

        shot = chrome.send("Page.captureScreenshot", format="png",
                           captureBeyondViewport=args.full)
        Path(args.out).write_bytes(base64.b64decode(shot["data"]))
        print(f"wrote {args.out}", file=sys.stderr)
    finally:
        chrome.close()


if __name__ == "__main__":
    main()
