"""
Deterministic tests for DelistWatch using genlayer-test's Direct Mode.

Inputs are real responses from Binance, OKX and KuCoin captured on
2026-10-04 - market-status APIs, each exchange's delisting-announcement
list, and the announcements themselves - reduced to the fields the
contract reads by scripts/build_fixtures.py, which checks that every
reduced fixture parses exactly like the raw capture (sources and SHA-256s
in tests/fixtures/manifest.json).

Real cases are the test cases:
- KuCoin STORJ/USDT, today: trading, and the one announcement whose title
  names STORJ is "KuCoin Futures Will Delist the ICXUSDT and STORJUSDT
  Perpetual Contracts" - a futures delisting (TRADING).
- Binance BTC/USDT, today: four generic spot-pair notices scanned, none
  names BTC (TRADING, decided without the LLM).
- Binance STORJ/USDT ("BREAK"), OKX STORJ/USDT (gone), KuCoin NOPEX/USDT
  (never existed), today: NOT_TRADING from market data alone.
- Before the delistings took effect: OKX's STORJ/USDT schedule, Binance's
  STORJ token delisting, Binance removing QNT/USDC (DELISTING_ANNOUNCED for
  QNT/USDC, TRADING for QNT/USDT), KuCoin's "ST" delisting of WAXP read
  together with an Earn-only WAXP notice.

The one thing that can't be captured today is a market API as it stood
before a delisting. For those cases the market response is the real
response of a trading pair with only the tickers changed (_trading_market)
- marked SYNTHETIC wherever it is used. Every announcement is real.

Five layers: market status, announcements and verdicts, the reader's
limits, fail-closed scanning, and the consensus boundary.
"""

import json
import pathlib
import re
import sys

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())["fixtures"]
TODAY = "2026-10-04T12:00:00Z"

KUCOIN_FUTURES = "/en-kucoin-futures-will-delist-the-icxusdt-and-storjusdt-perpetual-contracts-and-related-services-2026-08-26"
KUCOIN_ST = "/en-st-kucoin-will-delist-multiple-tokens-on-2026-09-07-1"
KUCOIN_EARN_WAXP = "/en-kucoin-earn-will-delist-the-waxp-products"
# OKX localises its help centre by region; Studio Next's validators get the
# en-us one (research/README.md), so the OKX scenarios use what they get.
# The global help centre's format is covered too (GLOBAL_* refs).
OKX_STORJ = "en-us/help/okx-to-delist-dora-icx-storj-zeus-and-elf-spot-trading-pairs"
OKX_AEON = "en-us/help/okx-to-delist-aeon-usd-spot-trading-pair"
OKX_USD = "en-us/help/okx-to-delist-selected-usd-spot-trading-pairs"
GLOBAL_OKX_STORJ = "help/okx-to-delist-dora-icx-storj-zeus-and-elf-spot-trading-pairs"
GLOBAL_OKX_AEON = "help/okx-to-delist-aeon-usd-spot-trading-pair"
GLOBAL_OKX_USDS = "help/okx-to-delist-selected-usds-spot-trading-pairs"
BINANCE_STORJ = "d72915ed7a60473b92f0818d959a227a"
BINANCE_TODAY_NOTICES = ["63415de54a164619aaaf245850349654", "7d17add1ffe6416391f65a001734e1c7",
                         "545ca5ad28254999b793bcf1ddd51f93", "30b1347d97324180bb469c761e4eed5a"]
BINANCE_AUGUST_NOTICES = ["fab1676df7fb464a9e4634c6f777659e", "b2d783892ef54b4daddecf142076a8cf",
                          "23504a5454d545998414c9ad3e8832f3"]
BINANCE_QNT_NOTICES = ["30b1347d97324180bb469c761e4eed5a", "b9198262dd5f4071a1119b9f52cbe00c"]

OKX_STORJ_QUOTE = "STORJ/USDT October 3, 2026, 08:00 - 10:00 UTC"
BINANCE_STORJ_QUOTE = ("we have decided to delist and cease trading on all spot trading pairs for the following "
                       "token(s) at 2026-09-03 03:00 (UTC)")
BINANCE_QNT_QUOTE = "At 2026-09-18 03:00 (UTC): BREV/USDC, COOKIE/USDC, LA/USDC and QNT/USDC"
KUCOIN_ST_QUOTE = ("the following projects will be delisted, and its associated token will be removed from the "
                   "platform at 8:00 on September 7, 2026 (UTC)")


# --- Helpers ------------------------------------------------------------------


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _mock(direct_vm, url: str, body: str, status: int = 200) -> None:
    # Anchored at both ends, so one URL can never be served another's body.
    direct_vm.mock_web("^" + re.escape(url) + "$", {"method": "GET", "response": {
        "status": status, "headers": {}, "body": body.encode("utf-8")}})


def _serve(direct_vm, name: str, body=None, status=None) -> None:
    meta = MANIFEST[name]
    _mock(direct_vm, meta["url"], _fixture(name) if body is None else body,
          meta["status"] if status is None else status)


def _detail_name(exchange: str, ref: str) -> str:
    ext = "html" if exchange == "okx" else "json"
    return f"{exchange}_d_{ref.lstrip('/').replace('/', '_')}.{ext}"


def _serve_details(direct_vm, exchange: str, refs) -> None:
    for ref in refs:
        _serve(direct_vm, _detail_name(exchange, ref))


def _market_url(exchange: str, base: str, quote: str) -> str:
    return {"binance": f"https://data-api.binance.vision/api/v3/exchangeInfo?symbol={base}{quote}",
            "okx": f"https://www.okx.com/api/v5/public/instruments?instType=SPOT&instId={base}-{quote}",
            "kucoin": f"https://api.kucoin.com/api/v2/symbols/{base}-{quote}"}[exchange]


def _trading_market(direct_vm, exchange: str, base: str, quote: str) -> None:
    """SYNTHETIC: the market response of a pair before its delisting - the
    real response of a trading pair today, with only the tickers changed."""
    if exchange == "binance":
        doc = json.loads(_fixture("binance_market_BTCUSDT.json"))
        doc["symbols"][0].update(symbol=base + quote, baseAsset=base, quoteAsset=quote)
    elif exchange == "okx":
        doc = json.loads(_fixture("okx_market_BTC-USDT.json"))
        doc["data"][0].update(instId=f"{base}-{quote}", baseCcy=base, quoteCcy=quote)
    else:
        doc = json.loads(_fixture("kucoin_market_STORJ-USDT.json"))
        doc["data"].update(symbol=f"{base}-{quote}", baseCurrency=base, quoteCurrency=quote)
    assert doc_status(doc, exchange) == "trading"
    _mock(direct_vm, _market_url(exchange, base, quote), json.dumps(doc))


