import { test } from "node:test";
import assert from "node:assert/strict";
import { startBackend, type BackendEvent } from "../../src/tui/state/backend.ts";
import { formatResult } from "../../src/tui/components/results.ts";

test("command completion does not duplicate streamed output", () => {
  const text = formatResult("execute_command", { stdout: "secret-output", stderr: "failure", exitCode: 7, timedOut: true, truncated: true, cancelled: false });
  assert.equal(text, "Exit: 7 · timed out · output limit reached");
  assert.ok(!text.includes("secret-output"));
  assert.match(formatResult("execute_command", { denied: true }), /denied/);
  assert.match(formatResult("read_file", { content: "file content" }), /file content/);
});

test("TypeScript bridge starts Python, reports request errors, and shuts down", { timeout: 5000 }, async () => {
  const events: BackendEvent[] = [];
  let resolveEvent: (() => void) | undefined;
  const backend = startBackend(event => { events.push(event); resolveEvent?.(); }, () => {});
  const next = async (type: BackendEvent["type"]) => {
    while (true) {
      const index = events.findIndex(event => event.type === type);
      if (index !== -1) return events.splice(index, 1)[0];
      await new Promise<void>(resolve => { resolveEvent = resolve; });
      resolveEvent = undefined;
    }
  };
  try {
    const ready = await next("ready");
    assert.equal(ready.type, "ready");
    backend.send({ type: "cd", path: "/this/path/does/not/exist" });
    const error = await next("error");
    assert.equal(error.type, "error");
    backend.send({ type: "reset" });
    assert.equal((await next("ready")).type, "ready");
  } finally { backend.close(); }
});
