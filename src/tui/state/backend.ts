import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, delimiter } from "node:path";
import { createInterface } from "node:readline";

type BunPipe = {
  write(data: string): number;
  flush(): Promise<void> | void;
  end(data?: string): Promise<void> | void;
};
type BunProcess = {
  stdin: BunPipe;
  stdout: ReadableStream<Uint8Array>;
  stderr: ReadableStream<Uint8Array>;
  exited: Promise<number>;
  kill(signal?: string): void;
};
type BunRuntime = { spawn(command: string[], options: Record<string, unknown>): BunProcess };

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

export function startBackend(onEvent: (event: BackendEvent) => void, onExit: (code: number | null, signal: NodeJS.Signals | null) => void) {
  const root = fileURLToPath(new URL("../../../", import.meta.url));
  const venvPython = join(root, ".venv/bin/python");
  const python = process.env.SHELL_E_PYTHON || (existsSync(venvPython) ? venvPython : "python3");
  const env = { ...process.env, PYTHONPATH: [join(root, "src"), process.env.PYTHONPATH].filter(Boolean).join(delimiter) };
  const bun = (globalThis as typeof globalThis & { Bun?: BunRuntime }).Bun;
  let closing = false;
  let exited = false;
  const emitLine = (line: string) => {
    if (closing) return;
    let event: BackendEvent;
    try { event = JSON.parse(line) as BackendEvent; }
    catch { onEvent({ type: "error", text: `Invalid JSON from Python backend: ${line.slice(0, 200)}` }); return; }
    try { onEvent(event); }
    catch (error) { onEvent({ type: "error", text: `TUI event handler failed: ${String(error)}` }); }
  };
  const processExited = (code: number | null, signal: NodeJS.Signals | null) => {
    exited = true;
    if (!closing) onExit(code, signal);
  };
  let write: (line: string) => void;
  let end: (line: string) => void;
  let kill: () => void;
  let child: ReturnType<typeof spawn> | BunProcess;
  let lines: ReturnType<typeof createInterface> | undefined;
  if (bun) {
    // Bun's native FileSink keeps stdin open for the full multi-message session.
    // Its Node child_process compatibility layer closed the pipe after a write.
    const process = bun.spawn([python, "-u", "-m", "shell_e.bridge"], {
      stdin: "pipe", stdout: "pipe", stderr: "pipe", env,
    });
    child = process;
    write = line => { process.stdin.write(line); void process.stdin.flush(); };
    end = line => { void process.stdin.end(line); };
    kill = () => process.kill("SIGTERM");
    const readLines = async (stream: ReadableStream<Uint8Array>, onLine: (line: string) => void) => {
      const decoder = new TextDecoder();
      let buffer = "";
      for await (const chunk of stream) {
        buffer += decoder.decode(chunk, { stream: true });
        const complete = buffer.split("\n");
        buffer = complete.pop()!;
        for (const line of complete) onLine(line);
      }
      buffer += decoder.decode();
      if (buffer) onLine(buffer);
    };
    void readLines(process.stdout, emitLine).catch(error => {
      if (!closing) onEvent({ type: "error", text: `Python stdout failed: ${error.message}` });
    });
    void readLines(process.stderr, line => {
      if (!closing && line) onEvent({ type: "error", text: line });
    }).catch(error => {
      if (!closing) onEvent({ type: "error", text: `Python stderr failed: ${error.message}` });
    });
    void process.exited.then(code => processExited(code, null));
  } else {
    const nodeProcess = spawn(python, ["-u", "-m", "shell_e.bridge"], {
      stdio: ["pipe", "pipe", "pipe"], env,
    });
    child = nodeProcess;
    lines = createInterface({ input: nodeProcess.stdout });
    lines.on("line", emitLine);
    nodeProcess.stderr.on("data", data => { if (!closing) onEvent({ type: "error", text: data.toString() }); });
    nodeProcess.on("error", error => { if (!closing) onEvent({ type: "error", text: error.message }); });
    nodeProcess.stdin.on("error", error => { if (!closing) onEvent({ type: "error", text: error.message }); });
    nodeProcess.on("close", (code, signal) => {
      lines?.close();
      processExited(code, signal);
    });
    write = line => nodeProcess.stdin.write(line);
    end = line => nodeProcess.stdin.end(line);
    kill = () => nodeProcess.kill("SIGTERM");
  }
  return {
    send(request: BackendRequest) {
      if (!closing && !exited) write(JSON.stringify(request) + "\n");
    },
    close() {
      if (closing) return;
      closing = true;
      end(JSON.stringify({ type: "shutdown" }) + "\n");
      // Python handles SIGTERM by cancelling the agent and cleaning its process group.
      const timer = setTimeout(() => { if (!exited) kill(); }, 1000);
      timer.unref();
      if (bun) void (child as BunProcess).exited.then(() => clearTimeout(timer));
      else (child as ReturnType<typeof spawn>).once("close", () => clearTimeout(timer));
    },
  };
}
