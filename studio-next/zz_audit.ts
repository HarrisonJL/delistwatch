import * as crypto from "crypto";
import * as fs from "fs";
import { readClient } from "./lib";
const R = "/Users/harrison/Documents/Claude scripts/";
const PAIRS: [string, string, string, boolean][] = [
  // [repo, address, port file, expected identical]
  ["auditscope", "0x3B3c8317f24e394A24520D5f382E95bdb6f2be40", "auditscope/contracts/auditscope_studio_next.py", true],
  ["auditscope", "0xc9049928572eB42370672fb88989482268bb604d", "auditscope/contracts/listing_gate_studio_next.py", true],
  ["auditscope", "0xe7fc2ed2c909A2f3C22662C62bCd895724F38504", "auditscope/contracts/auditscope_studio_next.py", false],
  ["auditscope", "0x102fb8495D68c68317422A62519365b1687A15dc", "auditscope/contracts/auditscope_studio_next.py", false],
  ["quotekeeper", "0x1A0A3594CDB6b650D1e417269BC64152B87B503d", "quotekeeper/contracts/quotekeeper_studio_next.py", true],
  ["quotekeeper", "0x46bc8b6670146F902441248F74dc95c106285E3d", "quotekeeper/contracts/retainer_consumer_studio_next.py", true],
  ["quotekeeper", "0x873a571f866575DD92dA7A3E89CB0ae2FC65830C", "quotekeeper/contracts/retainer_consumer_studio_next.py", true],
  ["entitystanding", "0xC332c97876643E5037F5a8069Eb92b442c70ae49", "entitystanding/contracts/entity_standing_studio_next.py", true],
  ["licencecheck", "0x301740e01AB6b7538B9078D9ec98914540b4B91F", "licencecheck/contracts/licence_check_studio_next.py", true],
  ["termsshift", "0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69", "termsshift/contracts/terms_shift_studio_next.py", true],
  ["termsshift", "0x5923e852A081737Fee943697289E8b37e7C4B541", "termsshift/contracts/treasury_policy_studio_next.py", true],
  ["delistwatch", "0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc", "delistwatch/contracts/delist_watch_studio_next.py", true],
  ["delistwatch", "0x0818EAe37BBaEe0A9D64c16b831b0E55315d9FA8", "delistwatch/contracts/collateral_policy_studio_next.py", true],
  ["kybdesk", "0xc9C8Dd8Fe79Ae433169A9Fb6cd1eA1E6069822fF", "kybdesk/contracts/kyb_desk_studio_next.py", true],
  ["kybdesk", "0xf97448d11167F5c05043e97307325A8aa76121E1", "kybdesk/contracts/onboarding_gate_studio_next.py", true],
  ["passportmap", "0x170E181A241F8D5909E72d17e2f9D3D027fcA747", "passportmap/contracts/passport_map_studio_next.py", true],
  ["passportmap", "0x75e6846612A26a4D76BE0766b5ED7b8141c18D68", "passportmap/contracts/listing_gate_studio_next.py", true],
];
const sha = (s: string) => crypto.createHash("sha256").update(s).digest("hex");
(async () => {
  const c = readClient();
  let bad = 0;
  for (const [repo, address, file, expected] of PAIRS) {
    await new Promise((r) => setTimeout(r, 2200));
    let onchain: any = await c.getContractCode(address);
    if (typeof onchain !== "string") onchain = Buffer.from(onchain).toString("utf-8");
    const local = fs.readFileSync(R + file, "utf-8");
    const same = onchain === local;
    const ok = same === expected;
    if (!ok) bad++;
    console.log(`${ok ? "OK   " : "FAIL "} ${repo.padEnd(15)} ${address.slice(0, 10)}… ${same ? "IDENTICAL" : "DIFFERENT"}${expected ? "" : " (expected: superseded)"} ${sha(onchain).slice(0, 12)} vs ${sha(local).slice(0, 12)} ${file.split("/").pop()}`);
  }
  console.log(bad ? `${bad} MISMATCH(ES)` : "ALL PARITY CHECKS PASS");
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.log("ERR", e?.message); process.exit(2); });
