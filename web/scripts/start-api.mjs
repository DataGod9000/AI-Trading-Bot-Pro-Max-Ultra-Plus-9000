#!/usr/bin/env node
/**
 * Start btc-paper-api from the repo root (parent of web/) so DATABASE_PATH and .env resolve.
 * If something already serves FastAPI docs on 8000, skip starting a second server (avoids EADDRINUSE).
 */
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..", "..");
const win = process.platform === "win32";
const venvBin = path.join(root, ".venv", win ? "Scripts" : "bin");
const apiCli = win ? path.join(venvBin, "btc-paper-api.exe") : path.join(venvBin, "btc-paper-api");
const python = win ? path.join(venvBin, "python.exe") : path.join(venvBin, "python");

const PROBE_URL = "http://127.0.0.1:8000/openapi.json";
const PROBE_MS = 2500;

async function apiAlreadyListening() {
  try {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), PROBE_MS);
    const res = await fetch(PROBE_URL, { signal: ac.signal });
    clearTimeout(t);
    return res.ok;
  } catch {
    return false;
  }
}

function run(cmd, args) {
  const child = spawn(cmd, args, { cwd: root, stdio: "inherit", shell: false });
  child.on("exit", (code, signal) => {
    if (signal) {
      process.exit(1);
    }
    process.exit(code ?? 0);
  });
}

async function main() {
  if (!fs.existsSync(apiCli) && !fs.existsSync(python)) {
    console.error(
      "[start-api] No venv at .venv next to the web/ folder.\n" +
        "  From repo root: python3 -m venv .venv && source .venv/bin/activate && pip install -e '.[api]'",
    );
    process.exit(1);
  }

  if (await apiAlreadyListening()) {
    console.log(
      "[start-api] Port 8000 already has an API (/openapi.json OK). Not starting another btc-paper-api.",
    );
    console.log(
      "[start-api] If new routes 404 (e.g. /api/news/analytics), stop that process and restart so code reloads.",
    );
    process.exit(0);
  }

  if (fs.existsSync(apiCli)) {
    run(apiCli, []);
  } else {
    run(python, ["-m", "uvicorn", "btc_paper.api_server:app", "--host", "127.0.0.1", "--port", "8000"]);
  }
}

main().catch((err) => {
  console.error("[start-api]", err);
  process.exit(1);
});
