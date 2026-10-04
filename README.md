# DelistWatch

**Is this token's spot market still trading on this exchange, and has the exchange announced that it will stop?** A GenLayer Intelligent Contract that reads Binance's, OKX's and KuCoin's own market data and delisting announcements and publishes a verdict a lending contract can act on: `TRADING`, `DELISTING_ANNOUNCED`, `NOT_TRADING`, or `UNDETERMINED`.

| | |
|---|---|
| Network | GenLayer Studio Next (chain 61997) |
| DelistWatch | [`0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc`](https://explorer-studio-dev.genlayer.com/address/0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc) |
| CollateralPolicy (consumer) | [`0x0818EAe37BBaEe0A9D64c16b831b0E55315d9FA8`](https://explorer-studio-dev.genlayer.com/address/0x0818EAe37BBaEe0A9D64c16b831b0E55315d9FA8) |
| Live proof | [CONTRACT.md](CONTRACT.md): three exchanges, five real markets, every transaction unanimous, the facts reproduced byte for byte by the test suite |
| Tests | 82 Direct Mode tests on real exchange responses; 46/46 safety mutations killed |

## Why this exists

A lending protocol that accepts a token as collateral depends on being able to sell it. When a major exchange delists the token, that liquidity disappears, often within a week or two of the announcement. The signal exists: every exchange publishes its delistings. But it's buried in a stream of announcements that mostly don't matter to a spot market:

- **"KuCoin Futures Will Delist the ICXUSDT and STORJUSDT Perpetual Contracts"** names STORJ, yet STORJ's spot market on KuCoin keeps trading (live proof: `TRADING`).
- **"Notice of Removal of Spot Trading Pairs - 2026-09-18"** names no token in its title. Its text removes QNT/USDC and leaves QNT/USDT trading.
- **"ST: KuCoin Will Delist Multiple Tokens on 2026-09-07"** names no token in its title. Its text lists 25 tokens.

A keyword filter gets both kinds wrong: it raises false alarms on the first and misses the second and third. The question needs reading, but reading by an LLM isn't something a lending contract should have to trust. DelistWatch confines the LLM to the one question that needs it, and makes every answer checkable.

## How it decides

### 1. "Trading right now" is plain code

Every validator reads the exchange's own public market API for the exact pair (`data-api.binance.vision`, OKX `/api/v5/public/instruments`, KuCoin `/api/v2/symbols`) and parses its status field. A response for a different symbol is never accepted. Binance `BREAK`, an OKX state other than `live`, KuCoin `enableTrading: false`, or "no such pair" all mean `NOT_TRADING`, with no LLM involved. That data outranks any announcement.

### 2. The announcements come from the exchange, and the contract picks which to read

The contract reads each exchange's own delisting list through the exchange's own JSON endpoint (Binance's CMS catalog 161 "Delisting", OKX's `/api/v5/support/announcements?annType=announcements-delistings`, KuCoin's `delistings` category). It builds every URL itself, from tickers restricted to `[A-Z0-9]`. An announcement is opened if it is recent and either:

- its title names the token (as `STORJ`, `STORJUSDT`, `STORJ/USDT` or `(STORJ)`), within the last **60 days**; or
- it is a **generic spot notice**, within the last **21 days**: a title that announces spot removals without naming the tokens ("Notice of Removal of Spot Trading Pairs", "OKX to delist selected USD spot trading pair", "KuCoin Will Delist Certain Projects & Their Associated Tokens"). Titles about futures, margin, loans, Earn, Alpha or copy trading are not generic spot notices.

Each opened page must be the announcement that was asked for (its own code, slug or path must match) and must be filed under the exchange's delisting category. The reader is shown only the announcements whose **text** names the token. If none does, the verdict is `TRADING` without an LLM call (live: Binance BTC/USDT, four notices opened, none names BTC).

Older announcements aren't needed: a delisting announced longer ago has taken effect, and step 1 already sees it.

### 3. The LLM decides one thing and must quote it

Shown those announcements whole, the reader answers: *taken together, do these end spot trading of BASE/QUOTE on this exchange, and if so, on what date?* Its powers are deliberately narrow:

- **It can only move a trading market down**, from `TRADING` to `DELISTING_ANNOUNCED` or `UNDETERMINED`. It can never make a non-trading market look tradeable.
- **A delisting counts only with a verbatim quote and a stated date.** Every fragment of the quote must appear word for word in the announcements, and the effective date must be written there too (as `2026-10-03`, `October 3, 2026` or `3 October 2026`). Every validator checks both against its own copy. A claim that fails either is `UNDETERMINED`, not a published delisting.
- **"Doesn't end spot trading" counts only if the reader saw every announcement whole.** Each is shown in full up to 12,000 characters. If one is longer, a "no" can't clear it (`UNDETERMINED`), though a quoted "yes" from its visible part still counts.
- **A passed date while the market still trades is `UNDETERMINED`.** The facts don't add up, so nothing is published as settled.
- **An unreadable answer is never a default "no".** It is `UNDETERMINED`.

### 4. Fail closed

| Verdict | Meaning |
|---|---|
| `TRADING` | The pair trades now, and no announcement the contract read ends its spot trading. |
| `DELISTING_ANNOUNCED` | The pair trades now, but the exchange has announced the end of its spot trading. A quoted, dated finding that every validator's reader shares. Carries the effective date. |
| `NOT_TRADING` | The exchange's market data says the pair is halted, suspended or not listed. |
| `UNDETERMINED` | Something couldn't be settled: the market API, the announcement list or an announcement was unreadable; the list doesn't reach back over the lookback; more announcements matched than one reading covers (6); an announcement was too long to clear; or the reader couldn't support its answer. The reasons are recorded. |

`is_tradeable(watch_id, max_age_seconds)` is true only for a fresh `TRADING`.

## Equivalence principle

A custom leader/validator pair (`gl.vm.run_nondet`):

- **Deterministic facts: exact agreement.** Each validator re-fetches and must derive identical facts: market status, every list entry scanned, every announcement opened (readable, category, names the token, complete), and, through a SHA-256 digest, the exact text the reader is shown. The record stores previews and the digests. The full text is reproducible from the exchange.
- **The reader: agreement on the decision a lending protocol acts on.** Each validator runs its own reader and must reach the same verdict and the same effective date. The leader's quote and date must also be grounded in each validator's own copy, and the leader's `grounded` flag must be what the validator computes.
- **The verdict is never taken from the leader.** It is recomputed from the agreed facts and reading.

The consensus-boundary tests (`tests/test_delist_watch.py`, section 5) show validators rejecting: a leader hiding a delisting, one claiming a delisting its own reader doesn't find, a quote not in the validator's copy, a different effective date, a reading of announcements that never name the token, tampered facts or digest, and malformed readings.

## What this proves, and what it doesn't

| It proves | It does not prove |
|---|---|
| What the exchange's own market API said about this exact pair, at check time | That the market is liquid. A trading pair can still be thin |
| That a committee of validators agreed on which of the exchange's own delisting announcements were read, and on the exact text | Anything about other exchanges, or other products on this one (futures, margin, Earn) |
| That a published delisting is quoted and dated from the exchange's own words | Anything announced only outside the exchange's delisting category, or before the lookback window |
| | That the exchange won't postpone or change its schedule. A new check reads any update |

This is not investment advice; it's a signal a lending contract can wire in and a person can audit.

## Using it from another contract

`contracts/collateral_policy.py` is a deployed, working example: a loan against a token reverts unless DelistWatch's latest check of its market is a fresh `TRADING`, and only up to the policy's loan-to-value ratio.

```python
watch = gl.contract.get_at(self.delistwatch_address)
if not watch.view().is_tradeable(watch_id, self.max_age_seconds):
    raise gl.vm.UserError("collateral refused")
```

Live: loans against STORJ on KuCoin and BTC on Binance succeeded. Loans against STORJ on OKX and Binance reverted with `collateral 'okx-storj' refused: …` (CONTRACT.md).

| Method | |
|---|---|
| `register_watch(watch_id, exchange, base, quote, label)` | Permissionless and immutable. `exchange` is `binance`, `okx` or `kucoin`; tickers are `[A-Z0-9]{1,15}`. |
| `check(watch_id)` | Permissionless: a fresh read of the market and the announcements. |
| `is_tradeable(watch_id, max_age_seconds)` | The consumer view. |
| `latest_check` / `latest_verdict` / `get_check` / `get_checks(offset, limit)` | Full history: verdict, reasons, effective date, facts, reading. |
| `get_watch` / `list_watches` / `get_rules` / `get_state` | |

## Testing

```bash
python3 -m venv .venv && .venv/bin/pip install genlayer-test==0.29.2 genvm-linter==0.11.0 pytest
.venv/bin/pytest tests -q                     # 82 tests
python3 scripts/mutation_check.py             # 46/46 mutations killed
.venv/bin/genvm-lint check contracts/delist_watch.py
```

- **Real exchange responses.** The fixtures are Binance's, OKX's and KuCoin's own responses, captured on 2026-10-04 (`scripts/capture_raw.py`; OKX's en-us announcement list was captured through GenVM itself, `research/`). They are reduced to the fields the contract reads (`scripts/build_fixtures.py`), and the build fails unless the contract's parsers return exactly the same result for every reduced fixture as for the raw capture. Sources and SHA-256s are in `tests/fixtures/manifest.json`. Announcement text is never edited.
- **The fixtures reproduce the live record.** For all five live watches, replaying the fixtures in Direct Mode yields facts identical to what the validators agreed on-chain, including the digest of every announcement text shown to the reader (`test_fixtures_reproduce_the_facts_validators_agreed_on_live`).
- **Real cases are the test cases.** These include the KuCoin futures trap, Binance's spot-pair notices (QNT/USDC removed, QNT/USDT not), OKX's STORJ schedule, Binance's STORJ token delisting, and KuCoin's "ST" delisting read together with an Earn-only notice for the same token.
- **Synthetic, and marked as such:** the market API as it stood *before* a delisting (today's real response for a trading pair, with only the tickers changed), and deliberate breakages of real responses: a foreign URL in a list, a page served for the wrong announcement, a stripped category, an over-long announcement.
- **Mutation check.** `tests/mutations.txt` lists 46 deliberate breakages, each removing one safety property; `scripts/mutation_check.py` confirms the suite catches every one.
- CollateralPolicy's cross-contract call can't run in Direct Mode (no glsim hook), so it's proven live instead: allowed loans, refused loans, and an over-limit loan.
- `contracts/*.py` are the tested sources (GenVM v0.2.11). `contracts/*_studio_next.py` are mechanical ports (`scripts/port_to_studio_next.py`), and the on-chain code is byte-identical to them (`studio-next/verify_code.ts`).

## Known limitations

- **Three exchanges.** Bybit's market API refuses Studio Next's validators (HTTP 403, CloudFront country block), and Binance's main API answers 451. DelistWatch uses Binance's official market-data mirror, which serves the same `exchangeInfo` (`research/`).
- **OKX's help centre is regional.** OKX serves Studio Next's validators its **en-us** announcement list and pages. Its market API is not regional (same response size; the first 30,000 characters checked are identical). An OKX delisting published only for another region, such as an EEA-only stablecoin removal, isn't seen. Each record shows which site was read (`en-us/help/...` refs). The first deployment didn't accept those URLs and failed closed (`UNDETERMINED`) until fixed (CONTRACT.md, "Superseded deployment").
- **Lookback windows.** Delistings announced more than 60 days ahead (title naming the token) or 21 days ahead (generic notice) aren't read until the market changes. Exchanges normally give one to two weeks' notice.
- **Single-letter tickers** (`J`, `S`) match more text than intended. That costs `UNDETERMINED`s, not false `TRADING`s.
- **Validators read the exchange at slightly different moments.** If an announcement is published mid-check, validators disagree and the round rotates rather than recording a mixed reading.

## Repository layout

```
contracts/delist_watch.py                tested source (GenVM v0.2.11)
contracts/delist_watch_studio_next.py    deployed port (Studio Next)
contracts/collateral_policy*.py          consumer contract + port
tests/                                   Direct Mode tests, fixtures + manifest, mutations.txt
scripts/                                 capture, fixture build, port, mutation check
studio-next/                             deploy, schema check, live proof (prove.ts, live_proof.json), verify_code.ts
research/                                what GenVM can fetch from each exchange, and the OKX region finding
```