def doc_status(doc: dict, exchange: str) -> str:
    if exchange == "binance":
        return "trading" if doc["symbols"][0]["status"] == "TRADING" else "other"
    if exchange == "okx":
        return "trading" if doc["data"][0]["state"] == "live" else "other"
    return "trading" if doc["data"]["enableTrading"] else "other"


def _reader(direct_vm, exchange: str, base: str, quote: str, ends_spot, date=None, evidence=None) -> None:
    direct_vm.mock_llm(f"END SPOT trading of the {base}/{quote} pair on {exchange}",
                       json.dumps({"ends_spot": ends_spot, "effective_date": date, "evidence": evidence}))


def _warp(direct_vm, timestamp: str) -> None:
    # genlayer-test 0.29.2's warp() never refreshes the datetime in the SDK's
    # already-imported gl.message_raw after deploy; set it too. Live GenVM
    # gives every call a fresh timestamp (confirmed on Studio Next).
    direct_vm.warp(timestamp)
    gl = sys.modules.get("genlayer.gl")
    if gl is not None and getattr(gl, "message_raw", None) is not None:
        gl.message_raw["datetime"] = timestamp


def _deploy(direct_vm, direct_deploy, direct_owner, now=TODAY):
    direct_vm.warp(now)
    direct_vm.sender = direct_owner
    contract = direct_deploy("contracts/delist_watch.py")
    _warp(direct_vm, now)
    return contract


def _watch(dw, watch_id, exchange, base, quote):
    dw.register_watch(watch_id, exchange, base, quote, f"{base}/{quote} on {exchange}")


def _leader(direct_vm):
    """The leader result the last check() actually produced."""
    stored, _leader_fn, _validator_fn = direct_vm._captured_validators[-1]
    return json.loads(stored)


# Scenario setups: each serves exactly what the contract should fetch - a
# fetch outside the scenario hits no mock and fails the test.


def kucoin_storj_today(direct_vm, ends_spot=False, **reading):
    direct_vm.clear_mocks()
    _serve(direct_vm, "kucoin_market_STORJ-USDT.json")
    _serve(direct_vm, "kucoin_list.json")
    _serve_details(direct_vm, "kucoin", [KUCOIN_FUTURES])
    _reader(direct_vm, "kucoin", "STORJ", "USDT", ends_spot, **reading)


def binance_btc_today(direct_vm):
    direct_vm.clear_mocks()
    _serve(direct_vm, "binance_market_BTCUSDT.json")
    _serve(direct_vm, "binance_list.json")
    _serve_details(direct_vm, "binance", BINANCE_TODAY_NOTICES)


def okx_btc_today(direct_vm):
    direct_vm.clear_mocks()
    _serve(direct_vm, "okx_market_BTC-USDT.json")
    _serve(direct_vm, "okx_list_us.json")
    _serve_details(direct_vm, "okx", [OKX_STORJ, OKX_AEON])


def okx_storj_before(direct_vm, ends_spot=True, date="2026-10-03", evidence=OKX_STORJ_QUOTE):
    direct_vm.clear_mocks()
    _trading_market(direct_vm, "okx", "STORJ", "USDT")  # SYNTHETIC (see module docstring)
    _serve(direct_vm, "okx_list_us.json")
    _serve_details(direct_vm, "okx", [OKX_STORJ, OKX_AEON, OKX_USD])
    _reader(direct_vm, "okx", "STORJ", "USDT", ends_spot, date, evidence)


# --- 1. Market status: plain code, the exchange's own data --------------------


def test_futures_delisting_named_in_the_title_does_not_stop_spot_trading(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "kucoin-storj", "kucoin", "STORJ", "USDT")
    kucoin_storj_today(direct_vm)
    dw.check("kucoin-storj")
    c = dw.latest_check("kucoin-storj")
    assert c["verdict"] == "TRADING" and c["reasons"] == [] and c["effective_date"] == ""
    f = c["facts"]
    assert f["market_state"] == "TRADING" and f["market_detail"] == "enableTrading=true"
    assert f["list_ok"] is True and f["list_covers_lookback"] is True and f["list_reaches"] == "2026-04-15"
    assert f["matching_announcements"] == 1 and f["scan_truncated"] is False
    [a] = f["announcements"]
    assert a["ref"] == KUCOIN_FUTURES and a["date"] == "2026-08-23"
    assert a["readable"] and a["delisting_category"] and a["names_token"] and a["complete"]
    assert a["url"] == f"https://www.kucoin.com/_api/cms/articles{KUCOIN_FUTURES}?lang=en_US"
    assert a["excerpt_preview"].startswith("KuCoin Futures Will Delist the ICXUSDT and STORJUSDT")
    assert len(a["excerpt_digest"]) == 64
    assert c["reading"] == {"ends_spot": False, "effective_date": None, "evidence": None, "grounded": False}
    assert dw.is_tradeable("kucoin-storj", 3600) is True


def test_generic_notices_that_never_name_the_token_are_decided_without_the_llm(direct_vm, direct_deploy, direct_owner):
    # No LLM mock is registered: a reader call would fail the check.
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "binance-btc", "binance", "BTC", "USDT")
    binance_btc_today(direct_vm)
    dw.check("binance-btc")
    c = dw.latest_check("binance-btc")
    assert c["verdict"] == "TRADING" and c["reading"] is None
    assert [a["ref"] for a in c["facts"]["announcements"]] == BINANCE_TODAY_NOTICES
    assert all(a["readable"] and a["delisting_category"] and not a["names_token"]
               for a in c["facts"]["announcements"])


