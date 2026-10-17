"""Open-Meteo API access: the keyless free hosts by default, customer hosts with a key (ADR 0056).

The key is a credential. These tests pin two promises: without a key the requests are exactly the
ones swelter always made, and with a key the key is sent to Open-Meteo and reaches nothing else —
no stderr/stdout line, no exception text, no store row, no published file, no `doctor` output.
No real network: the shared HTTPS boundary (or the adapter's ``_get_json``) is stubbed.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from swelter.cli import main
from swelter.sources import _http, openmeteo
from swelter.sources._http import REDACTED, SourceError, get_json, redact_url

from .conftest import ROOT

#: A fake key with characters that change under percent-encoding, so both spellings are checked.
SENTINEL = "om-SENTINEL+key/9f3&x=y"
SENTINEL_FORMS = (SENTINEL, quote(SENTINEL, safe=""), "om-SENTINEL")

PLACES = (
    openmeteo.Neighborhood("Oak Park", 38.547, -121.463),
    openmeteo.Neighborhood("Midtown", 38.572, -121.479),
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda *_: None)


def _assert_no_key(text: str) -> None:
    for form in SENTINEL_FORMS:
        assert form not in text


def _hour(reference: datetime) -> str:
    return (reference - timedelta(hours=2)).strftime("%Y-%m-%dT%H:00")


def _payload_for(url: str, hour: str) -> list[dict[str, Any]]:
    """An Open-Meteo-shaped answer with one location per requested latitude."""
    count = len(parse_qs(urlsplit(url).query)["latitude"][0].split(","))
    if "air-quality" in url:
        hourly: dict[str, Any] = {"time": [hour], "pm2_5": [8.0], "pm10": [12.0]}
    else:
        hourly = {"time": [hour], "temperature_2m": [31.0], "relative_humidity_2m": [40.0]}
    return [{"hourly": hourly} for _ in range(count)]


# --- default: the free hosts, byte for byte ------------------------------------------------------


def test_without_a_key_the_requests_are_exactly_the_free_host_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_get(url: str) -> Any:
        seen.append(url)
        return []

    monkeypatch.setattr(openmeteo, "_get_json", fake_get)
    openmeteo.fetch(PLACES, past_days=1, now=datetime(2026, 8, 15, 14, tzinfo=UTC))

    coords = "latitude=38.547,38.572&longitude=-121.463,-121.479"
    assert seen == [
        "https://air-quality-api.open-meteo.com/v1/air-quality?"
        f"{coords}&hourly=pm2_5,pm10&past_days=1&forecast_days=1",
        "https://api.open-meteo.com/v1/forecast?"
        f"{coords}&hourly=temperature_2m,relative_humidity_2m&past_days=1&forecast_days=1",
    ]


def test_a_blank_key_in_the_environment_is_no_key() -> None:
    assert openmeteo.api_key_from_env({}) == ""
    assert openmeteo.api_key_from_env({openmeteo.API_KEY_ENV: "   "}) == ""
    assert openmeteo.api_key_from_env({openmeteo.API_KEY_ENV: f" {SENTINEL}\n"}) == SENTINEL


# --- with a key: customer hosts, key sent ---------------------------------------------------------


def test_with_a_key_the_customer_hosts_receive_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_get(url: str) -> Any:
        seen.append(url)
        return []

    monkeypatch.setattr(openmeteo, "_get_json", fake_get)
    openmeteo.fetch(PLACES, now=datetime(2026, 8, 15, 14, tzinfo=UTC), api_key=SENTINEL)

    assert [urlsplit(u).hostname for u in seen] == [
        "customer-air-quality-api.open-meteo.com",
        "customer-api.open-meteo.com",
    ]
    for url in seen:
        assert urlsplit(url).path in {"/v1/air-quality", "/v1/forecast"}
        # Percent-encoded on the wire, and it round-trips to the exact key.
        assert parse_qs(urlsplit(url).query)["apikey"] == [SENTINEL]


# --- the key never leaves the request ------------------------------------------------------------


def test_redact_url_replaces_only_credential_values() -> None:
    url = f"https://customer-api.open-meteo.com/v1/forecast?latitude=1,2&apikey={quote(SENTINEL)}"
    redacted = redact_url(url)
    _assert_no_key(redacted)
    assert f"apikey={REDACTED}" in redacted
    assert "latitude=1,2" in redacted  # the rest of the request stays diagnosable
    plain = "https://api.open-meteo.com/v1/forecast?latitude=1,2&hourly=temperature_2m"
    assert redact_url(plain) == plain  # nothing to hide: unchanged, byte for byte


def test_shared_fetch_errors_never_quote_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"https://customer-api.open-meteo.com/v1/forecast?apikey={quote(SENTINEL, safe='')}"
    real_request = _http._request_json

    def refused(*_a: Any, **_k: Any) -> Any:
        raise _http._HTTPStatusError(401, {})

    monkeypatch.setattr(_http, "_request_json", refused)
    with pytest.raises(SourceError) as non_retryable:
        get_json(url)
    _assert_no_key(str(non_retryable.value))

    def flaky(*_a: Any, **_k: Any) -> Any:
        raise _http._HTTPStatusError(503, {})

    monkeypatch.setattr(_http, "_request_json", flaky)
    with pytest.raises(SourceError) as exhausted:
        get_json(url, retries=2)
    _assert_no_key(str(exhausted.value))

    with pytest.raises(ValueError) as bad_scheme:
        real_request(url.replace("https://", "http://"), {}, 1.0)
    _assert_no_key(str(bad_scheme.value))


def test_a_failed_chunk_with_a_key_prints_no_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reference = datetime(2026, 8, 15, 14, tzinfo=UTC)
    sent: list[str] = []

    def fake_request(url: str, _headers: Any, _timeout: float) -> Any:
        sent.append(url)
        if "38.547" in url:  # the first chunk is refused outright
            raise _http._HTTPStatusError(401, {})
        return _payload_for(url, _hour(reference))

    monkeypatch.setattr(_http, "_request_json", fake_request)
    obs = openmeteo.fetch(PLACES, chunk=1, now=reference, api_key=SENTINEL)

    assert obs  # the second place still came back
    assert any(quote(SENTINEL, safe="") in url for url in sent)  # the key was sent...
    captured = capsys.readouterr()
    assert "chunk 0 failed" in captured.err
    _assert_no_key(captured.out + captured.err)  # ...and appears nowhere else
    _assert_no_key(repr(obs))


def test_scrub_removes_both_spellings_and_is_a_no_op_without_a_key() -> None:
    text = f"raw {SENTINEL} encoded {quote(SENTINEL, safe='')}"
    _assert_no_key(openmeteo.scrub(text, SENTINEL))
    assert openmeteo.scrub(text, "") == text


def test_cli_fetch_with_a_key_writes_and_prints_no_trace_of_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end: every byte the fetch writes (store, sidecars, config, web artifacts) and every
    line it prints is searched for the key."""
    monkeypatch.setenv(openmeteo.API_KEY_ENV, SENTINEL)
    hour = _hour(datetime.now(UTC))
    sent: list[str] = []

    def fake_request(url: str, _headers: Any, _timeout: float) -> Any:
        sent.append(url)
        if len(sent) == 1:  # one refused chunk, so the error path is exercised too
            raise _http._HTTPStatusError(403, {})
        return _payload_for(url, hour)

    monkeypatch.setattr(_http, "_request_json", fake_request)
    rc = main(
        [
            "fetch",
            "--source",
            "openmeteo",
            "--store",
            str(tmp_path / "store"),
            "--config",
            str(tmp_path / "net.yaml"),
            "--web",
            str(tmp_path / "web"),
            "--cooling-centers",
            str(tmp_path / "absent.geojson"),
        ]
    )

    assert rc == 0
    hosts = [urlsplit(u).hostname or "" for u in sent]
    assert hosts and all(host.startswith("customer-") for host in hosts)
    captured = capsys.readouterr()
    assert f"{openmeteo.API_KEY_ENV} is set" in captured.err
    _assert_no_key(captured.out + captured.err)
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert written
    for path in written:
        data = path.read_bytes()
        for form in SENTINEL_FORMS:
            assert form.encode() not in data, path


