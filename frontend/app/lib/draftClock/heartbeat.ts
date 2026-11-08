export const HEARTBEAT_INTERVAL_MS = 3000;

export function startHeartbeatLoop(send: () => void, intervalMs: number = HEARTBEAT_INTERVAL_MS): () => void {
  send();
  const id = setInterval(send, intervalMs);
  return () => clearInterval(id);
}