@pytest.mark.parametrize("watch, fixture, detail", [
    (("binance", "STORJ", "USDT"), "binance_market_STORJUSDT.json", "market_not_trading:status=BREAK"),
    (("okx", "STORJ", "USDT"), "okx_market_STORJ-USDT.json", "market_not_listed:Instrument ID doesn't exist"),
    (("kucoin", "NOPEX", "USDT"), "kucoin_market_NOPEX-USDT.json", "market_not_listed:Trading pair does not exist"),
    (("binance", "NOPEX", "USDT"), "binance_market_NOPEXUSDT.json", "market_not_listed:Invalid symbol"),
])
def test_a_pair_that_is_not_trading_is_decided_from_market_data_alone(direct_vm, direct_deploy, direct_owner,
                                                                      watch, fixture, detail):
    # Only the market API is served: reading announcements would fail.
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "w", *watch)
    direct_vm.clear_mocks()
    _serve(direct_vm, fixture)
    dw.check("w")
    c = dw.latest_check("w")
    assert c["verdict"] == "NOT_TRADING" and c["reasons"] == [detail]
    assert c["facts"]["list_ok"] is None and c["facts"]["announcements"] == [] and c["reading"] is None
    assert dw.is_tradeable("w", 3600) is False


@pytest.mark.parametrize("exchange, field, value, detail", [
    ("binance", "status", "HALT", "status=HALT"),
    ("okx", "state", "suspend", "state=suspend"),
    ("kucoin", "enableTrading", False, "enableTrading=false"),
])
def test_a_listed_pair_whose_market_is_halted_is_not_trading(direct_vm, direct_deploy, direct_owner,
                                                             exchange, field, value, detail):
    # SYNTHETIC halted states: each exchange's real trading response with
    # its status field set to a documented non-trading value.
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "w", exchange, "BTC", "USDT")
    name = {"binance": "binance_market_BTCUSDT.json", "okx": "okx_market_BTC-USDT.json",
            "kucoin": "kucoin_market_STORJ-USDT.json"}[exchange]
    doc = json.loads(_fixture(name))
    if exchange == "binance":
        doc["symbols"][0][field] = value
    elif exchange == "okx":
        doc["data"][0][field] = value
    else:
        doc["data"].update(symbol="BTC-USDT", baseCurrency="BTC", **{field: value})
    direct_vm.clear_mocks()
    _mock(direct_vm, _market_url(exchange, "BTC", "USDT"), json.dumps(doc))
    dw.check("w")
    c = dw.latest_check("w")
    assert c["verdict"] == "NOT_TRADING" and c["reasons"] == [f"market_not_trading:{detail}"]


@pytest.mark.parametrize("status, body", [
    (451, '{"code":0,"msg":"Service unavailable from a restricted location"}'),
    (200, "<html><body>Access denied</body></html>"),
    (200, '{"code":"200000","data":null}'),
])
def test_an_unreadable_market_api_is_undetermined(direct_vm, direct_deploy, direct_owner, status, body):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "w", "kucoin", "STORJ", "USDT")
    direct_vm.clear_mocks()
    _mock(direct_vm, _market_url("kucoin", "STORJ", "USDT"), body, status)
    dw.check("w")
    c = dw.latest_check("w")
    assert c["verdict"] == "UNDETERMINED" and c["reasons"] == [f"market_unavailable:http_{status}"]


def test_a_market_answer_for_a_different_pair_is_not_accepted(direct_vm, direct_deploy, direct_owner):
    # A trading BTCUSDT answer served for STORJUSDT must not read as trading.
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "w", "binance", "STORJ", "USDT")
    direct_vm.clear_mocks()
    _mock(direct_vm, _market_url("binance", "STORJ", "USDT"), _fixture("binance_market_BTCUSDT.json"))
    dw.check("w")
    assert dw.latest_check("w")["reasons"] == ["market_unavailable:http_200"]


def test_network_failure_records_nothing(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "w", "kucoin", "STORJ", "USDT")
    direct_vm.clear_mocks()
    with pytest.raises(Exception):
        dw.check("w")
    assert dw.latest_verdict("w") == "NONE" and dw.get_state()["check_count"] == 0


LIVE_PROOF = json.loads((pathlib.Path(__file__).parent.parent / "studio-next" / "live_proof.json").read_text())


@pytest.mark.parametrize("watch_id, watch, serve", [
    ("kucoin-storj", ("kucoin", "STORJ", "USDT"), lambda vm: kucoin_storj_today(vm)),
    ("binance-btc", ("binance", "BTC", "USDT"), lambda vm: binance_btc_today(vm)),
    ("okx-storj", ("okx", "STORJ", "USDT"), lambda vm: _serve(vm, "okx_market_STORJ-USDT.json")),
    ("binance-storj", ("binance", "STORJ", "USDT"), lambda vm: _serve(vm, "binance_market_STORJUSDT.json")),
    ("okx-btc", ("okx", "BTC", "USDT"), lambda vm: okx_btc_today(vm)),
])
def test_fixtures_reproduce_the_facts_validators_agreed_on_live(direct_vm, direct_deploy, direct_owner,
                                                                watch_id, watch, serve):
    # The record each live check stored on Studio Next (studio-next/
    # live_proof.json) must come out identical - market facts, every
    # announcement scanned, and the digest of the exact text the reader was
    # shown - when this suite replays the committed fixtures.
    [live] = [e["check"] for e in LIVE_PROOF if e["step"] == "check" and e["watch_id"] == watch_id]
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, watch_id, *watch)
    direct_vm.clear_mocks()
    serve(direct_vm)
    dw.check(watch_id)
    c = dw.latest_check(watch_id)
    assert c["facts"] == live["facts"]
    assert (c["verdict"], c["reasons"], c["reading"]) == (live["verdict"], live["reasons"], live["reading"])


# --- 2. Announcements and verdicts -------------------------------------------


def test_announced_okx_spot_delisting(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "okx-storj", "okx", "STORJ", "USDT")
    okx_storj_before(direct_vm)
    dw.check("okx-storj")
    c = dw.latest_check("okx-storj")
    assert c["verdict"] == "DELISTING_ANNOUNCED" and c["effective_date"] == "2026-10-03"
    assert c["reasons"] == ["spot_delisting_announced"]
    assert c["reading"] == {"ends_spot": True, "effective_date": "2026-10-03", "evidence": OKX_STORJ_QUOTE,
                            "grounded": True}
    # All three recent spot notices were opened; only the one naming STORJ
    # was shown to the reader.
    shown = {a["ref"]: a["names_token"] for a in c["facts"]["announcements"]}
    assert shown == {OKX_STORJ: True, OKX_AEON: False, OKX_USD: False}
    assert c["facts"]["announcements"][0]["url"] == "https://www.okx.com/" + OKX_STORJ
    assert dw.is_tradeable("okx-storj", 3600) is False