def test_cli_fetch_failure_message_never_quotes_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(openmeteo.API_KEY_ENV, SENTINEL)

    def leaky(*_a: Any, **_k: Any) -> Any:
        raise SourceError(f"upstream echoed {SENTINEL}")

    monkeypatch.setattr(openmeteo, "fetch", leaky)
    rc = main(
        [
            "fetch",
            "--source",
            "openmeteo",
            "--store",
            str(tmp_path / "store"),
            "--config",
            str(tmp_path / "net.yaml"),
            "--web",
            str(tmp_path / "web"),
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "fetch failed" in err
    _assert_no_key(err)


def test_cli_fetch_without_a_key_does_not_mention_customer_endpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(openmeteo.API_KEY_ENV, raising=False)
    received: dict[str, Any] = {}

    def fake_fetch(*_a: Any, **kwargs: Any) -> list[Any]:
        received.update(kwargs)
        return []

    monkeypatch.setattr(openmeteo, "fetch", fake_fetch)
    main(
        [
            "fetch",
            "--source",
            "openmeteo",
            "--store",
            str(tmp_path / "store"),
            "--config",
            str(tmp_path / "net.yaml"),
            "--web",
            str(tmp_path / "web"),
        ]
    )
    assert received["api_key"] == ""
    assert "customer" not in capsys.readouterr().err


# --- `swelter doctor` reports presence, never the value ------------------------------------------


def test_doctor_reports_a_set_key_without_its_value(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(openmeteo.API_KEY_ENV, SENTINEL)
    assert main(["doctor", "--config", str(ROOT / "network.yaml")]) == 0
    captured = capsys.readouterr()
    assert f"{openmeteo.API_KEY_ENV} is set" in captured.err
    _assert_no_key(captured.out + captured.err)


def test_doctor_reports_an_absent_key_and_the_free_tier_terms(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(openmeteo.API_KEY_ENV, raising=False)
    assert main(["doctor", "--config", str(ROOT / "network.yaml")]) == 0
    err = capsys.readouterr().err
    assert f"{openmeteo.API_KEY_ENV} is not set" in err
    assert "non-commercial" in err
