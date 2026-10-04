// npx tsx deploy.ts <contract file in ../contracts> [constructor args as JSON]
import * as fs from "fs";
import { client, fees, waitDecided, EXPLORER } from "./lib";

async function main() {
  const file = process.argv[2] ?? "delist_watch_studio_next.py";
  const args = process.argv[3] ? JSON.parse(process.argv[3]) : [];
  const c = client();
  console.log(`Deploying ${file} ${JSON.stringify(args)} as ${c.account.address}`);
  const code = fs.readFileSync(`../contracts/${file}`, "utf-8");
  const hash = await c.deployContract({ code, args, fees: await fees(c) });
  console.log(`Deploy tx: ${hash}`);
  const tx = await waitDecided(c, hash);
  console.log(`Result: ${tx.txExecutionResultName ?? tx.result_name}`);
  console.log(`Contract address: ${tx.to_address ?? tx.recipient}`);
  console.log(`${EXPLORER}/tx/${hash}`);
  process.exit(0);
}
main().catch((e) => {
  console.error(e);
  process.exit(1);
});