def test_okx_global_help_centre_format_reads_the_same(direct_vm, direct_deploy, direct_owner):
    # The same announcement from OKX's global help centre (help/<slug>
    # URLs, a list that also carries futures notices): same verdict.
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "okx-storj", "okx", "STORJ", "USDT")
    direct_vm.clear_mocks()
    _trading_market(direct_vm, "okx", "STORJ", "USDT")  # SYNTHETIC
    _serve(direct_vm, "okx_list.json")
    _serve_details(direct_vm, "okx", [GLOBAL_OKX_STORJ, GLOBAL_OKX_AEON, GLOBAL_OKX_USDS])
    _reader(direct_vm, "okx", "STORJ", "USDT", True, "2026-10-03", OKX_STORJ_QUOTE)
    dw.check("okx-storj")
    c = dw.latest_check("okx-storj")
    assert c["verdict"] == "DELISTING_ANNOUNCED" and c["effective_date"] == "2026-10-03"
    assert [a["ref"] for a in c["facts"]["announcements"]] == [GLOBAL_OKX_STORJ, GLOBAL_OKX_AEON, GLOBAL_OKX_USDS]


def test_announced_binance_token_delisting(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-08-25T12:00:00Z")
    _watch(dw, "binance-storj", "binance", "STORJ", "USDT")
    direct_vm.clear_mocks()
    _trading_market(direct_vm, "binance", "STORJ", "USDT")  # SYNTHETIC
    _serve(direct_vm, "binance_list.json")
    _serve_details(direct_vm, "binance", [BINANCE_STORJ] + BINANCE_AUGUST_NOTICES)
    _reader(direct_vm, "binance", "STORJ", "USDT", True, "2026-09-03", BINANCE_STORJ_QUOTE)
    dw.check("binance-storj")
    c = dw.latest_check("binance-storj")
    assert c["verdict"] == "DELISTING_ANNOUNCED" and c["effective_date"] == "2026-09-03"
    storj = c["facts"]["announcements"][0]
    assert storj["ref"] == BINANCE_STORJ and storj["complete"] and storj["excerpt_chars"] > 10000


def test_removing_one_quote_pair_ends_that_pair_only(direct_vm, direct_deploy, direct_owner):
    # Binance's 2026-09-18 notice removes QNT/USDC. QNT/USDC: delisting
    # announced. QNT/USDT, reading the same notice: still trading.
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-17T12:00:00Z")
    _watch(dw, "qnt-usdc", "binance", "QNT", "USDC")
    _watch(dw, "qnt-usdt", "binance", "QNT", "USDT")
    for watch_id, quote, ends, date, evidence in [("qnt-usdc", "USDC", True, "2026-09-18", BINANCE_QNT_QUOTE),
                                                  ("qnt-usdt", "USDT", False, None, None)]:
        direct_vm.clear_mocks()
        _trading_market(direct_vm, "binance", "QNT", quote)  # SYNTHETIC
        _serve(direct_vm, "binance_list.json")
        _serve_details(direct_vm, "binance", BINANCE_QNT_NOTICES)
        _reader(direct_vm, "binance", "QNT", quote, ends, date, evidence)
        dw.check(watch_id)
    assert dw.latest_check("qnt-usdc")["verdict"] == "DELISTING_ANNOUNCED"
    assert dw.latest_check("qnt-usdc")["effective_date"] == "2026-09-18"
    usdt = dw.latest_check("qnt-usdt")
    assert usdt["verdict"] == "TRADING"
    assert [(a["ref"], a["names_token"]) for a in usdt["facts"]["announcements"]] == [
        (BINANCE_QNT_NOTICES[0], True), (BINANCE_QNT_NOTICES[1], False)]


def test_kucoin_special_treatment_delisting_read_with_an_earn_only_notice(direct_vm, direct_deploy, direct_owner):
    # The ST notice's title names no token; its text lists WAXP. The Earn
    # notice names WAXP in its title but ends only an Earn product.
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-05T12:00:00Z")
    _watch(dw, "kucoin-waxp", "kucoin", "WAXP", "USDT")
    direct_vm.clear_mocks()
    _trading_market(direct_vm, "kucoin", "WAXP", "USDT")  # SYNTHETIC
    _serve(direct_vm, "kucoin_list.json")
    _serve_details(direct_vm, "kucoin", [KUCOIN_ST, KUCOIN_EARN_WAXP])
    _reader(direct_vm, "kucoin", "WAXP", "USDT", True, "2026-09-07", KUCOIN_ST_QUOTE)
    dw.check("kucoin-waxp")
    c = dw.latest_check("kucoin-waxp")
    assert c["verdict"] == "DELISTING_ANNOUNCED" and c["effective_date"] == "2026-09-07"
    assert {a["ref"] for a in c["facts"]["announcements"] if a["names_token"]} == {KUCOIN_ST, KUCOIN_EARN_WAXP}


def test_a_delisting_date_that_has_passed_while_the_market_still_trades_is_undetermined(
        direct_vm, direct_deploy, direct_owner):
    # OKX removed STORJ/USDC on 30 September. If the market API still says
    # trading on 1 October, something doesn't add up - fail closed.
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-10-01T12:00:00Z")
    _watch(dw, "okx-storj-usdc", "okx", "STORJ", "USDC")
    direct_vm.clear_mocks()
    _trading_market(direct_vm, "okx", "STORJ", "USDC")  # SYNTHETIC
    _serve(direct_vm, "okx_list_us.json")
    _serve_details(direct_vm, "okx", [OKX_STORJ, OKX_AEON, OKX_USD])
    _reader(direct_vm, "okx", "STORJ", "USDC", True, "2026-09-30", "STORJ/USDC September 30, 2026, 08:00 - 10:00 UTC")
    dw.check("okx-storj-usdc")
    c = dw.latest_check("okx-storj-usdc")
    assert c["verdict"] == "UNDETERMINED"
    assert c["reasons"] == ["delisting_date_passed_but_market_trading:2026-09-30"]


def test_announcements_older_than_the_lookback_are_not_read(direct_vm, direct_deploy, direct_owner):
    # 62 days after KuCoin's STORJ futures notice it is out of the window:
    # TRADING without opening it or calling the LLM.
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-10-24T12:00:00Z")
    _watch(dw, "kucoin-storj", "kucoin", "STORJ", "USDT")
    direct_vm.clear_mocks()
    _serve(direct_vm, "kucoin_market_STORJ-USDT.json")
    _serve(direct_vm, "kucoin_list.json")
    dw.check("kucoin-storj")
    c = dw.latest_check("kucoin-storj")
    assert c["verdict"] == "TRADING" and c["facts"]["announcements"] == [] and c["reading"] is None


# --- 3. The reader's limits ----------------------------------------------------


def test_a_delisting_claim_without_a_real_quote_is_not_published(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "kucoin-storj", "kucoin", "STORJ", "USDT")
    kucoin_storj_today(direct_vm, True, date="2026-08-26",
                       evidence="KuCoin will delist the STORJ/USDT spot trading pair")
    dw.check("kucoin-storj")
    c = dw.latest_check("kucoin-storj")
    assert c["verdict"] == "UNDETERMINED" and c["reasons"] == ["delisting_claim_unquoted"]
    assert c["reading"]["grounded"] is False


def test_a_real_quote_with_a_date_the_announcement_never_states_is_not_published(
        direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "okx-storj", "okx", "STORJ", "USDT")
    okx_storj_before(direct_vm, date="2026-10-13")
    dw.check("okx-storj")
    assert dw.latest_check("okx-storj")["reasons"] == ["delisting_claim_unquoted"]


def test_a_missing_date_is_not_published(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "okx-storj", "okx", "STORJ", "USDT")
    okx_storj_before(direct_vm, date=None)
    dw.check("okx-storj")
    assert dw.latest_check("okx-storj")["reasons"] == ["delisting_claim_unquoted"]


def test_stitched_quote_of_genuine_fragments_is_grounded(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "okx-storj", "okx", "STORJ", "USDT")
    okx_storj_before(direct_vm, evidence="Affected tokens: DORA, ICX, STORJ, ZEUS, ELF ... " + OKX_STORJ_QUOTE)
    dw.check("okx-storj")
    assert dw.latest_check("okx-storj")["verdict"] == "DELISTING_ANNOUNCED"


def test_stitched_quote_with_one_invented_fragment_is_not_grounded(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "okx-storj", "okx", "STORJ", "USDT")
    okx_storj_before(direct_vm, evidence=OKX_STORJ_QUOTE + " ... STORJ will also be removed from every other venue")
    dw.check("okx-storj")
    assert dw.latest_check("okx-storj")["reasons"] == ["delisting_claim_unquoted"]


@pytest.mark.parametrize("answer", ['{"ends_spot": "no"}', '{"verdict": "TRADING"}', '["ends_spot", false]'])
def test_an_unreadable_reader_answer_is_undetermined_not_trading(direct_vm, direct_deploy, direct_owner, answer):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "kucoin-storj", "kucoin", "STORJ", "USDT")
    direct_vm.clear_mocks()
    _serve(direct_vm, "kucoin_market_STORJ-USDT.json")
    _serve(direct_vm, "kucoin_list.json")
    _serve_details(direct_vm, "kucoin", [KUCOIN_FUTURES])
    direct_vm.mock_llm("END SPOT trading of the STORJ/USDT pair on kucoin", answer)
    dw.check("kucoin-storj")
    c = dw.latest_check("kucoin-storj")
    assert c["verdict"] == "UNDETERMINED" and c["reasons"] == ["reader_gave_no_answer"] and c["reading"] is None


