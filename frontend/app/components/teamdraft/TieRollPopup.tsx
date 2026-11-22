import {
  Dice1,
  Dice2,
  Dice3,
  Dice4,
  Dice5,
  Dice6,
  X,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { UserType } from '~/index';
import { cn } from '~/lib/utils';
import type { TieResolution } from './types';

export const DEFAULT_TIE_HOLD_MS = 5000;
/** A viewer who learns of the tie as the hold ends still gets this long to read the result. */
export const TIE_ROLL_MIN_VISIBLE_MS = 3000;
const WINNER_LINGER_MS = 1500;
const MIN_ROUND_MS = 500;
const MAX_ROUND_MS = 1200;
const TUMBLE_SHARE = 0.7;
const FRAME_MS = 80;

const DICE: LucideIcon[] = [Dice1, Dice2, Dice3, Dice4, Dice5, Dice6];

export interface TieRollTimeline {
  roundMs: number;
  winnerAtMs: number;
  totalMs: number;
}

export function tieRollTimeline(
  rounds: number,
  holdMs: number,
): TieRollTimeline {
  const totalMs = Math.max(holdMs, MIN_ROUND_MS * rounds + WINNER_LINGER_MS);
  const roundMs = Math.min(
    MAX_ROUND_MS,
    Math.max(MIN_ROUND_MS, (totalMs - WINNER_LINGER_MS) / Math.max(rounds, 1)),
  );
  return { roundMs, winnerAtMs: roundMs * rounds, totalMs };
}

export interface TieRollFrame {
  /** Index of the round currently shown; -1 before the first roll starts. */
  round: number;
  tumbling: boolean;
  winnerShown: boolean;
}

export function tieRollFrame(
  elapsedMs: number,
  rounds: number,
  t: TieRollTimeline,
): TieRollFrame {
  if (elapsedMs >= t.winnerAtMs)
    return { round: rounds - 1, tumbling: false, winnerShown: true };
  const round = Math.min(rounds - 1, Math.floor(elapsedMs / t.roundMs));
  const inRound = elapsedMs - round * t.roundMs;
  return {
    round,
    tumbling: inRound < t.roundMs * TUMBLE_SHARE,
    winnerShown: false,
  };
}

export interface TieRollTeam {
  id: number;
  captain: UserType | null;
}

interface TieRollPopupProps {
  tie: TieResolution;
  teams: TieRollTeam[];
  onDone: () => void;
  /** The draft clock is on; the countdown also needs the server's `hold_until`, sent only when it holds the clock. */
  clockHeld: boolean;
  /** Injected for tests; defaults to performance.now. */
  now?: () => number;
  /** Server-clock epoch ms, used to read `hold_until`; defaults to this browser's clock. */
  serverNow?: () => number;
  /** The tied round's live clock start and pause state; a pause or resume moves it. */
  liveHold?: LiveTieHold | null;
}

export interface LiveTieHold {
  until: string | null;
  paused: boolean;
}

interface LiveHoldDraft {
  state?: string | null;
  latest_round?: number | null;
  draft_rounds?: ReadonlyArray<{
    pk: number;
    pick_number?: number | null;
    started_at?: string | null;
  }> | null;
}

interface LiveHoldTick {
  active_round_pk: number | null;
  round_started_at: string | null;
}

/** The tied pick's clock start from the live draft state (a newer tick wins); null once another pick is active. */
export function liveTieHold(
  tick: LiveHoldTick | null,
  draft: LiveHoldDraft | null,
  tickIsNewer: boolean,
  pickNumber: number | undefined,
): LiveTieHold | null {
  if (!draft || pickNumber == null) return null;
  const round = draft.draft_rounds?.find((r) => r.pk === draft.latest_round);
  if (!round || round.pick_number !== pickNumber) return null;
  const fromTick =
    tick && tickIsNewer && tick.active_round_pk === round.pk
      ? tick.round_started_at
      : null;
  return {
    until: fromTick ?? round.started_at ?? null,
    paused: draft.state === 'paused',
  };
}

const perfNow = () => performance.now();
const localNow = () => Date.now();

/** Hold left at mount: until `hold_until` on the server clock (never more than the full hold), else `hold_ms`. */
export function tieHoldLeftMs(tie: TieResolution, serverNowMs: number): number {
  const fullMs = tie.hold_ms ?? DEFAULT_TIE_HOLD_MS;
  const until = tie.hold_until ? Date.parse(tie.hold_until) : Number.NaN;
  if (Number.isNaN(until)) return fullMs;
  return Math.min(fullMs, Math.max(0, until - serverNowMs));
}

export function TieRollPopup({
  tie,
  teams,
  onDone,
  clockHeld,
  now = perfNow,
  serverNow = localNow,
  liveHold = null,
}: TieRollPopupProps) {
  const rounds = tie.roll_rounds.length;
  const [mountHoldLeftMs] = useState(() => tieHoldLeftMs(tie, serverNow()));
  const timeline = tieRollTimeline(
    rounds,
    Math.max(mountHoldLeftMs, TIE_ROLL_MIN_VISIBLE_MS),
  );
  const nowRef = useRef(now);
  const [startedAt] = useState(now);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const id = setInterval(
      () => setElapsed(nowRef.current() - startedAt),
      FRAME_MS,
    );
    return () => clearInterval(id);
  }, [startedAt]);

  const paused = liveHold?.paused ?? false;
  const movedUntil = movedHoldEnd(tie, liveHold);
  const holdLeftMs =
    movedUntil == null
      ? Math.max(0, mountHoldLeftMs - elapsed)
      : Math.max(0, movedUntil - serverNow());
  const done = !paused && elapsed >= timeline.totalMs && holdLeftMs <= 0;

  useEffect(() => {
    if (done) onDone();
  }, [done, onDone]);

  const frame = tieRollFrame(elapsed, rounds, timeline);
  const step = Math.floor(elapsed / FRAME_MS);
  const captainOf = (teamId: number) =>
    teams.find((t) => t.id === teamId)?.captain ?? null;
  const labelOf = (teamId: number) => {
    const captain = captainOf(teamId);
    return captain
      ? DisplayName(captain)
      : (tie.tied_teams.find((t) => t.id === teamId)?.name ?? 'Team');
  };
  const winnerLabel = labelOf(tie.winner_id);
  const secondsLeft = Math.ceil(holdLeftMs / 1000);
  const serverHeld =
    tie.hold_until != null && !Number.isNaN(Date.parse(tie.hold_until));
  const remainingMs = paused
    ? timeline.totalMs
    : Math.max(timeline.totalMs - elapsed, holdLeftMs);
  const remainingPct = Math.min(100, (100 * remainingMs) / timeline.totalMs);

  return (
    <div
      data-testid="tie-roll-popup"
      data-pick-number={tie.pick_number ?? ''}
      data-winner-id={tie.winner_id}
      role="status"
      aria-live="polite"
      className="pointer-events-auto fixed inset-x-3 bottom-20 z-[60] animate-in fade-in slide-in-from-right-8 duration-300 rounded-xl border border-white/15 bg-base-950/95 p-4 text-white shadow-2xl backdrop-blur md:inset-x-auto md:bottom-auto md:top-14 md:right-4 md:w-[24rem]"
    >
      <span className="sr-only">
        Tie{tie.pick_number ? ` for pick ${tie.pick_number}` : ''}:{' '}
        {winnerLabel} won the dice roll and picks next.
      </span>
      <div className="flex items-start justify-between gap-2" aria-hidden>
        <div>
          <div className="text-base font-semibold">
            Tie{tie.pick_number ? ` for pick #${tie.pick_number}` : ''}: rolling
            dice
          </div>
          <div className="text-xs text-muted-foreground">
            Same team MMR. Highest roll picks next.
          </div>
        </div>
        <button
          type="button"
          data-testid="tie-roll-close"
          aria-label="Hide dice roll"
          onClick={onDone}
          className="rounded p-1 text-muted-foreground hover:bg-white/10 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <ul className="mt-2 flex flex-col gap-1.5" aria-hidden>
        {tie.tied_teams.map((team, idx) => {
          const roll = tie.roll_rounds[frame.round]?.find(
            (r) => r.team_id === team.id,
          );
          const out = !roll;
          const isWinner = frame.winnerShown && team.id === tie.winner_id;
          const lost = frame.winnerShown && !isWinner;
          const tumbling = frame.tumbling && !out && frame.round >= 0;
          const face = tumbling
            ? ((step + idx * 2) % 6) + 1
            : (roll?.roll ?? 1);
          const Die = DICE[face - 1];
          const history = tie.roll_rounds
            .slice(0, tumbling ? frame.round : frame.round + 1)
            .map((r) => r.find((x) => x.team_id === team.id)?.roll)
            .filter((r): r is number => r != null);
          const captain = captainOf(team.id);
          return (
            <li
              key={team.id}
              data-testid={`tie-roll-row-${team.id}`}
              data-winner={isWinner}
              className={cn(
                'flex items-center gap-3 rounded-lg px-2.5 py-2 transition-colors',
                isWinner ? 'bg-success/25 ring-1 ring-success' : 'bg-white/5',
                (out || lost) && 'opacity-40',
              )}
            >
              {captain ? (
                <UserAvatar user={captain} size="md" />
              ) : (
                <div className="h-8 w-8 shrink-0 rounded-full bg-muted" />
              )}
              <span
                className={cn(
                  'flex-1 truncate text-sm',
                  isWinner && 'font-semibold',
                )}
              >
                {labelOf(team.id)}
              </span>
              {history.length > 1 && (
                <span className="font-mono text-[10px] text-muted-foreground">
                  {history.slice(0, -1).join(' · ')}
                </span>
              )}
              {out ? (
                <span className="text-[10px] uppercase text-muted-foreground">
                  out
                </span>
              ) : (
                <Die
                  data-testid={`tie-roll-die-${team.id}`}
                  data-face={tumbling ? undefined : face}
                  className={cn(
                    'h-9 w-9',
                    tumbling && 'animate-spin [animation-duration:400ms]',
                    isWinner ? 'text-success' : 'text-white',
                  )}
                />
              )}
            </li>
          );
        })}
      </ul>

      <div className="mt-2 flex items-center gap-2" aria-hidden>
        <span
          data-testid="tie-roll-result"
          className={cn(
            'flex-1 text-sm',
            frame.winnerShown
              ? 'font-semibold text-success'
              : 'text-muted-foreground',
          )}
        >
          {frame.winnerShown ? `${winnerLabel} picks next` : 'Rolling…'}
        </span>
        {clockHeld && serverHeld && (paused || secondsLeft > 0) && (
          <span
            data-testid="tie-roll-countdown"
            className="text-xs tabular-nums text-muted-foreground"
          >
            {paused ? 'Clock paused' : `Clock starts in ${secondsLeft}s`}
          </span>
        )}
      </div>
      <div className="mt-1 h-1 overflow-hidden rounded bg-white/10" aria-hidden>
        <div
          className="h-full bg-primary transition-[width] duration-100"
          style={{ width: `${remainingPct}%` }}
        />
      </div>
    </div>
  );
}

/** The live hold end in server epoch ms when a pause or resume has moved it off `hold_until`. */
function movedHoldEnd(
  tie: TieResolution,
  liveHold: LiveTieHold | null,
): number | null {
  if (!liveHold?.until) return null;
  const live = Date.parse(liveHold.until);
  if (Number.isNaN(live)) return null;
  const sent = tie.hold_until ? Date.parse(tie.hold_until) : Number.NaN;
  return live === sent ? null : live;
}

export function tieRollKey(tie: TieResolution): string {
  return `${tie.pick_number ?? ''}:${tie.winner_id}:${JSON.stringify(tie.roll_rounds)}`;
}
