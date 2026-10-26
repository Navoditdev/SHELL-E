import { createCliRenderer, BoxRenderable, TextRenderable, InputRenderable,
  InputRenderableEvents, ScrollBoxRenderable } from "@opentui/core";
import { startBackend, type BackendEvent } from "../state/backend.ts";
import { formatResult } from "../components/results.ts";

const visible = (text: string) => text.replace(/[\x00-\x08\x0b-\x1f\x7f-\x9f]/g,
  char => `\\x${char.charCodeAt(0).toString(16).padStart(2, "0")}`);

export async function startTui() {
  const renderer = await createCliRenderer({ exitOnCtrlC: false });
  let busy = true;
  let closing = false;
  let approval: string | undefined;
  let model = "";
  const layout = new BoxRenderable(renderer, { width: "100%", height: "100%", flexDirection: "column", padding: 1 });
  const header = new TextRenderable(renderer, { content: "Shell-E · Starting Python agent…", fg: "#7dd3fc", height: 2 });
  const scroll = new ScrollBoxRenderable(renderer, { flexGrow: 1, width: "100%", stickyScroll: true, stickyStart: "bottom" });
  let log = "Describe a task. Every shell command requires approval.\n";
  const transcript = new TextRenderable(renderer, { content: log, width: "100%" });
  scroll.add(transcript);
  const status = new TextRenderable(renderer, { content: "Starting…", height: 1, fg: "#a3a3a3" });
  const input = new InputRenderable(renderer, { width: "100%", placeholder: "What would you like to do?", maxLength: 8000 });
  layout.add(header); layout.add(scroll); layout.add(status); layout.add(input);
  renderer.root.add(layout);
  const append = (text: string) => {
    log = (log + visible(text)).slice(-100000);
    transcript.content = log;
  };
  const ready = (cwd: string) => {
    busy = false; approval = undefined;
    header.content = visible(`Shell-E · ${model}\n${cwd}`);
    status.content = "Ready · Esc cancel · Ctrl+C quit · /help";
    input.placeholder = "What would you like to do?"; input.focus();
  };
  const onEvent = (event: BackendEvent) => {
    if (closing) return;
    switch (event.type) {
      case "ready": model = event.model; ready(event.cwd); break;
      case "done": ready(event.cwd); break;
      case "status": status.content = visible(event.text); break;
      case "text": append(event.text); break;
      case "output": append(`\n[${event.stream}] ${event.text}`); break;
      case "tool": append(`\n[tool] ${event.name} ${JSON.stringify(event.arguments)}\n`); break;
      case "result": append(`\n[result] ${formatResult(event.name, event.result)}\n`); break;
      case "error":
        append(`\nError: ${event.text}\n`);
        busy = false; approval = undefined; status.content = "Ready · Type /help for commands"; input.focus();
        break;
      case "approval":
        approval = event.id;
        append(`\nAPPROVAL REQUIRED\nDirectory: ${event.cwd}\nTimeout: ${event.timeout_ms}ms\nReason: ${event.explanation}\n$ ${event.command}\n`);
        status.content = "Type yes or no, then Enter";
        input.value = ""; input.placeholder = "yes / no"; input.focus();
        break;
    }
  };
  const backend = startBackend(onEvent, (code, signal) => {
    append(`\nPython agent exited (code ${code ?? "unknown"}${signal ? `, signal ${signal}` : ""}). Restart Shell-E to reconnect.\n`);
    status.content = "Backend stopped · Ctrl+C quit";
    busy = true; approval = undefined; input.blur();
  });
  const shutdown = () => {
    if (closing) return;
    closing = true; backend.close(); renderer.destroy();
    process.removeListener("SIGTERM", shutdown);
    process.removeListener("SIGINT", shutdown);
  };
  process.once("SIGTERM", shutdown);
  process.once("SIGINT", shutdown);
  renderer.keyInput.on("keypress", key => {
    if (key.ctrl && key.name === "c") shutdown();
    else if (key.name === "escape" && busy) {
      approval = undefined; input.value = ""; input.blur();
      status.content = "Cancelling…"; backend.send({ type: "cancel" });
    } else if (key.name === "pageup") scroll.scrollBy(-10);
    else if (key.name === "pagedown") scroll.scrollBy(10);
  });
  input.on(InputRenderableEvents.ENTER, (value: string) => {
    const prompt = value.trim(); input.value = "";
    if (approval) {
      if (!/^(yes|no)$/i.test(prompt)) { status.content = "Enter yes to approve or no to reject"; return; }
      backend.send({ type: "approval", id: approval, approved: prompt.toLowerCase() === "yes" });
      approval = undefined; input.blur(); status.content = "Working…"; return;
    }
    if (busy || !prompt) return;
    if (prompt === "/exit" || prompt === "/quit") { shutdown(); return; }
    if (prompt === "/help") {
      append("\nCommands: /help, /cd <directory>, /clear, /exit\n");
      return;
    }
    if (prompt === "/clear") {
      log = ""; transcript.content = ""; backend.send({ type: "reset" }); return;
    }
    if (prompt === "/cd" || prompt.startsWith("/cd ")) {
      const path = prompt.slice(3).trim();
      if (!path) { append("\nUsage: /cd <directory>\n"); return; }
      busy = true; input.blur(); status.content = "Changing directory…";
      backend.send({ type: "cd", path }); return;
    }
    if (prompt.startsWith("/")) {
      append(`\nUnknown command: ${prompt.split(/\s/, 1)[0]}. Type /help for commands.\n`);
      return;
    }
    busy = true; input.blur(); status.content = "Thinking…";
    append(`\nYou: ${prompt}\nShell-E: `);
    backend.send({ type: "prompt", text: prompt });
  });
}