def _long_futures_notice() -> str:
    # SYNTHETIC: the real KuCoin futures notice with its own text repeated
    # until it is longer than one reading covers.
    doc = json.loads(_fixture(_detail_name("kucoin", KUCOIN_FUTURES)))
    doc["data"]["content"] = doc["data"]["content"] * 5
    return json.dumps(doc)


def test_not_ending_trading_is_never_accepted_from_a_cut_announcement(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "kucoin-storj", "kucoin", "STORJ", "USDT")
    kucoin_storj_today(direct_vm)
    direct_vm.clear_mocks()
    _serve(direct_vm, "kucoin_market_STORJ-USDT.json")
    _serve(direct_vm, "kucoin_list.json")
    _serve(direct_vm, _detail_name("kucoin", KUCOIN_FUTURES), body=_long_futures_notice())
    _reader(direct_vm, "kucoin", "STORJ", "USDT", False)
    dw.check("kucoin-storj")
    c = dw.latest_check("kucoin-storj")
    assert c["verdict"] == "UNDETERMINED" and c["reasons"] == [f"announcement_too_long_to_clear:{KUCOIN_FUTURES}"]
    assert c["facts"]["announcements"][0]["complete"] is False
    assert c["facts"]["announcements"][0]["excerpt_chars"] == 12000


def test_a_quoted_delisting_in_a_cut_announcement_still_counts(direct_vm, direct_deploy, direct_owner):
    # The cut limits what can be cleared, not what can be found. SYNTHETIC:
    # OKX's real STORJ notice with its article repeated past one reading.
    page = _fixture(_detail_name("okx", OKX_STORJ))
    inner = re.search(r"(<article\b[^>]*>)(.*?)(</article>)", page, re.S)
    page = page.replace(inner.group(0), inner.group(1) + inner.group(2) * 3 + inner.group(3))
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "okx-storj", "okx", "STORJ", "USDT")
    okx_storj_before(direct_vm)
    direct_vm.clear_mocks()
    _trading_market(direct_vm, "okx", "STORJ", "USDT")  # SYNTHETIC
    _serve(direct_vm, "okx_list_us.json")
    _serve_details(direct_vm, "okx", [OKX_AEON, OKX_USD])
    _serve(direct_vm, _detail_name("okx", OKX_STORJ), body=page)
    _reader(direct_vm, "okx", "STORJ", "USDT", True, "2026-10-03", OKX_STORJ_QUOTE)
    dw.check("okx-storj")
    c = dw.latest_check("okx-storj")
    assert c["facts"]["announcements"][0]["complete"] is False
    assert c["verdict"] == "DELISTING_ANNOUNCED"


# --- 4. Fail-closed scanning ----------------------------------------------------


