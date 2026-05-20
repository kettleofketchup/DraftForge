import { useEffect, useRef, useState } from "react";
import type { HeroDraftTick } from "./types";

/**
 * Derived countdown values reconstructed client-side from server anchors.
 *
 * `tick.server_time` defines our clock offset; everything else flows from
 * that + `Date.now()` evaluated on each requestAnimationFrame.
 */
export interface DraftCountdown {
  /** ms remaining in the current round's grace window. 0 once expired. */
  graceRemainingMs: number;
  /** Reserve time remaining for team A right now. */
  teamAReserveMs: number;
  /** Reserve time remaining for team B right now. */
  teamBReserveMs: number;
  /** ms remaining until the RESUMING countdown ends. 0 outside RESUMING. */
  resumingRemainingMs: number;
}

const ZERO: DraftCountdown = {
  graceRemainingMs: 0,
  teamAReserveMs: 0,
  teamBReserveMs: 0,
  resumingRemainingMs: 0,
};

function computeServerNowMs(tick: HeroDraftTick): number {
  // Offset between server clock and ours. Server time was the moment the
  // broadcast was assembled; our Date.now() at receive includes network
  // latency, so offset absorbs both clock skew and one-way latency.
  const serverTimeMs = new Date(tick.server_time).getTime();
  const receivedAtMs = Date.now();
  const offset = serverTimeMs - receivedAtMs;
  return Date.now() + offset;
}

function deriveCountdown(tick: HeroDraftTick | null): DraftCountdown {
  if (!tick) return ZERO;

  const serverNowMs = computeServerNowMs(tick);

  // RESUMING — single countdown to draft.resuming_until
  if (tick.draft_state === "resuming" && tick.resuming_until) {
    const target = new Date(tick.resuming_until).getTime();
    return {
      ...ZERO,
      resumingRemainingMs: Math.max(0, target - serverNowMs),
    };
  }

  // DRAFTING — compute grace + per-team reserve from anchors
  if (
    tick.draft_state === "drafting" &&
    tick.round_started_at &&
    typeof tick.round_grace_time_ms === "number"
  ) {
    const startedAtMs = new Date(tick.round_started_at).getTime();
    const elapsedMs = Math.max(0, serverNowMs - startedAtMs);
    const graceRemainingMs = Math.max(0, tick.round_grace_time_ms - elapsedMs);

    // Active team's reserve burns down once elapsed exceeds grace.
    // Non-active team's reserve stays at its round-start value.
    const reserveConsumedMs = Math.max(0, elapsedMs - tick.round_grace_time_ms);
    const teamAAtStart = tick.team_a_reserve_ms ?? 0;
    const teamBAtStart = tick.team_b_reserve_ms ?? 0;
    const teamAReserveMs =
      tick.team_a_id === tick.active_team_id
        ? Math.max(0, teamAAtStart - reserveConsumedMs)
        : teamAAtStart;
    const teamBReserveMs =
      tick.team_b_id === tick.active_team_id
        ? Math.max(0, teamBAtStart - reserveConsumedMs)
        : teamBAtStart;

    return {
      graceRemainingMs,
      teamAReserveMs,
      teamBReserveMs,
      resumingRemainingMs: 0,
    };
  }

  return ZERO;
}

/**
 * Render-time countdown driven by requestAnimationFrame.
 *
 * Each frame recomputes remaining values from `tick`'s anchors using the
 * client's current `Date.now()`. Result: 60fps smooth UI that keeps
 * counting down even when ticks are delayed or dropped — eliminates the
 * "everyone's timer froze for a few seconds" symptom by design.
 *
 * Re-anchors implicitly on every new tick (the closure captures the new
 * tick reference, so offset re-computation happens on next frame).
 */
export function useDraftCountdown(tick: HeroDraftTick | null): DraftCountdown {
  const [countdown, setCountdown] = useState<DraftCountdown>(() =>
    deriveCountdown(tick),
  );
  const tickRef = useRef(tick);
  tickRef.current = tick;

  useEffect(() => {
    let rafId = 0;
    const frame = () => {
      setCountdown(deriveCountdown(tickRef.current));
      rafId = requestAnimationFrame(frame);
    };
    rafId = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(rafId);
  }, []);

  return countdown;
}
