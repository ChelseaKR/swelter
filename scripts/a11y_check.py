#!/usr/bin/env python3
"""Structural accessibility gate for the dashboard — a merge-blocking WCAG 2.2 AA subset.

This is the pure-Python check that runs in CI on every PR (``make a11y``). It cannot judge
computed colour contrast or live ARIA semantics — that is the job of the advisory axe/pa11y
pass and the manual NVDA/VoiceOver review documented in docs/accessibility/ACR.md. What it
*can* do, deterministically and with no browser, is hold the structural floor the README
promises: a language, a single heading, a skip link, labelled controls, landmarks, no
keyboard traps from positive tabindex, image text alternatives, and — the load-bearing one —
a real data-table equivalent so the map is never the only way in.

Exit status is 0 when every check passes and 1 otherwise, with a per-check report.
"""

from __future__ import annotations

import contextlib
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "web" / "index.html"
STYLES = ROOT / "web" / "styles.css"


@dataclass
class Page:
    html_lang: str | None = None
    title_text: str = ""
    h1_count: int = 0
    landmarks: set[str] = field(default_factory=set)
    label_for: set[str] = field(default_factory=set)
    controls: list[tuple[str | None, bool]] = field(default_factory=list)  # (id, has_aria_label)
    has_table: bool = False
    skip_link_targets: set[str] = field(default_factory=set)
    ids: set[str] = field(default_factory=set)
    imgs_total: int = 0
    imgs_with_alt: int = 0
    max_tabindex: int = 0
    lang_switch: bool = False


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.page = Page()
        self._in_title = False

    def _handle_control_or_media_tag(self, tag: str, a: dict[str, str]) -> bool:
        """Handle the form-control / image / skip-link tags. Returns True if ``tag`` matched."""
        page = self.page
        if tag in {"input", "select", "textarea"}:
            page.controls.append(
                (a.get("id") or None, bool(a.get("aria-label") or a.get("aria-labelledby")))
            )
        elif tag == "img":
            page.imgs_total += 1
            if "alt" in a:
                page.imgs_with_alt += 1
        elif tag == "a" and a.get("href", "").startswith("#"):
            page.skip_link_targets.add(a["href"][1:])
        else:
            return False
        return True

    def _handle_tag_specific(self, tag: str, a: dict[str, str]) -> None:
        page = self.page
        if tag == "html":
            page.html_lang = a.get("lang")
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            page.h1_count += 1
        elif tag in {"main", "nav", "header", "footer"}:
            page.landmarks.add(tag)
        elif tag == "table":
            page.has_table = True
        elif tag == "label" and a.get("for"):
            page.label_for.add(a["for"])
        else:
            self._handle_control_or_media_tag(tag, a)

    def _handle_common_attrs(self, a: dict[str, str]) -> None:
        page = self.page
        if a.get("id"):
            page.ids.add(a["id"])
        if a.get("role") == "main":
            page.landmarks.add("main")
        if "data-lang-switch" in a:
            page.lang_switch = True
        if a.get("tabindex"):
            with contextlib.suppress(ValueError):
                page.max_tabindex = max(page.max_tabindex, int(a["tabindex"]))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        self._handle_tag_specific(tag, a)
        self._handle_common_attrs(a)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.page.title_text += data.strip()


def _checks(page: Page, css: str) -> list[tuple[bool, str]]:
    # Evaluate labelling per control, so a control that is both <label for>'d and aria-labelled
    # cannot over-count and mask a different, genuinely unlabelled control.
    unlabelled = sum(
        1
        for control_id, has_aria in page.controls
        if not ((control_id is not None and control_id in page.label_for) or has_aria)
    )
    return [
        (bool(page.html_lang), f"<html lang> is set (lang={page.html_lang!r})"),
        (bool(page.title_text), f"document has a <title> ({page.title_text!r})"),
        (page.h1_count == 1, f"exactly one <h1> (found {page.h1_count})"),
        ({"main", "header"} <= page.landmarks, f"landmarks present ({sorted(page.landmarks)})"),
        (
            bool(page.skip_link_targets & page.ids),
            f"a skip link targets an in-page id ({sorted(page.skip_link_targets)})",
        ),
        (unlabelled <= 0, f"every form control is labelled ({unlabelled} unlabelled)"),
        (page.has_table, "a data-table equivalent to the map exists"),
        (
            page.imgs_with_alt == page.imgs_total,
            f"every <img> has alt ({page.imgs_with_alt}/{page.imgs_total})",
        ),
        (page.max_tabindex <= 0, f"no positive tabindex (max={page.max_tabindex})"),
        (page.lang_switch, "a language switch is present (data-lang-switch)"),
        (
            "prefers-reduced-motion" in css,
            "CSS honours prefers-reduced-motion",
        ),
        (
            "focus-visible" in css or ":focus" in css,
            "CSS provides a visible focus indicator",
        ),
    ]


def main() -> int:
    if not INDEX.is_file():
        print(f"a11y: {INDEX} not found", file=sys.stderr)
        return 1
    collector = _Collector()
    collector.feed(INDEX.read_text(encoding="utf-8"))
    css = STYLES.read_text(encoding="utf-8") if STYLES.is_file() else ""

    results = _checks(collector.page, css)
    failed = 0
    for ok, message in results:
        marker = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{marker}] {message}")
    total = len(results)
    print(f"a11y: {total - failed}/{total} structural checks passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
