#!/usr/bin/env node
/**
 * cg-session.mjs — renew the Coinglass web session (CG_SESSION) used by the
 * Model 1/2/3 liquidation-heatmap surface.
 *
 * The token is a long-lived login accessToken (the page keeps its `obe`
 * cookie for 180 days); renew it when heatmap calls start returning
 * 40000-with-session ("session token rejected").
 *
 * Usage:
 *   CG_USER=you@example.com CG_PASS=... node scripts/cg-session.mjs
 *   (credentials via env only — never on the command line, never stored)
 *
 * Writes CG_SESSION into .env (gitignored) and prints next steps.
 */
import { execFileSync } from "child_process";
import fs from "fs";
import os from "os";
import path from "path";

const ROOT = path.resolve(import.meta.dirname, "..");
const ENV = path.join(ROOT, ".env");
const TOKEN_FILE = path.join(os.tmpdir(), "cg_session_token.txt");

if (!process.env.CG_USER || !process.env.CG_PASS) {
  console.error("usage: CG_USER=you@example.com CG_PASS=... node scripts/cg-session.mjs");
  process.exit(2);
}

execFileSync("node", [path.join(ROOT, "scripts/research/cg_login.mjs"), TOKEN_FILE], {
  stdio: "inherit",
  env: process.env,
});

const token = fs.readFileSync(TOKEN_FILE, "utf8").trim();
if (!token || token.length < 20) {
  console.error("login did not produce a token — see output above");
  process.exit(1);
}

let env = fs.existsSync(ENV) ? fs.readFileSync(ENV, "utf8") : "";
if (/^CG_SESSION=.*$/m.test(env)) {
  env = env.replace(/^CG_SESSION=.*$/m, `CG_SESSION=${token}`);
} else {
  env += `\n# Coinglass web session (obe token) — unlocks Model 1/2/3 heatmaps beyond the anonymous BTC 24h view\nCG_SESSION=${token}\n`;
}
fs.writeFileSync(ENV, env, { mode: 0o600 });
console.log(`\nCG_SESSION updated in .env (${token.length} chars).`);
console.log("Restart the terminal (npm run dev / npm start) to pick it up, then verify:");
console.log("  curl 'http://localhost:3000/api/cg/stopmap?sym=XAU&model=1&mode=coin&range=3d'");
