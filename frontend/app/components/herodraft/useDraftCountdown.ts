import { useEffect, useRef, useState } from "react";
import { useHeroDraftStore } from "~/store/heroDraftStore";
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

function deriveCountdown(
  tick: HeroDraftTick | null,
  serverClockOffsetMs: number,
): DraftCountdown {
  if (!tick) return ZERO;

  // Offset was captured ONCE at tick-receive time by the store.
  // Computing it again per frame (Date.now() + (server_time - Date.now()))
  // collapses to `server_time` exactly — the clock would only advance
  // when a new tick arrived (1Hz), not the 60fps we want.
  const serverNowMs = Date.now() + serverClockOffsetMs;

  // RESUMING — single countdown to draft.resuming_until. The grace and
  // reserve values are FROZEN at what they'll be when RESUMING completes:
  // server has already pushed round_started_at forward by pause_duration
  // + 3s, so evaluating elapsed at resuming_until reproduces the values
  // from the moment of pause.
  if (tick.draft_state === "resuming" && tick.resuming_until) {
    const target = new Date(tick.resuming_until).getTime();
    const resumingRemainingMs = Math.max(0, target - serverNowMs);
    const frozen = computeDraftingValues(tick, target);
    return {
      ...frozen,
      resumingRemainingMs,
    };
  }

  // DRAFTING — compute grace + per-team reserve from anchors
  if (tick.draft_state === "drafting") {
    return {
      ...computeDraftingValues(tick, serverNowMs),
      resumingRemainingMs: 0,
    };
  }

  return ZERO;
}

function computeDraftingValues(
  tick: HeroDraftTick,
  serverNowMs: number,
): Omit<DraftCountdown, "resumingRemainingMs"> {
  if (
    !tick.round_started_at ||
    typeof tick.round_grace_time_ms !== "number"
  ) {
    return { graceRemainingMs: 0, teamAReserveMs: 0, teamBReserveMs: 0 };
  }
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

  return { graceRemainingMs, teamAReserveMs, teamBReserveMs };
}

/**
 * Render-time countdown driven by requestAnimationFrame.
 *
 * Reads `tick`, `serverClockOffsetMs`, and `draft.state` from the store.
 * Each frame recomputes remaining values from the tick's anchors using
 * `Date.now() + offset` — smooth 60fps even when 1Hz ticks are delayed
 * or dropped, eliminating the "everyone's timer froze" symptom.
 *
 * During pause the server stops broadcasting ticks; the cached tick
 * keeps reading `drafting` with a stale `round_started_at`. We skip the
 * setState call while `draft.state === "paused"` so values freeze at
 * whatever they were the moment pause was entered.
 */
export function useDraftCountdown(): DraftCountdown {
  const tick = useHeroDraftStore((s) => s.tick);
  const serverClockOffsetMs = useHeroDraftStore((s) => s.serverClockOffsetMs);
  const isPaused = useHeroDraftStore((s) => s.draft?.state === "paused");

  const [countdown, setCountdown] = useState<DraftCountdown>(() =>
    deriveCountdown(tick, serverClockOffsetMs),
  );

  const tickRef = useRef(tick);
  const offsetRef = useRef(serverClockOffsetMs);
  const isPausedRef = useRef(isPaused);
  tickRef.current = tick;
  offsetRef.current = serverClockOffsetMs;
  isPausedRef.current = isPaused;

  // Re-derive once on every new tick even while paused, so a tick that
  // lands DURING pause (e.g. a final RESUMING anchor) still propagates
  // its values into the display before the frame loop freezes.
  useEffect(() => {
    setCountdown(deriveCountdown(tick, serverClockOffsetMs));
  }, [tick, serverClockOffsetMs]);

  useEffect(() => {
    let rafId = 0;
    const frame = () => {
      if (!isPausedRef.current) {
        setCountdown(deriveCountdown(tickRef.current, offsetRef.current));
      }
      rafId = requestAnimationFrame(frame);
    };
    rafId = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(rafId);
  }, []);

  return countdown;
}

// Exported for unit-test access to the pure derivation logic.
export { deriveCountdown as _deriveCountdown };
export type { HeroDraftTick };
