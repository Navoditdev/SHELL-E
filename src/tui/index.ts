import { startTui } from "./screens/main.ts";
try { await startTui(); }
catch (error) { console.error(error instanceof Error ? error.message : error); process.exitCode = 1; }
