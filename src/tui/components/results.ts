// Execution output is already streamed. Display only completion metadata here.
export function formatResult(name: string, result: unknown): string {
  if (name === "execute_command" && result && typeof result === "object" && "exitCode" in result) {
    const command = result as { exitCode: number | null; timedOut: boolean; truncated: boolean; cancelled: boolean };
    return `Exit: ${command.exitCode ?? "terminated"}${command.timedOut ? " · timed out" : ""}${command.truncated ? " · output limit reached" : ""}${command.cancelled ? " · cancelled" : ""}`;
  }
  return JSON.stringify(result);
}