def test_an_unreadable_announcement_list_is_undetermined(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "kucoin-storj", "kucoin", "STORJ", "USDT")
    direct_vm.clear_mocks()
    _serve(direct_vm, "kucoin_market_STORJ-USDT.json")
    _serve(direct_vm, "kucoin_list.json", body="<html>Just a moment...</html>", status=503)
    dw.check("kucoin-storj")
    c = dw.latest_check("kucoin-storj")
    assert c["verdict"] == "UNDETERMINED" and c["reasons"] == ["announcements_unavailable"]
    assert c["facts"]["list_ok"] is False


def _break_okx_url(doc):
    doc["data"][0]["details"][5]["url"] = "https://evil.example/help/okx-to-delist-selected-usds-spot-trading-pairs"


def _break_okx_type(doc):
    doc["data"][0]["details"][5]["annType"] = "announcements-new-listings"


def _break_kucoin_category(doc):
    doc["items"][20]["categories"] = [c for c in doc["items"][20]["categories"] if c["path"] != "delistings"]


def _break_kucoin_path(doc):
    doc["items"][3]["path"] = "/../../api/v2/accounts"


def _break_binance_code(doc):
    doc["data"]["catalogs"][0]["articles"][7]["code"] = "../../private/query?x="


def _break_binance_catalog(doc):
    doc["data"]["catalogs"][0]["catalogId"] = 48


@pytest.mark.parametrize("exchange, base, now, breaker", [
    ("okx", "STORJ", "2026-09-25T12:00:00Z", _break_okx_url),
    ("okx", "STORJ", "2026-09-25T12:00:00Z", _break_okx_type),
    ("kucoin", "STORJ", TODAY, _break_kucoin_category),
    ("kucoin", "STORJ", TODAY, _break_kucoin_path),
    ("binance", "BTC", TODAY, _break_binance_code),
    ("binance", "BTC", TODAY, _break_binance_catalog),
])
def test_one_malformed_list_entry_makes_the_whole_list_unreadable(direct_vm, direct_deploy, direct_owner,
                                                                  exchange, base, now, breaker):
    # A list entry with a foreign URL, a path that isn't a plain slug, or an
    # entry from outside the delisting category means the format changed or
    # the list isn't what it claims: nothing from it is trusted.
    doc = json.loads(_fixture(f"{exchange}_list.json"))
    breaker(doc)
    dw = _deploy(direct_vm, direct_deploy, direct_owner, now)
    _watch(dw, "w", exchange, base, "USDT")
    direct_vm.clear_mocks()
    _trading_market(direct_vm, exchange, base, "USDT")  # SYNTHETIC
    _serve(direct_vm, f"{exchange}_list.json", body=json.dumps(doc))
    dw.check("w")
    assert dw.latest_check("w")["reasons"] == ["announcements_unavailable"]


def test_a_list_that_does_not_reach_back_over_the_lookback_is_undetermined(direct_vm, direct_deploy, direct_owner):
    # Only the 12 newest KuCoin entries (back to 2026-08-12): anything
    # announced between 5 and 12 August could have fallen off the page.
    doc = json.loads(_fixture("kucoin_list.json"))
    doc["items"] = doc["items"][:12]
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "kucoin-storj", "kucoin", "STORJ", "USDT")
    direct_vm.clear_mocks()
    _serve(direct_vm, "kucoin_market_STORJ-USDT.json")
    _serve(direct_vm, "kucoin_list.json", body=json.dumps(doc))
    dw.check("kucoin-storj")
    c = dw.latest_check("kucoin-storj")
    assert c["reasons"] == ["announcement_list_too_short:2026-08-12"] and c["facts"]["announcements"] == []


def test_an_unreadable_announcement_is_undetermined(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "binance-btc", "binance", "BTC", "USDT")
    binance_btc_today(direct_vm)
    direct_vm.clear_mocks()
    _serve(direct_vm, "binance_market_BTCUSDT.json")
    _serve(direct_vm, "binance_list.json")
    _serve_details(direct_vm, "binance", BINANCE_TODAY_NOTICES[1:])
    _serve(direct_vm, _detail_name("binance", BINANCE_TODAY_NOTICES[0]), body="", status=502)
    dw.check("binance-btc")
    c = dw.latest_check("binance-btc")
    assert c["verdict"] == "UNDETERMINED"
    assert c["reasons"] == [f"announcement_unreadable:{BINANCE_TODAY_NOTICES[0]}"]


def _okx_storj_scan(direct_vm):
    _trading_market(direct_vm, "okx", "STORJ", "USDT")  # SYNTHETIC
    _serve(direct_vm, "okx_list_us.json")
    return "okx", "STORJ", "2026-09-25T12:00:00Z", [OKX_STORJ, OKX_AEON, OKX_USD]


def _binance_btc_scan(direct_vm):
    _serve(direct_vm, "binance_market_BTCUSDT.json")
    _serve(direct_vm, "binance_list.json")
    return "binance", "BTC", TODAY, BINANCE_TODAY_NOTICES


def _kucoin_waxp_scan(direct_vm):
    _trading_market(direct_vm, "kucoin", "WAXP", "USDT")  # SYNTHETIC
    _serve(direct_vm, "kucoin_list.json")
    return "kucoin", "WAXP", "2026-09-05T12:00:00Z", [KUCOIN_ST, KUCOIN_EARN_WAXP]


SCANS = [_okx_storj_scan, _binance_btc_scan, _kucoin_waxp_scan]


@pytest.mark.parametrize("scan", SCANS)
def test_a_page_that_is_not_the_announcement_asked_for_is_unreadable(direct_vm, direct_deploy, direct_owner, scan):
    # The URL for one announcement serves another real announcement: the ref
    # check catches it, so no text is attributed to the wrong announcement.
    direct_vm.clear_mocks()
    exchange, base, now, refs = scan(direct_vm)
    dw = _deploy(direct_vm, direct_deploy, direct_owner, now)
    _watch(dw, "w", exchange, base, "USDT")
    _serve_details(direct_vm, exchange, refs[1:])
    _serve(direct_vm, _detail_name(exchange, refs[0]), body=_fixture(_detail_name(exchange, refs[1])))
    direct_vm.mock_llm("END SPOT trading", json.dumps({"ends_spot": False, "effective_date": None, "evidence": None}))
    dw.check("w")
    assert dw.latest_check("w")["reasons"] == [f"announcement_unreadable:{refs[0]}"]


