# DelistWatch: deployment and live proof

Everything below is on GenLayer Studio Next (chain 61997), produced by `studio-next/prove.ts` on 2026-10-04 and logged in full (every recorded check, every vote) in [`studio-next/live_proof.json`](studio-next/live_proof.json). Explorer: `https://explorer-studio-dev.genlayer.com/tx/<hash>`.

## Deployments

| Contract | Address | Deploy tx |
|---|---|---|
| DelistWatch | `0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc` | `0x6ace2420cb9a57c6cbca4d8aae1553f757fd01347c64d3ad57881fd0517a1f04` |
| CollateralPolicy (`max_age_seconds` 86400, `ltv_bps` 5000) | `0x0818EAe37BBaEe0A9D64c16b831b0E55315d9FA8` | `0x9b5b34e1d0d66e5b71248543de7eebb374230990c297c7bcfbceb2a4f32ca01a` |

### Verify the deployed source matches this repo

```bash
cd studio-next && npm ci
npx tsx verify_code.ts 0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc delist_watch_studio_next.py
npx tsx verify_code.ts 0x0818EAe37BBaEe0A9D64c16b831b0E55315d9FA8 collateral_policy_studio_next.py
```

| File | SHA-256 | On-chain |
|---|---|---|
| `contracts/delist_watch_studio_next.py` | `65450eb378d26236bad24241c096b4929d8a710b436bad154b65abbf5d17f77b` | identical |
| `contracts/collateral_policy_studio_next.py` | `6e8ea6e030446260b8af2bc3f460fce5d00fd05288dd0303fd67f248049ceb05` | identical |
| `contracts/delist_watch.py` (tested source) | `1a97d1eb6e6093f90665d18b88373f0bf603c1d04316676849f1dd8f3ae00883` | ported mechanically |
| `contracts/collateral_policy.py` (tested source) | `4b6cb82da10d87235e651cdfe8be9a43d62abe701ebc066706c770d5816eaa94` | ported mechanically |

## 1. Registration

| Watch | Exchange / pair | Tx | Result |
|---|---|---|---|
| `kucoin-storj` | KuCoin STORJ/USDT | `0x1bfaca298fd171b148930bc1eba853d777155fada07928c0d2e40d6256dc01eb` | ✓ |
| `okx-storj` | OKX STORJ/USDT | `0xbe4cf3e527136dfb7d823e77ae1b19fad0a08b3b28647320733c2c6e9828605f` | ✓ |
| `binance-storj` | Binance STORJ/USDT | `0x8a756e2c52e344cfbd59f0b61db9d604b547401c86c4d9ed7c1d9cb0ecc14ec0` | ✓ |
| `binance-btc` | Binance BTC/USDT | `0x7796963d5c581d7b40a019f0612e74aafd1b5bf9b57899452f1c2a9365f72c62` | ✓ |
| `okx-btc` | OKX BTC/USDT | `0x1acff24e7c8dad08a99a8fb8b2f2198a04fffd546f5843005faeb992bc740327` | ✓ |
| `bybit-btc` | unsupported exchange | `0xb70f953f0fc9233546c0f1b662ca26642de18a4de486cfd2bcdaa1cee10f8a56` | reverted: `exchange must be one of binance, okx, kucoin` |
| `okx-inject` | base `BTC-USDT&instType=SWAP` | `0x9b2ce72cedce9f62e83196d57f03f27a00a4580d244abb5e234f31fd94b7b1f5` | reverted: `base must be 1-15 characters of A-Z or 0-9` |

The second refusal matters: tickers are spliced into the contract's own API URLs, so a ticker that could add a query parameter (here, switching OKX's instrument type to swaps) never gets in.

## 2. Checks: every verdict path that today's markets offer

All five checks reached consensus with every voting validator agreeing (3 of 5 sampled per round, all `AGREE`).

| Watch | Tx | Verdict | What the validators agreed on |
|---|---|---|---|
| `kucoin-storj` | `0xaeaa61eaeb20e45d959714408a4410d64ae75b8e58f377dfa27a09fae9d97bd6` | **`TRADING`** | Market `enableTrading=true`. One announcement names STORJ: "KuCoin Futures Will Delist the ICXUSDT and STORJUSDT Perpetual Contracts…" (2026-08-23). Every reader: `ends_spot: false`. A futures delisting doesn't end spot trading. |
| `okx-storj` | `0x3d547be4265e8803089dbdc51ad625ffdeb6f5a36f2a72681d3d3ded8306ef8e` | **`NOT_TRADING`** | OKX's instrument API: `51001` (pair doesn't exist). OKX removed STORJ/USDT on 3 Oct. No announcement read, no LLM. |
| `binance-storj` | `0xcef68338a532cc9de154bea74cb4625d910a721cb90efce522148bb9b89102d6` | **`NOT_TRADING`** | Binance `exchangeInfo`: `status=BREAK`. Binance delisted STORJ on 3 Sep. No LLM. |
| `binance-btc` | `0xc5e75e8a93ef51620afd896787cfc1efb08d55e8247b5d502dc4c1888c12671c` | **`TRADING`** | Market `TRADING`. Four generic spot notices from the last 21 days opened and parsed (2026-09-16, 09-22, 09-23, 09-29). None names BTC, so the reader was never called. |
| `okx-btc` | `0xd5f81f61fb44796eb9a790d4c1c9ea00cdfd6e102930a027330be8675e202d7f` | **`TRADING`** | Market `state=live`. Two spot notices opened from OKX's **en-us** help centre (`en-us/help/okx-to-delist-dora-…`, `en-us/help/okx-to-delist-aeon-usd-…`). Neither names BTC, so no LLM. |

