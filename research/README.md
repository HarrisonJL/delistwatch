# Research: what GenVM can read from each exchange

Before building, every source DelistWatch might use was fetched **from inside GenVM on Studio Next**, not from a laptop, because exchanges answer differently by region and client. Two throwaway probe contracts did the fetching:

- `0xd5145AE06f6392C522501B0ea3de34047A641359`: `probe_get(url, ua)` stores status, length, SHA-256 and the first 700 bytes.
- `0x41579FcC264faD9FaAB29FbD831A42A11E337E41`: `body_of(url)` stores the full body, up to 30,000 characters.

Results are readable from each contract's `get_results()`; transaction hashes are below.

## Market-status APIs

| Exchange | URL (pair STORJ/USDT) | From GenVM | Used |
|---|---|---|---|
| Binance | `api.binance.com/api/v3/exchangeInfo?symbol=STORJUSDT` | **451**, "restricted location" | no |
| Binance | `data-api.binance.vision/api/v3/exchangeInfo?symbol=STORJUSDT` (Binance's official public market-data mirror) | 200, `status: BREAK` | **yes** |
| Binance | same mirror, `symbol=NOPEXUSDT` (`0x8447a6e8cf884fa3e5edfb4c86f9e48b426f52007606ee970220c758be6079e5`) | 400, `code -1121 Invalid symbol` | parsed as not listed |
| OKX | `www.okx.com/api/v5/public/instruments?instType=SPOT&instId=STORJ-USDT` | 200, `code 51001` (doesn't exist) | **yes** |
| OKX | `…/instruments?instType=SPOT` in full (`0x146b6e90bd79c2cc56acdf397ce5885489b285b116717c4183de63bddb6bbef1`) | 1,234,359 bytes: the same length as fetched outside the US, and the first 30,000 characters (all that was stored) identical | evidence the market API isn't regional |
| KuCoin | `api.kucoin.com/api/v2/symbols/STORJ-USDT` | 200, `enableTrading: true` | **yes** |
| Bybit | `api.bybit.com/v5/market/instruments-info?category=spot&symbol=STORJUSDT` | **403**, CloudFront country block | no, so Bybit isn't supported |

## Delisting announcements

| Exchange | Source | From GenVM | Used |
|---|---|---|---|
| Binance | CMS list API, catalog 161 "Delisting" (`0x56d17842069519729a5b0cf4e19c324ce5b1d5eadda44ec35aee46cb8e0a78b0`) | 200, JSON | **yes** (page size 50) |
| Binance | CMS article detail API (`0x988510c64cbcc619b5415f8c97a91f8d20e1e72ea8244eb41ceb78e5df5af410`) | 200, JSON; body is a node tree | **yes** |
| OKX | help-centre section page, HTML (`0xbef2bd89a5af6e2d57a8a0425ee6108991977c01db557f3461c62a8576e607cf`) | 200, but 80,181 bytes vs 97,223 locally | no: replaced by the API below |
| OKX | `/api/v5/support/announcements?annType=announcements-delistings` (documented public API; `0xdb6cb86473d4033b0c70210e8cc6347b3b7f780466d22ea396ae9ce46c6b2292`) | 200, JSON | **yes** |
| OKX | article page `help/<slug>` (`0xf7f56bc5194487f758df0e213db92e43a5bae31c5d928670b69d7ac54b68f69f`, `0x1a1c9e84396c3deaf1ce3e64450c435a919d45f3114532b7cf06e929c6c238bb`) | 200, the `lang="en-us"` page | **yes**: `appState` JSON plus `<article>` |
| KuCoin | announcement page `__NEXT_DATA__` (`0xbee93e1319753c299ada588b9dba8c31f1353e60ddb332eb65b0ff959b610d22`) | 200, but only 10 entries (about 6 weeks) | no: too short for the lookback |
| KuCoin | `/_api/cms/articles?…&category=delistings` (JSON behind KuCoin's own announcement pages; `0x987e89f0091a1a479402666e674a95caa135b2c5d844577d60355639a99c7ea2`) | 200, 50 entries (about 6 months) | **yes** |
| KuCoin | `/_api/cms/articles/<path>` (`0xe4b166d870ec31a4d6ea800a46226106ef2895629115c0a52311666eb0482a8b`) | 200, JSON with HTML `content` | **yes** |
| Bybit | announcements list and article (`0xdc2cbc22874a88d6be186027a479e3176b12528bae07f364fea5dd338ba183fc`, `0x0f852484a14373e53bdc692c2ed16cc0448c42b9507f730c39d2a47b811546e5`) | 200 | no: Bybit's market API is blocked (above) |

## Finding: OKX's help centre is regional, and its market API is not

The first deployment's OKX check failed closed (`UNDETERMINED: announcements_unavailable`; CONTRACT.md, "Superseded deployment"). The full list body GenVM received (`body_of`, tx `0x73b32a8a0c4fdaa85c2b5e18f49da93c506f45504abd5889c0559fc1177b3bc2`) showed why. OKX serves Studio Next's validators its **US** help centre:

- every URL is `https://www.okx.com/en-us/help/<slug>`, where outside the US it is `https://www.okx.com/help/<slug>`;
- 18 entries instead of 20, with no perpetual-futures notices, and "selected USD spot trading pairs" where the global list has the USDⓈ version;
- the article pages are the `en-us` versions, and the STORJ/USDT schedule reads the same in both.

The instruments API, in contrast, returned GenVM a body of exactly the same length (1,234,359 bytes) as outside the US, and its first 30,000 characters (all the probe stored) are identical. The fix keeps the region visible: list URLs may carry a `xx-yy/` prefix, the ref recorded on-chain keeps it (`en-us/help/…`), and the article is fetched from that same URL. That list body is committed as the fixture `okx_list_us.json`, with the probe transaction in `tests/fixtures/manifest.json`. The `en-us` article fixtures, fetched directly from `/en-us/help/<slug>`, reproduce the text digests validators recorded live (CONTRACT.md).

## Why the reader is needed: real titles that a keyword filter gets wrong

From the lists above, on 2026-10-04:

- Titles naming a token, for a product other than spot: "KuCoin Futures Will Delist the ICXUSDT and STORJUSDT Perpetual Contracts…", "KuCoin Earn Will Delist the WAXP Products", "OKX to delist perpetual futures for ICXUSDT", "Binance Will Extend the Monitoring Tag to Include ACT, BLUR, PIVX & QKC".
- Spot delistings whose titles name no token: "Notice of Removal of Spot Trading Pairs - 2026-10-02" (Binance, weekly), "ST: KuCoin Will Delist Multiple Tokens on 2026-09-07" (25 tokens), "KuCoin Will Delist Certain Projects & Their Associated Tokens", "OKX to delist selected USD spot trading pair".
- Pair-level removals: Binance's 2026-09-18 notice removes QNT/USDC and leaves QNT/USDT trading.

Title rules decide only *which* announcements to open. Whether one ends spot trading of a given pair is the reader's call, made with a quote and a date that validators check.
