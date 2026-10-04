"""
Captures the real exchange responses the test fixtures are built from.

Every URL here is one the contract itself builds (same endpoints, same
query strings). Responses are saved byte-for-byte under
tests/fixtures/raw/ (gitignored - they include each site's boilerplate),
with their SHA-256 in tests/fixtures/raw_manifest.json.
scripts/build_fixtures.py then reduces them to the committed fixtures.

The captures used by the committed fixtures were taken on 2026-10-04;
re-running this script captures the exchanges as they are *now*, which
will differ (new announcements, delisted pairs).

One capture can't be taken from here: OKX localises its help centre by the
reader's region, and Studio Next's validators get the en-us list. That list
(okx_list_us.json) was captured through GenVM itself - research/README.md
gives the probe transaction - and is kept as-is by this script.

Usage (from the repo root):  python3 scripts/capture_raw.py
"""

import datetime
import hashlib
import json
import pathlib
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
RAW = REPO / "tests" / "fixtures" / "raw"

BINANCE_DETAIL = "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode="
OKX_DETAIL = "https://www.okx.com/help/"
OKX_DETAIL_US = "https://www.okx.com/en-us/help/"
KUCOIN_DETAIL = "https://www.kucoin.com/_api/cms/articles"

CAPTURES = {
    # Market status - the pair as it is on the capture date.
    "binance_market_STORJUSDT.json": "https://data-api.binance.vision/api/v3/exchangeInfo?symbol=STORJUSDT",
    "binance_market_BTCUSDT.json": "https://data-api.binance.vision/api/v3/exchangeInfo?symbol=BTCUSDT",
    "binance_market_NOPEXUSDT.json": "https://data-api.binance.vision/api/v3/exchangeInfo?symbol=NOPEXUSDT",
    "okx_market_STORJ-USDT.json": "https://www.okx.com/api/v5/public/instruments?instType=SPOT&instId=STORJ-USDT",
    "okx_market_BTC-USDT.json": "https://www.okx.com/api/v5/public/instruments?instType=SPOT&instId=BTC-USDT",
    "kucoin_market_STORJ-USDT.json": "https://api.kucoin.com/api/v2/symbols/STORJ-USDT",
    "kucoin_market_NOPEX-USDT.json": "https://api.kucoin.com/api/v2/symbols/NOPEX-USDT",
    # Each exchange's own delisting-announcement list.
    "binance_list.json": "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&pageNo=1&pageSize=50&catalogId=161",
    "okx_list.json": "https://www.okx.com/api/v5/support/announcements?annType=announcements-delistings",
    "kucoin_list.json": "https://www.kucoin.com/_api/cms/articles?page=1&pageSize=50&category=delistings&lang=en_US",
    # Binance announcements: the spot-pair notices of the last three weeks,
    # the STORJ delisting and the spot-pair notices around it.
    "binance_d_63415de54a164619aaaf245850349654.json": BINANCE_DETAIL + "63415de54a164619aaaf245850349654",
    "binance_d_7d17add1ffe6416391f65a001734e1c7.json": BINANCE_DETAIL + "7d17add1ffe6416391f65a001734e1c7",
    "binance_d_545ca5ad28254999b793bcf1ddd51f93.json": BINANCE_DETAIL + "545ca5ad28254999b793bcf1ddd51f93",
    "binance_d_30b1347d97324180bb469c761e4eed5a.json": BINANCE_DETAIL + "30b1347d97324180bb469c761e4eed5a",
    "binance_d_b9198262dd5f4071a1119b9f52cbe00c.json": BINANCE_DETAIL + "b9198262dd5f4071a1119b9f52cbe00c",
    "binance_d_d72915ed7a60473b92f0818d959a227a.json": BINANCE_DETAIL + "d72915ed7a60473b92f0818d959a227a",
    "binance_d_fab1676df7fb464a9e4634c6f777659e.json": BINANCE_DETAIL + "fab1676df7fb464a9e4634c6f777659e",
    "binance_d_b2d783892ef54b4daddecf142076a8cf.json": BINANCE_DETAIL + "b2d783892ef54b4daddecf142076a8cf",
    "binance_d_23504a5454d545998414c9ad3e8832f3.json": BINANCE_DETAIL + "23504a5454d545998414c9ad3e8832f3",
    # OKX: the STORJ spot delisting and the two other spot notices near it,
    # from the global help centre and from the en-us one validators are served.
    "okx_d_help_okx-to-delist-dora-icx-storj-zeus-and-elf-spot-trading-pairs.html":
        OKX_DETAIL + "okx-to-delist-dora-icx-storj-zeus-and-elf-spot-trading-pairs",
    "okx_d_help_okx-to-delist-aeon-usd-spot-trading-pair.html": OKX_DETAIL + "okx-to-delist-aeon-usd-spot-trading-pair",
    "okx_d_help_okx-to-delist-selected-usds-spot-trading-pairs.html":
        OKX_DETAIL + "okx-to-delist-selected-usds-spot-trading-pairs",
    "okx_d_en-us_help_okx-to-delist-dora-icx-storj-zeus-and-elf-spot-trading-pairs.html":
        OKX_DETAIL_US + "okx-to-delist-dora-icx-storj-zeus-and-elf-spot-trading-pairs",
    "okx_d_en-us_help_okx-to-delist-aeon-usd-spot-trading-pair.html":
        OKX_DETAIL_US + "okx-to-delist-aeon-usd-spot-trading-pair",
    "okx_d_en-us_help_okx-to-delist-selected-usd-spot-trading-pairs.html":
        OKX_DETAIL_US + "okx-to-delist-selected-usd-spot-trading-pairs",
    # KuCoin: the futures-only STORJ announcement (the title trap), a real
    # spot delisting, and an Earn-only announcement for one of its tokens.
    "kucoin_d_en-kucoin-futures-will-delist-the-icxusdt-and-storjusdt-perpetual-contracts-and-related-services-2026-08-26.json":
        KUCOIN_DETAIL + "/en-kucoin-futures-will-delist-the-icxusdt-and-storjusdt-perpetual-contracts-and-related-services-2026-08-26?lang=en_US",
    "kucoin_d_en-st-kucoin-will-delist-multiple-tokens-on-2026-09-07-1.json":
        KUCOIN_DETAIL + "/en-st-kucoin-will-delist-multiple-tokens-on-2026-09-07-1?lang=en_US",
    "kucoin_d_en-kucoin-earn-will-delist-the-waxp-products.json":
        KUCOIN_DETAIL + "/en-kucoin-earn-will-delist-the-waxp-products?lang=en_US",
}


def fetch(url: str) -> tuple:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DelistWatch fixture capture)"})
    try:
        with urllib.request.urlopen(request, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path = REPO / "tests" / "fixtures" / "raw_manifest.json"
    previous = json.loads(manifest_path.read_text())["captures"] if manifest_path.exists() else {}
    # Captures taken through GenVM are kept exactly as they are.
    manifest = {name: meta for name, meta in previous.items() if meta.get("source") == "studio-next"}
    for name, url in CAPTURES.items():
        status, body = fetch(url)
        (RAW / name).write_bytes(body)
        manifest[name] = {"url": url, "status": status, "bytes": len(body),
                          "sha256": hashlib.sha256(body).hexdigest()}
        print(f"{status} {len(body):>7} {name}")
    out = {"captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "captures": manifest}
    manifest_path.write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
