import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, delimiter } from "node:path";
import { createInterface } from "node:readline";

export type BackendEvent =
  | { type: "ready"; model: string; cwd: string }
  | { type: "done"; cwd: string }
  | { type: "status" | "text" | "error"; text: string }
  | { type: "output"; stream: "stdout" | "stderr"; text: string }
  | { type: "tool"; name: string; arguments: unknown }
  | { type: "result"; name: string; result: unknown }
  | { type: "approval"; id: string; command: string; cwd: string; explanation: string; timeout_ms: number };
export type BackendRequest =
  | { type: "prompt"; text: string }
  | { type: "approval"; id: string; approved: boolean }
  | { type: "cd"; path: string }
  | { type: "cancel" | "reset" | "shutdown" };

export function startBackend(onEvent: (event: BackendEvent) => void, onExit: () => void) {
  const root = fileURLToPath(new URL("../../../", import.meta.url));
  const venvPython = join(root, ".venv/bin/python");
  const python = process.env.SHELL_E_PYTHON || (existsSync(venvPython) ? venvPython : "python3");
  const child = spawn(python, ["-u", "-m", "shell_e.bridge"], {
    stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env, PYTHONPATH: [join(root, "src"), process.env.PYTHONPATH].filter(Boolean).join(delimiter) },
  });
  let closing = false;
  let exited = false;
  const lines = createInterface({ input: child.stdout });
  lines.on("line", line => {
    if (closing) return;
    try { onEvent(JSON.parse(line) as BackendEvent); }
    catch { onEvent({ type: "error", text: "Invalid message from Python backend" }); }
  });
  child.stderr.on("data", data => { if (!closing) onEvent({ type: "error", text: data.toString() }); });
  child.on("error", error => { if (!closing) onEvent({ type: "error", text: error.message }); });
  child.stdin.on("error", error => { if (!closing) onEvent({ type: "error", text: error.message }); });
  child.on("close", () => { exited = true; lines.close(); if (!closing) onExit(); });
  return {
    send(request: BackendRequest) {
      if (!closing && !exited && child.stdin.writable) child.stdin.write(JSON.stringify(request) + "\n");
    },
    close() {
      if (closing) return;
      closing = true;
      child.stdin.end(JSON.stringify({ type: "shutdown" }) + "\n");
      // Python handles SIGTERM by cancelling the agent and cleaning its process group.
      const timer = setTimeout(() => { if (!exited) child.kill("SIGTERM"); }, 1000);
      timer.unref();
      child.once("close", () => clearTimeout(timer));
    },
  };
}