**The fixtures reproduce these records exactly.** `test_fixtures_reproduce_the_facts_validators_agreed_on_live` replays the committed fixtures for all five watches. It asserts the resulting facts (market detail, every announcement's ref, date, flags, preview and text digest), verdict, reasons and reading equal what is stored on-chain here. The tests therefore run on the same bytes, as far as the contract reads them, that the validators fetched.

**Paths proven in tests rather than live.** On 2026-10-04 no supported exchange had an announced spot delisting still in the future: the most recent, OKX's STORJ/USDT schedule, took effect on 3 October. So `DELISTING_ANNOUNCED`, and the `UNDETERMINED` paths that need a failing exchange, are proven on real announcements in `tests/test_delist_watch.py`:

- OKX STORJ/USDT as of 25 Sep: `DELISTING_ANNOUNCED`, effective 2026-10-03.
- Binance STORJ/USDT as of 25 Aug: effective 2026-09-03.
- Binance QNT/USDC vs QNT/USDT as of 17 Sep: one ends, one keeps trading.
- KuCoin WAXP/USDT as of 5 Sep: the "ST" notice, read alongside an Earn-only notice.

A new watch with `prove.ts register` / `check` shows the live path the next time an exchange announces one.

## 3. The consumer: CollateralPolicy

`borrow(watch_id, collateral_value, amount)` at a 50% loan-to-value limit, requiring `is_tradeable(watch_id, 86400)`:

| Loan | Tx | Result |
|---|---|---|
| 1000 against 2000 of STORJ on KuCoin | `0x317af46e2be1bf7b0e3d7e998af04861dc360dfd24cc0fbb2ef3eaf36d79db19` | ✓ recorded |
| 1000 against 2000 of STORJ on OKX | `0x65c6ec2ec6b2bb0db4b93cfe057e77789c83f4062a5f88bcad5eaeb3cad62294` | reverted: `collateral 'okx-storj' refused: DelistWatch has no fresh check showing its spot market trading with no announced delisting` |
| 1000 against 2000 of STORJ on Binance | `0x5b3d1dfb60974548efb6432e6d8dbf08b18576004da72074e97c6b597caeca45` | reverted: `collateral 'binance-storj' refused: …` |
| 1001 against 2000 of BTC on Binance | `0xc413efe867294c8df5446baade9073439e664a6a31ca887f9061c058de4bfe5f` | reverted: `amount exceeds the 50% loan-to-value limit` |
| 800 against 2000 of BTC on Binance | `0x9168dfd5b6e9d1a4048515d101cca9a82c0e3b5800c734b494eac612fe83510a` | ✓ recorded |

`get_config()` afterwards: `loan_count: 2`. `is_tradeable(…, 86400)`: true for `kucoin-storj`, `binance-btc` and `okx-btc`; false for `okx-storj` and `binance-storj`. With `max_age_seconds = 1` it is false for all five, because every check is older than a second.

## Superseded deployment

| Contract | Address | Why superseded |
|---|---|---|
| DelistWatch v1 | `0x70Df3c0FC985Ec575B537532B5e86c3cff666754` | Its live check of OKX BTC/USDT (`0xa6c86b1510ef18b846caa6a3ef3f4f06798a086637bfb67f87a1d2471dad2794`) recorded `UNDETERMINED: announcements_unavailable`. |
| CollateralPolicy v1 | `0xE361F0B82217F3e66A23ac448f15BBC7F59e726c` | Pointed at DelistWatch v1. |

What happened: OKX serves Studio Next's validators its US help centre, and every list entry's URL is `https://www.okx.com/en-us/help/<slug>`. v1 accepted only `https://www.okx.com/help/<slug>` and, by design, treats one unrecognised entry as an unreadable list. It therefore failed closed rather than reading an unverified list. The bytes the validators received were captured through GenVM (`research/README.md`). The fix accepts a region prefix and keeps it in each recorded ref. The en-us list is now a test fixture, and the v2 OKX check above reads it. v1's full log: [`studio-next/live_proof_superseded_v1.json`](studio-next/live_proof_superseded_v1.json). Its Binance and KuCoin checks reached the same verdicts as v2.
