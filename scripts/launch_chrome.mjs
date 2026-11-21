// Launch full Chromium (automation-evasion flags off) under Xvfb for CDP.
// Usage: node launch_chrome.mjs <display> <user-data-dir> [cdp-port]
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const display = process.argv[2] || ":99";
const userDataDir = process.argv[3] || mkdtempSync(join(homedir(), "chrome-prof-"));
const port = parseInt(process.argv[4] || "9222", 10);
const chrome = `${homedir()}/.cache/ms-playwright/chromium-1200/chrome-linux64/chrome`;

const xvfb = spawn("/usr/bin/Xvfb", [display, "-screen", "0", "1920x1080x24"], {
  stdio: ["ignore", "pipe", "pipe"],
});
xvfb.stderr.on("data", () => {}); // X server chatter is expected

const args = [
  `--user-data-dir=${userDataDir}`,
  `--remote-debugging-port=${port}`,
  "--no-first-run", "--no-default-browser-check",
  "--disable-blink-features=AutomationControlled",
  "--password-store=basic", "--use-mock-keychain",
  "--lang=en-US",
  "--start-maximized",
];
const chromeProc = spawn(chrome, args, {
  env: { ...process.env, DISPLAY: display },
  stdio: ["ignore", "pipe", "pipe"],
  detached: false,
});
let booted = "";
chromeProc.stderr.on("data", (d) => { booted += d.toString(); });
chromeProc.on("exit", (c) => { console.error(`chrome exited rc=${c}`); xvfb.kill(); process.exit(1); });

// Wait for the CDP endpoint to answer.
const deadline = Date.now() + 30000;
while (Date.now() < deadline) {
  try {
    const r = await fetch(`http://127.0.0.1:${port}/json/version`);
    if (r.ok) {
      const v = await r.json();
      console.log(`CDP_READY port=${port} browser=${v.Browser}`);
      console.log(`USER_DATA_DIR=${userDataDir}`);
      console.log(`DISPLAY=${display}`);
      process.exit(0);
    }
  } catch {}
  await new Promise((r) => setTimeout(r, 500));
}
console.error(`CDP never came up. stderr tail:\n${booted.slice(-800)}`);
chromeProc.kill(); xvfb.kill();
process.exit(1);
