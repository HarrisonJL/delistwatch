// Reproducible live proof for DelistWatch + CollateralPolicy. Every step's
// tx hash, result and the contract's recorded output are appended to
// live_proof.json - the source for CONTRACT.md's tables.
//
//   npx tsx prove.ts <delistwatch address> <collateralpolicy address> <step>
//   steps: register | refuse | check | borrow | read   (optional 4th arg: one watch_id)
import * as fs from "fs";
import { client, readClient, write, safeJson } from "./lib";

const WATCHES: [string, string, string, string, string][] = [
  ["kucoin-storj", "kucoin", "STORJ", "USDT", "STORJ/USDT on KuCoin (its STORJ futures were delisted in August)"],
  ["okx-storj", "okx", "STORJ", "USDT", "STORJ/USDT on OKX (delisting scheduled 3 Oct 2026)"],
  ["binance-storj", "binance", "STORJ", "USDT", "STORJ/USDT on Binance (delisting scheduled 3 Sep 2026)"],
  ["binance-btc", "binance", "BTC", "USDT", "BTC/USDT on Binance"],
  ["okx-btc", "okx", "BTC", "USDT", "BTC/USDT on OKX"],
];

function log(entry: Record<string, unknown>) {
  const all = fs.existsSync("live_proof.json") ? JSON.parse(fs.readFileSync("live_proof.json", "utf-8")) : [];
  all.push(entry);
  fs.writeFileSync("live_proof.json", JSON.stringify(all, null, 1));
}

async function main() {
  const [dw, cp, step, only] = process.argv.slice(2);
  const watches = WATCHES.filter(([id]) => !only || id === only);
  const c = client();
  const r = readClient();
  const votes = (tx: any) => tx.last_round?.validator_votes_name ?? [];

  if (step === "register") {
    for (const [id, exchange, base, quote, label] of watches) {
      const { hash, tx } = await write(c, dw, "register_watch", [id, exchange, base, quote, label]);
      const w = JSON.parse(safeJson(await r.readContract({ address: dw, functionName: "get_watch", args: [id] })));
      log({ step: "register", watch_id: id, tx: hash, result: tx.txExecutionResultName, votes: votes(tx), watch: w });
    }
  } else if (step === "refuse") {
    // Registration builds URLs from the tickers, so anything that could
    // alter a URL - or an exchange it has no reader for - must revert.
    for (const args of [["bybit-btc", "bybit", "BTC", "USDT", "unsupported exchange"],
                        ["okx-inject", "okx", "BTC-USDT&instType=SWAP", "USDT", "ticker injecting a query parameter"]]) {
      const { hash, tx } = await write(c, dw, "register_watch", args);
      log({ step: "refuse", watch_id: args[0], args, tx: hash, result: tx.txExecutionResultName, votes: votes(tx) });
    }
  } else if (step === "check") {
    for (const [id] of watches) {
      const { hash, tx } = await write(c, dw, "check", [id]);
      const chk = JSON.parse(safeJson(await r.readContract({ address: dw, functionName: "latest_check", args: [id] })));
      log({ step: "check", watch_id: id, tx: hash, result: tx.txExecutionResultName, votes: votes(tx), check: chk });
      const f = chk.facts ?? {};
      console.log(`  ${id}: ${chk.verdict} ${safeJson(chk.reasons)} market=${f.market_state}/${f.market_detail}`);
      for (const a of f.announcements ?? []) {
        console.log(`     ${a.date} names_token=${a.names_token} complete=${a.complete} | ${a.title}`);
      }
      console.log(`     reading: ${safeJson(chk.reading)}`);
    }
  } else if (step === "borrow") {
    const loans: [string, number, number][] = [
      ["kucoin-storj", 2000, 1000],  // trading: allowed at 50% LTV
      ["okx-storj", 2000, 1000],     // not trading: refused
      ["binance-storj", 2000, 1000], // not trading: refused
      ["binance-btc", 2000, 1001],   // over the LTV limit: refused before DelistWatch is asked
      ["binance-btc", 2000, 800],    // trading: allowed
    ];
    for (const [id, collateral, amount] of loans) {
      const { hash, tx } = await write(c, cp, "borrow", [id, collateral, amount]);
      const total = await r.readContract({ address: cp, functionName: "total_for", args: [id] });
      log({ step: "borrow", watch_id: id, collateral_value: collateral, amount, tx: hash,
            result: tx.txExecutionResultName, votes: votes(tx), total_after: String(total) });
      console.log(`  borrow(${id}, ${collateral}, ${amount}) -> ${tx.txExecutionResultName}, total now ${total}`);
    }
  } else if (step === "read") {
    for (const [id] of WATCHES) {
      for (const maxAge of [86400, 1]) {
        const ok = await r.readContract({ address: dw, functionName: "is_tradeable", args: [id, maxAge] });
        console.log(`  is_tradeable(${id}, ${maxAge}) = ${ok}`);
        log({ step: "read", call: `is_tradeable(${id}, ${maxAge})`, value: ok });
      }
    }
    console.log("  CollateralPolicy config:", safeJson(await r.readContract({ address: cp, functionName: "get_config", args: [] })));
  }
  process.exit(0);
}

main().catch((e) => {
  console.error(e?.shortMessage ?? e?.message ?? e);
  process.exit(1);
});
