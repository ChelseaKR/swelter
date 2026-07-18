"""Bilingual-by-gate: the en/es message catalogs must stay at parity.

A resident-facing string that exists in ``en`` but not ``es`` (or vice versa) is an equity defect,
not a cosmetic one — a Spanish-first reader silently falls back to English for exactly the guidance,
alert, and trust copy this project exists to deliver in their language. The org-wide
``INTERNATIONALIZATION-STANDARD`` makes this merge-blocking (G6 key-parity ``keys(en) == keys(es)``
and G5 placeholder parity); swelter previously had no such check. These tests are it.

Pure stdlib, no browser: the catalogs are flat JSON, so key and MF2 variable parity are set
comparisons. Canonical syntax validation remains the pinned MessageFormat runtime's job.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT / "web" / "i18n"
INDEX = ROOT / "web" / "index.html"
APP_JS = ROOT / "web" / "app.js"

REFERENCE_LANG = "en"
#: Every locale the dashboard ships must reach parity with the reference catalog.
SHIPPED_LANGS = ("en", "es")

_PLACEHOLDER = re.compile(r"\{\$([A-Za-z][A-Za-z0-9_-]*)\b")
# A static t("key") / t('key') lookup in the dashboard logic (templated t(`...`) calls are skipped).
_T_LITERAL = re.compile(r"""\bt\(\s*["']([a-zA-Z0-9_-]+)["']\s*\)""")
_DATA_I18N = re.compile(r'data-i18n="([^"]+)"')
_DATA_I18N_ATTR = re.compile(r'data-i18n-attr="([^"]+)"')


def _load(lang: str) -> dict[str, str]:
    catalog: dict[str, str] = json.loads((I18N_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    return catalog


def _placeholders(value: str) -> set[str]:
    return set(_PLACEHOLDER.findall(value))


def test_every_shipped_locale_catalog_exists() -> None:
    for lang in SHIPPED_LANGS:
        assert (I18N_DIR / f"{lang}.json").is_file(), f"missing catalog: {lang}.json"


def test_en_es_key_parity_is_exact() -> None:
    """G6: ``keys(en) == keys(es)`` exactly — the symmetric difference must be empty."""
    en = set(_load("en"))
    es = set(_load("es"))
    only_en = sorted(en - es)
    only_es = sorted(es - en)
    assert not only_en, f"keys in en missing from es: {only_en}"
    assert not only_es, f"keys in es missing from en: {only_es}"


def test_placeholder_parity_per_key() -> None:
    """G5: each translated string carries the same MF2 ``{$variable}`` set as the reference.

    A dropped or renamed ``{$n}`` / ``{$place}`` would lose a runtime value
    to a reader in the other language; catch it deterministically rather than in production.
    """
    ref = _load(REFERENCE_LANG)
    for lang in SHIPPED_LANGS:
        if lang == REFERENCE_LANG:
            continue
        other = _load(lang)
        mismatched = {
            key: (sorted(_placeholders(ref[key])), sorted(_placeholders(other[key])))
            for key in ref
            if key in other and _placeholders(ref[key]) != _placeholders(other[key])
        }
        assert not mismatched, f"placeholder mismatch ({REFERENCE_LANG} vs {lang}): {mismatched}"


def test_no_empty_translations() -> None:
    """A present-but-empty string is a silent gap; it must not pass for a real translation."""
    for lang in SHIPPED_LANGS:
        blank = sorted(k for k, v in _load(lang).items() if not str(v).strip())
        assert not blank, f"empty strings in {lang}.json: {blank}"


def test_map_reset_label_is_route_neutral() -> None:
    """The shared shell serves California and Stuttgart, so its map copy cannot name one route."""
    assert _load("en")["map-reset-label"] == "Reset map pan and zoom"
    assert _load("es")["map-reset-label"] == "Restablecer la posición y el zoom del mapa"
    assert 'aria-label="Reset map pan and zoom"' in INDEX.read_text(encoding="utf-8")


def test_referenced_keys_resolve_in_every_locale() -> None:
    """Every i18n key the dashboard references must exist in every shipped locale.

    Sources: ``data-i18n`` / ``data-i18n-attr`` in the HTML, and static ``t("key")`` calls in the
    app logic. A key referenced but absent from a catalog would fall back to English (or the raw
    key) for that locale — exactly the guidance/alert/trust copy that owes both languages.
    """
    html = INDEX.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    referenced = set(_DATA_I18N.findall(html))
    referenced |= {pair.split(":")[1] for pair in _DATA_I18N_ATTR.findall(html)}
    referenced |= set(_T_LITERAL.findall(js))
    for lang in SHIPPED_LANGS:
        catalog = _load(lang)
        missing = sorted(key for key in referenced if key not in catalog)
        assert not missing, (
            f"keys referenced by the dashboard but absent from {lang}.json: {missing}"
        )