def _drop_category(exchange: str, body: str) -> str:
    if exchange == "binance":
        doc = json.loads(body)
        doc["data"]["firstCatalogId"] = 48
        return json.dumps(doc)
    if exchange == "okx":
        return body.replace('"slug": "announcements-delistings"', '"slug": "announcements-new-listings"')
    doc = json.loads(body)
    doc["data"]["categories"] = [c for c in doc["data"]["categories"] if c["path"] != "delistings"]
    return json.dumps(doc)


@pytest.mark.parametrize("scan", SCANS)
def test_an_announcement_outside_the_delisting_category_is_undetermined(direct_vm, direct_deploy, direct_owner,
                                                                        scan):
    direct_vm.clear_mocks()
    exchange, base, now, refs = scan(direct_vm)
    dw = _deploy(direct_vm, direct_deploy, direct_owner, now)
    _watch(dw, "w", exchange, base, "USDT")
    _serve_details(direct_vm, exchange, refs[1:])
    _serve(direct_vm, _detail_name(exchange, refs[0]),
           body=_drop_category(exchange, _fixture(_detail_name(exchange, refs[0]))))
    direct_vm.mock_llm("END SPOT trading", json.dumps({"ends_spot": False, "effective_date": None, "evidence": None}))
    dw.check("w")
    assert dw.latest_check("w")["reasons"] == [f"announcement_not_in_delisting_category:{refs[0]}"]


def test_a_quoted_delisting_outranks_an_unreadable_neighbour(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "okx-storj", "okx", "STORJ", "USDT")
    okx_storj_before(direct_vm)
    direct_vm.clear_mocks()
    _trading_market(direct_vm, "okx", "STORJ", "USDT")  # SYNTHETIC
    _serve(direct_vm, "okx_list_us.json")
    _serve_details(direct_vm, "okx", [OKX_STORJ, OKX_AEON])
    _serve(direct_vm, _detail_name("okx", OKX_USD), body="", status=500)
    _reader(direct_vm, "okx", "STORJ", "USDT", True, "2026-10-03", OKX_STORJ_QUOTE)
    dw.check("okx-storj")
    assert dw.latest_check("okx-storj")["verdict"] == "DELISTING_ANNOUNCED"


def test_more_matching_announcements_than_one_reading_covers_is_undetermined(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC list: Binance's real list plus four extra copies of today's
    # newest spot notice under new codes - eight matches, six read.
    doc = json.loads(_fixture("binance_list.json"))
    articles = doc["data"]["catalogs"][0]["articles"]
    newest = next(a for a in articles if a["code"] == BINANCE_TODAY_NOTICES[0])
    extra = [dict(newest, code=f"{i:032x}") for i in range(1, 5)]
    doc["data"]["catalogs"][0]["articles"] = extra + articles
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "binance-btc", "binance", "BTC", "USDT")
    direct_vm.clear_mocks()
    _serve(direct_vm, "binance_market_BTCUSDT.json")
    _serve(direct_vm, "binance_list.json", body=json.dumps(doc))
    body = _fixture(_detail_name("binance", BINANCE_TODAY_NOTICES[0]))
    for e in extra:
        _mock(direct_vm, "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode="
              + e["code"], body.replace(BINANCE_TODAY_NOTICES[0], e["code"]))
    _serve_details(direct_vm, "binance", BINANCE_TODAY_NOTICES[:2])
    dw.check("binance-btc")
    c = dw.latest_check("binance-btc")
    assert c["facts"]["matching_announcements"] == 8 and len(c["facts"]["announcements"]) == 6
    assert c["verdict"] == "UNDETERMINED" and c["reasons"] == ["too_many_announcements:8"]


def test_titles_about_other_products_are_not_scanned_as_spot_notices(direct_vm, direct_deploy, direct_owner):
    # As of 2026-09-25 KuCoin's recent titles are futures, Earn and
    # "Earn ... Delist Certain Assets" notices: none is a spot notice, none
    # names ZEUS, so nothing is opened (no detail mocks are served).
    # SYNTHETIC: KuCoin's real "KuCoin Earn to Adjust Earnings for Selected
    # Simple Earn (Flexible) Products and Delist Certain Assets" entry, moved
    # into the window - "Selected ... Assets" without "spot", in an Earn title.
    doc = json.loads(_fixture("kucoin_list.json"))
    earn = next(i for i in doc["items"] if i["title"].startswith("KuCoin Earn to Adjust Earnings"))
    doc["items"].insert(0, dict(earn, path=earn["path"] + "-x", publish_ts=1789900000))
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "kucoin-zeus", "kucoin", "ZEUS", "USDT")
    direct_vm.clear_mocks()
    _trading_market(direct_vm, "kucoin", "ZEUS", "USDT")  # SYNTHETIC
    _serve(direct_vm, "kucoin_list.json", body=json.dumps(doc))
    dw.check("kucoin-zeus")
    c = dw.latest_check("kucoin-zeus")
    assert c["verdict"] == "TRADING" and c["facts"]["matching_announcements"] == 0


# --- Registration and views ---------------------------------------------------


def test_register_builds_every_url_itself(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "okx-btc", "okx", "BTC", "USDT")
    w = dw.get_watch("okx-btc")
    assert w["market_url"] == "https://www.okx.com/api/v5/public/instruments?instType=SPOT&instId=BTC-USDT"
    assert w["announcements_url"] == "https://www.okx.com/api/v5/support/announcements?annType=announcements-delistings"
    assert w["check_count"] == 0 and dw.latest_verdict("okx-btc") == "NONE"
    assert dw.latest_check("okx-btc") == {"watch_id": "okx-btc", "verdict": "NONE"}
    assert dw.list_watches() == [{"watch_id": "okx-btc", "exchange": "okx", "base": "BTC", "quote": "USDT",
                                  "label": "BTC/USDT on okx", "check_count": 0}]
    assert dw.get_rules()["named_lookback_days"] == 60


