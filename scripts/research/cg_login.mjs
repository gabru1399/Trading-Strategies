#!/usr/bin/env node
/**
 * cg_login.mjs — authenticate against Coinglass and capture the session
 * token. NEVER prints or stores the password; writes ONLY the resulting
 * opaque session token to the path given as argv[2] (or prints code info
 * to stdout). Credentials are passed via env CG_USER / CG_PASS to keep
 * them out of ps listings.
 *
 * Flow (mined from the live page chunks, 2026-11-22):
 *   1. POST https://capi.coinglass.com/coin-community/api/user/login
 *      form: { mailAddress, password }  → data.accessToken
 *   2. POST https://fapi.coinglass.com/coin-community/api/user/web/session
 *      headers: { obe: accessToken }  → session bound; also read Set-Cookie.
 *   Session cookie format: obe=s_[0-9a-f]{32} (Max-Age 180d)
 */
import crypto from "crypto";
import fs from "fs";

const STATIC_KEY = Buffer.from("1f68efd73f8d4921acc0dead41dd39bc", "utf8");
const TOTP_SECRET_B32 = "I65VU7K5ZQL7WB4E";

function base32Decode(s) {
  const a = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = 0, value = 0; const out = [];
  for (const ch of s.toUpperCase().replace(/=+$/, "")) {
    const idx = a.indexOf(ch); if (idx === -1) continue;
    value = (value << 5) | idx; bits += 5;
    if (bits >= 8) { out.push((value >>> (bits - 8)) & 0xff); bits -= 8; }
  }
  return Buffer.from(out);
}
function totp(t) {
  const key = base32Decode(TOTP_SECRET_B32);
  const counter = Buffer.alloc(8); counter.writeUInt32BE(Math.floor(t / 30), 4);
  const d = crypto.createHmac("sha1", key).update(counter).digest();
  const off = d[d.length - 1] & 0x0f;
  return String((d.readUInt32BE(off) & 0x7fffffff) % 1000000).padStart(6, "0");
}
function makeObeToken() {
  const secs = Math.floor(Date.now() / 1000);
  const cipher = crypto.createCipheriv("aes-256-ecb", STATIC_KEY, null);
  return Buffer.concat([cipher.update(Buffer.from(`${secs},${totp(secs)}`, "utf8")), cipher.final()]).toString("base64");
}

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";
const BASE_HEADERS = {
  "user-agent": UA, accept: "*/*", "accept-language": "en-US,en;q=0.9",
  origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/",
};

const outPath = process.argv[2];
const user = process.env.CG_USER;
const pass = process.env.CG_PASS;
if (!user || !pass || !outPath) {
  console.error("usage: CG_USER=... CG_PASS=... node cg_login.mjs <token-out-path>");
  process.exit(2);
}

// 1. login
const loginRes = await fetch("https://capi.coinglass.com/coin-community/api/user/login", {
  method: "POST",
  headers: { ...BASE_HEADERS, "content-type": "application/x-www-form-urlencoded", obe: makeObeToken() },
  body: new URLSearchParams({ mailAddress: user, password: pass }).toString(),
  signal: AbortSignal.timeout(20000),
});
const setCookie = loginRes.headers.getSetCookie?.() ?? [];
const loginJson = await loginRes.json().catch(() => null);
if (!loginJson || loginJson.code !== "0") {
  console.error(`login failed: HTTP ${loginRes.status} code=${loginJson?.code ?? "?"} msg=${String(loginJson?.msg ?? "").slice(0, 120)}`);
  process.exit(1);
}
const accessToken = loginJson.data?.accessToken;
if (!accessToken) {
  console.error("login ok but no accessToken in payload — dumping key names only:",
    Object.keys(loginJson.data ?? {}).join(","));
  process.exit(1);
}
console.error(`login OK (code 0) — email: ${loginJson.data?.userInfo?.email ?? user?.email ?? "(n/a)"}`);

// 2. bind session (fapi web session) — capture the obe cookie if set server-side
const sessRes = await fetch("https://fapi.coinglass.com/coin-community/api/user/web/session", {
  method: "POST",
  headers: { ...BASE_HEADERS, obe: accessToken },
  credentials: "include",
  signal: AbortSignal.timeout(20000),
});
const sessCookies = sessRes.headers.getSetCookie?.() ?? [];
const sessJson = await sessRes.json().catch(() => null);
console.error(`session bind: HTTP ${sessRes.status} success=${sessJson?.success} cookies=${sessCookies.length}`);

// pick the session token: prefer an obe=s_... cookie, else the accessToken
let token = null;
for (const c of [...sessCookies, ...setCookie]) {
  const m = /(?:^|;\s*)obe=([^;]+)/.exec(c);
  if (m) { token = decodeURIComponent(m[1]); break; }
}
if (!token) token = accessToken;

// sanity: token format check (page expects s_[0-9a-f]{32} in the cookie, but
// accessToken format may differ — record what we got)
const fmt = /^s_[0-9a-f]{32}$/.test(token) ? "s_32hex" : token.slice(0, 2) === "s_" ? "s_other" : "other";
fs.writeFileSync(outPath, token, { mode: 0o600 });
console.error(`token captured (${fmt}, ${token.length} chars) -> ${outPath}`);
