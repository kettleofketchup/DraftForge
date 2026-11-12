export function captureClockOffset(serverTimeIso: string, receivedAtMs: number): number {
  const serverMs = Date.parse(serverTimeIso);
  return Number.isNaN(serverMs) ? 0 : serverMs - receivedAtMs;
}

/** Samples the estimator keeps: about the last ten seconds of 1 Hz ticks. */
export const CLOCK_OFFSET_SAMPLES = 10;

export interface ClockOffsetEstimate {
  samples: number[];
  offsetMs: number;
}

/**
 * Each sample is server_time - receivedAt, i.e. the true offset minus that
 * message's delivery delay. Delay is never negative, so the largest recent
 * sample is the least-delayed one; a tick stuck in a queue can't drag the clock.
 */
export function bestClockOffset(samples: readonly number[]): number {
  return samples.length === 0 ? 0 : Math.max(...samples);
}

/** Add one tick's sample, keeping the last {@link CLOCK_OFFSET_SAMPLES}. */
export function addClockOffsetSample(
  samples: readonly number[],
  serverTimeIso: string,
  receivedAtMs: number,
): ClockOffsetEstimate {
  const next = [...samples, captureClockOffset(serverTimeIso, receivedAtMs)].slice(-CLOCK_OFFSET_SAMPLES);
  return { samples: next, offsetMs: bestClockOffset(next) };
}

/** Restart the estimate from an initial_state's server_time (kept as-is when absent). */
export function seedClockOffset(
  samples: readonly number[],
  serverTimeIso: string | null | undefined,
  receivedAtMs: number,
): ClockOffsetEstimate {
  if (!serverTimeIso) return { samples: [...samples], offsetMs: bestClockOffset(samples) };
  return addClockOffsetSample([], serverTimeIso, receivedAtMs);
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
