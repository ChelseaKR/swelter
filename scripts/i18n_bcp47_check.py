#!/usr/bin/env python3
"""G3 BCP 47 tag-validity gate — merge-blocking (INTERNATIONALIZATION-STANDARD §4).

Every authored locale tag the dashboard ships must be a well-formed, registered BCP 47 (RFC 5646)
tag. A typo like ``es_ES`` (underscore), ``spanish``, or ``en-USA`` (bad region) silently breaks
``Intl``/content-negotiation and the language switch — the reader gets the wrong or no language.
The standard names ``babel.Locale.parse`` / ``Intl.Locale``; swelter keeps a stdlib-only gate
(one runtime dependency, by design), so this validates the RFC 5646 grammar directly and
registry-checks the primary language subtag against the ISO 639-1 set.

Authored tags are discovered, not hand-listed, from the surfaces that carry them:
  * the ``web/i18n/<tag>.json`` catalog filenames (the shipped locales),
  * the ``<html lang>`` root attribute in ``web/index.html`` (this is also **G4 html-lang-valid**,
    the merge-blocking complement to the structural a11y gate's ``html-has-lang``), and
  * the ``"lang"`` field in ``web/manifest.webmanifest``.

Pure standard library, offline, deterministic. Exit status is 0 when every tag is valid and 1
otherwise, listing each offender with the reason it failed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
I18N_DIR = ROOT / "web" / "i18n"
INDEX = ROOT / "web" / "index.html"
MANIFEST = ROOT / "web" / "manifest.webmanifest"

# The ISO 639-1 two-letter language set (static registry). A 2-letter primary subtag MUST be one
# of these; longer subtags are checked structurally (see _validate). This catches "spanish"/"engish"
# while a full ISO 639-2/3 table would only add rarely-authored 3-letter codes.
_ISO_639_1_CODES = (
    "aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy "
    "da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu "
    "hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb "
    "lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om "
    "or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw "
    "ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu"
)
ISO_639_1 = frozenset(_ISO_639_1_CODES.split())

_HTML_LANG = re.compile(r"<html[^>]*\blang\s*=\s*\"([^\"]*)\"", re.IGNORECASE)

# RFC 5646 subtag shapes (case-insensitive; BCP 47 canonical case is normalized by consumers).
_LANGUAGE = re.compile(r"^[A-Za-z]{2,3}$")  # primary language (2-3 alpha); registry-checked below
_SCRIPT = re.compile(r"^[A-Za-z]{4}$")  # e.g. Latn, Cyrl
_REGION = re.compile(r"^([A-Za-z]{2}|[0-9]{3})$")  # ISO 3166-1 alpha-2 or UN M.49
_VARIANT = re.compile(r"^([A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3})$")  # e.g. 1996, valencia
_SINGLETON = re.compile(r"^[A-WY-Za-wy-z0-9]$")  # extension/private-use singleton (not 'x' start)


def _validate(tag: str) -> str | None:
    """Return None if ``tag`` is a well-formed, registered BCP 47 tag, else a failure reason."""
    if not tag or not tag.strip():
        return "empty tag"
    if tag != tag.strip():
        return "leading/trailing whitespace"
    if "_" in tag:
        return "uses '_' (BCP 47 subtags are '-'-separated)"

    subtags = tag.split("-")
    primary = subtags[0]
    if not _LANGUAGE.match(primary):
        return f"primary language subtag {primary!r} is not 2-3 letters"
    if len(primary) == 2 and primary.lower() not in ISO_639_1:
        return f"primary language subtag {primary!r} is not a registered ISO 639-1 code"

    # Walk the remaining subtags in the RFC 5646 order (script? region? variant* / singleton...).
    i = 1
    if i < len(subtags) and _SCRIPT.match(subtags[i]):
        i += 1
    if i < len(subtags) and _REGION.match(subtags[i]):
        i += 1
    while i < len(subtags):
        sub = subtags[i]
        if _VARIANT.match(sub):
            i += 1
            continue
        if len(sub) == 1 and _SINGLETON.match(sub) or sub.lower() == "x":
            return None  # extension / private-use block — accept the tag as well-formed
        return f"subtag {sub!r} is not a valid script/region/variant"
    return None


def _authored_tags() -> list[tuple[str, str]]:
    """Return ``(source, tag)`` pairs for every authored locale tag, in a stable order."""
    tags: list[tuple[str, str]] = []
    for path in sorted(I18N_DIR.glob("*.json")):
        tags.append((f"catalog {path.name}", path.stem))
    if INDEX.is_file():
        m = _HTML_LANG.search(INDEX.read_text(encoding="utf-8"))
        if m:
            tags.append(("web/index.html <html lang> (G4)", m.group(1)))
    if MANIFEST.is_file():
        lang = json.loads(MANIFEST.read_text(encoding="utf-8")).get("lang")
        if isinstance(lang, str):
            tags.append(("web/manifest.webmanifest lang", lang))
    return tags


def main() -> int:
    tags = _authored_tags()
    if not tags:
        print("i18n-bcp47: no authored locale tags found", file=sys.stderr)
        return 1

    failed = 0
    for source, tag in tags:
        reason = _validate(tag)
        ok = reason is None
        if not ok:
            failed += 1
        marker = "PASS" if ok else "FAIL"
        detail = f"({reason})" if reason else "valid"
        print(f"  [{marker}] {source}: {tag!r} {detail}")

    if failed:
        print(f"i18n-bcp47: {len(tags) - failed}/{len(tags)} tags valid", file=sys.stderr)
        return 1
    print(f"i18n-bcp47: all {len(tags)} authored locale tags are valid BCP 47")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
