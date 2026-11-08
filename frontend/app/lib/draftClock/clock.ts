export function captureClockOffset(serverTimeIso: string, receivedAtMs: number): number {
  const serverMs = Date.parse(serverTimeIso);
  return Number.isNaN(serverMs) ? 0 : serverMs - receivedAtMs;
}

export function serverNow(offsetMs: number): number {
  return Date.now() + offsetMs;
}

export function serverNowISO(offsetMs: number): string {
  return new Date(serverNow(offsetMs)).toISOString();
}

export function elapsedSince(anchorIso: string | null | undefined, serverNowMs: number): number {
  if (!anchorIso) return 0;
  const anchorMs = Date.parse(anchorIso);
  if (Number.isNaN(anchorMs)) return 0;
  return Math.max(0, serverNowMs - anchorMs);
}

export function remaining(
  anchorIso: string | null | undefined,
  durationMs: number | null | undefined,
  serverNowMs: number,
): number {
  if (typeof durationMs !== 'number' || Number.isNaN(durationMs)) return 0;
  if (!anchorIso || Number.isNaN(Date.parse(anchorIso))) return 0;
  return Math.max(0, durationMs - elapsedSince(anchorIso, serverNowMs));
}
