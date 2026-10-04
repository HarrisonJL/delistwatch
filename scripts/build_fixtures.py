"""
Builds the committed test fixtures from the raw captures.

The raw captures (scripts/capture_raw.py, gitignored) are the exchanges'
responses byte for byte, including site chrome: OKX's article pages are
75-90 KB of HTML around a 3-5 KB announcement, Binance's article API wraps
each notice in footers, risk warnings and related-article lists. This
script keeps only what DelistWatch reads - the same JSON paths, the same
script tag, the same <article> element - and drops the rest. Announcement
text itself is never edited.

Every reduction is checked: the contract's own parsers must return exactly
the same result for the reduced fixture as for the raw capture, or the
script fails.

Usage (from the repo root):  python3 scripts/build_fixtures.py
"""

import importlib.util
import json
import pathlib
import re
import sys
import types

REPO = pathlib.Path(__file__).resolve().parent.parent
RAW = REPO / "tests" / "fixtures" / "raw"
OUT = REPO / "tests" / "fixtures"


def _load_contract():
    # The parsers are plain Python; stub the SDK names the module touches at
    # import time so they can run outside GenVM.
    class _Any:
        def __getattr__(self, k):
            return _Any()

        def __call__(self, *a, **k):
            return a[0] if len(a) == 1 and callable(a[0]) and not k else _Any()

        def __getitem__(self, k):
            return _Any()

        def __mro_entries__(self, bases):
            return (object,)

    stub = types.ModuleType("genlayer")
    stub.gl, stub.TreeMap, stub.DynArray, stub.Address = _Any(), _Any(), _Any(), _Any()
    stub.allow_storage, stub.u32 = (lambda c: c), int
    stub.__all__ = ["gl", "allow_storage", "TreeMap", "DynArray", "Address", "u32"]
    sys.modules["genlayer"] = stub
    spec = importlib.util.spec_from_file_location("delist_watch", REPO / "contracts" / "delist_watch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pick(d: dict, keys) -> dict:
    return {k: d[k] for k in keys if k in d}


def reduce_market(exchange: str, doc: dict) -> dict:
    if exchange == "binance":
        if "symbols" not in doc:
            return doc
        return {"timezone": doc.get("timezone"),
                "symbols": [_pick(s, ("symbol", "status", "baseAsset", "quoteAsset")) for s in doc["symbols"]]}
    if exchange == "okx":
        return {"code": doc["code"], "msg": doc.get("msg", ""),
                "data": [_pick(d, ("instId", "instType", "baseCcy", "quoteCcy", "state")) for d in doc["data"]]}
    if "data" not in doc:
        return doc
    return {"code": doc["code"], "data": _pick(doc["data"], ("symbol", "baseCurrency", "quoteCurrency",
                                                             "enableTrading", "st"))}


def reduce_list(exchange: str, doc: dict) -> dict:
    if exchange == "binance":
        catalog = doc["data"]["catalogs"][0]
        return {"code": doc["code"], "data": {"catalogs": [{
            "catalogId": catalog["catalogId"], "catalogName": catalog["catalogName"],
            "articles": [_pick(a, ("code", "title", "releaseDate")) for a in catalog["articles"]]}]}}
    if exchange == "okx":
        return doc
    return {"code": doc["code"], "success": doc["success"], "items": [
        dict(_pick(i, ("title", "path", "publish_ts", "publish_at")),
             categories=[_pick(c, ("path", "name")) for c in i["categories"]]) for i in doc["items"]]}


def reduce_detail(exchange: str, body: str) -> str:
    if exchange == "binance":
        doc = json.loads(body)
        return json.dumps({"code": doc["code"], "data": _pick(doc["data"], (
            "code", "title", "publishDate", "firstCatalogId", "firstCatalogName", "secondCatalogId",
            "thirdCatalogId", "body"))}, ensure_ascii=False)
    if exchange == "okx":
        state = re.search(r'<script[^>]*\bid="appState"[^>]*>(.*?)</script>', body, re.S).group(1)
        post = json.loads(state)["appContext"]["serverSideProps"]["currentPost"]
        reduced = {"appContext": {"serverSideProps": {"currentPost": dict(
            _pick(post, ("slug", "title", "publishTime")),
            section=_pick(post["section"], ("slug", "title")))}}}
        article = re.search(r"<article\b[^>]*>.*?</article>", body, re.S).group(0)
        return ('<!DOCTYPE html><html lang="en"><head><script id="appState" type="application/json">'
                + json.dumps(reduced, ensure_ascii=False) + "</script></head><body>" + article + "</body></html>")
    doc = json.loads(body)
    data = doc["data"]
    return json.dumps({"code": doc["code"], "success": doc["success"], "data": dict(
        _pick(data, ("title", "path", "publish_ts", "publish_at", "content")),
        categories=[_pick(c, ("path", "name")) for c in data["categories"]])}, ensure_ascii=False)


def main() -> None:
    dw = _load_contract()
    raw_manifest = json.loads((OUT / "raw_manifest.json").read_text())
    fixtures = {}
    for name, meta in raw_manifest["captures"].items():
        exchange = name.split("_")[0]
        status = meta["status"]
        raw = (RAW / name).read_bytes().decode("utf-8")
        if "_market_" in name:
            base, quote = re.match(r".*_market_([A-Z0-9]+?)-?(USDT)\.json$", name).groups()
            reduced = json.dumps(reduce_market(exchange, json.loads(raw)), ensure_ascii=False)
            same = dw._market_state(exchange, base, quote, status, raw) == \
                dw._market_state(exchange, base, quote, status, reduced)
        elif "_list" in name:
            reduced = json.dumps(reduce_list(exchange, json.loads(raw)), ensure_ascii=False)
            same = dw._parse_list(exchange, status, raw) == dw._parse_list(exchange, status, reduced)
        else:
            ref = name.split("_d_", 1)[1].rsplit(".", 1)[0]
            # KuCoin refs are paths ("/en-..."); OKX refs are "help/<slug>" or
            # "en-us/help/<slug>" (slugs never contain "_").
            ref = {"kucoin": "/" + ref, "okx": ref.replace("_", "/")}.get(exchange, ref)
            reduced = reduce_detail(exchange, raw)
            parsed = dw._parse_detail(exchange, ref, status, raw)
            same = parsed is not None and parsed == dw._parse_detail(exchange, ref, status, reduced)
        assert same, f"reduced fixture parses differently from the raw capture: {name}"
        (OUT / name).write_text(reduced)
        fixtures[name] = {"url": meta["url"], "status": status, "raw_bytes": meta["bytes"],
                          "raw_sha256": meta["sha256"], "fixture_bytes": len(reduced.encode("utf-8"))}
        if meta.get("source") == "studio-next":
            fixtures[name].update(source="studio-next", probe_contract=meta["probe_contract"],
                                  probe_tx=meta["probe_tx"])
        print(f"{meta['bytes']:>7} -> {len(reduced.encode('utf-8')):>6}  {name}")
    (OUT / "manifest.json").write_text(json.dumps(
        {"captured_at": raw_manifest["captured_at"], "fixtures": fixtures}, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