@pytest.mark.parametrize("watch_id, exchange, base, quote, label, message", [
    ("w", "bybit", "BTC", "USDT", "x", "exchange must be"),
    ("w", "Binance", "BTC", "USDT", "x", "exchange must be"),
    ("w", "okx", "btc", "USDT", "x", "base must be"),
    ("w", "okx", "BTC-USDT&instType=SWAP", "USDT", "x", "base must be"),
    ("w", "okx", "BTC/", "USDT", "x", "base must be"),
    ("w", "okx", "BTC", "USDT?x=1", "x", "quote must be"),
    ("w", "okx", "BTC", "BTC", "x", "base and quote must differ"),
    ("w", "okx", "BTC", "USDT", "", "label must be"),
    ("w", "okx", "BTC", "USDT", "x" * 101, "label must be"),
    ("bad id", "okx", "BTC", "USDT", "x", "watch_id must be"),
])
def test_register_rejects_malformed_input(direct_vm, direct_deploy, direct_owner, watch_id, exchange, base, quote,
                                          label, message):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match=message):
        dw.register_watch(watch_id, exchange, base, quote, label)


def test_register_rejects_duplicates_and_check_rejects_unknown(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "w", "okx", "BTC", "USDT")
    with pytest.raises(Exception, match="already registered"):
        _watch(dw, "w", "kucoin", "STORJ", "USDT")
    with pytest.raises(Exception, match="unknown watch_id"):
        dw.check("nope")


def test_is_tradeable_requires_a_fresh_trading_check_and_the_latest_check_wins(
        direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "kucoin-storj", "kucoin", "STORJ", "USDT")
    assert dw.is_tradeable("kucoin-storj", 10**6) is False and dw.is_tradeable("nope", 10**6) is False
    kucoin_storj_today(direct_vm)
    dw.check("kucoin-storj")
    assert dw.is_tradeable("kucoin-storj", 3600) is True
    _warp(direct_vm, "2026-10-04T14:00:00Z")
    assert dw.is_tradeable("kucoin-storj", 3600) is False and dw.is_tradeable("kucoin-storj", 7200) is True
    direct_vm.clear_mocks()
    _mock(direct_vm, _market_url("kucoin", "STORJ", "USDT"), "", 503)
    dw.check("kucoin-storj")
    assert dw.is_tradeable("kucoin-storj", 10**6) is False
    assert [c["verdict"] for c in dw.get_checks(0, 10)] == ["UNDETERMINED", "TRADING"]
    assert [c["verdict"] for c in dw.get_checks(1, 10)] == ["TRADING"]
    assert dw.get_check(0)["verdict"] == "TRADING" and dw.get_watch("kucoin-storj")["check_count"] == 2


# --- 5. Consensus boundary ---------------------------------------------------


def test_validator_accepts_an_honest_leader(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "okx-storj", "okx", "STORJ", "USDT")
    okx_storj_before(direct_vm)
    dw.check("okx-storj")
    assert direct_vm.run_validator() is True


def test_validator_rejects_a_leader_hiding_a_delisting(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "okx-storj", "okx", "STORJ", "USDT")
    okx_storj_before(direct_vm)
    dw.check("okx-storj")
    leader = _leader(direct_vm)
    leader["reading"] = {"ends_spot": False, "effective_date": None, "evidence": None, "grounded": False}
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_a_delisting_its_own_reader_does_not_find(direct_vm, direct_deploy, direct_owner):
    # The leader's quote is genuine, but the validator's reader sees a
    # futures-only notice: the decisions differ.
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "kucoin-storj", "kucoin", "STORJ", "USDT")
    kucoin_storj_today(direct_vm)
    dw.check("kucoin-storj")
    leader = _leader(direct_vm)
    leader["reading"] = {"ends_spot": True, "effective_date": "2026-10-26", "grounded": False,
                         "evidence": "KuCoin Futures will delist the following perpetual contracts"}
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_a_quote_not_in_its_own_copy(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "okx-storj", "okx", "STORJ", "USDT")
    okx_storj_before(direct_vm)
    dw.check("okx-storj")
    leader = _leader(direct_vm)
    leader["reading"]["evidence"] = "OKX will delist STORJ/USDT on October 3, 2026 at the request of regulators"
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_a_different_effective_date(direct_vm, direct_deploy, direct_owner):
    # STORJ/USDC's date (30 September) is in the same notice - grounded, but
    # not the date this validator's reader gives for STORJ/USDT.
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "okx-storj", "okx", "STORJ", "USDT")
    okx_storj_before(direct_vm)
    dw.check("okx-storj")
    leader = _leader(direct_vm)
    leader["reading"].update(effective_date="2026-09-30",
                             evidence="STORJ/USDC September 30, 2026, 08:00 - 10:00 UTC")
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_a_reading_when_nothing_names_the_token(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "binance-btc", "binance", "BTC", "USDT")
    binance_btc_today(direct_vm)
    dw.check("binance-btc")
    assert direct_vm.run_validator() is True
    leader = _leader(direct_vm)
    leader["reading"] = {"ends_spot": False, "effective_date": None, "evidence": None, "grounded": False}
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_tampered_facts(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner)
    _watch(dw, "kucoin-storj", "kucoin", "STORJ", "USDT")
    kucoin_storj_today(direct_vm)
    dw.check("kucoin-storj")
    for tamper in (lambda l: l["facts"].update(market_detail="enableTrading=false"),
                   lambda l: l["facts"]["announcements"].clear(),
                   lambda l: l["facts"]["announcements"][0].update(names_token=False),
                   lambda l: l.update(facts_digest="0" * 64)):
        leader = _leader(direct_vm)
        tamper(leader)
        assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_malformed_readings_and_leader_errors(direct_vm, direct_deploy, direct_owner):
    dw = _deploy(direct_vm, direct_deploy, direct_owner, "2026-09-25T12:00:00Z")
    _watch(dw, "okx-storj", "okx", "STORJ", "USDT")
    okx_storj_before(direct_vm)
    dw.check("okx-storj")
    for reading in ({"ends_spot": True}, {"ends_spot": "yes", "effective_date": None, "evidence": None,
                                          "grounded": False},
                    {"ends_spot": False, "effective_date": "2026-10-03", "evidence": None, "grounded": False},
                    {"ends_spot": True, "effective_date": "3 Oct", "evidence": OKX_STORJ_QUOTE, "grounded": True}):
        leader = _leader(direct_vm)
        leader["reading"] = reading
        assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False
    leader = _leader(direct_vm)
    leader["reading"]["grounded"] = False  # understated grounding is a mismatch too
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False
    assert direct_vm.run_validator(leader_error=Exception("fetch failed")) is False
    assert direct_vm.run_validator(leader_result="not json") is False
    assert direct_vm.run_validator(leader_result="[]") is False
