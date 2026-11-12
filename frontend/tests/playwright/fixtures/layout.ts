import { expect, type Page } from '@playwright/test';

import knownFindingsData from '../layout-known-findings.json' with { type: 'json' };
import { layoutProbeMain } from './layoutProbe';

/**
 * Playwright half of the layout detector: orchestration, reporting and the quarantine.
 * The in-page measuring lives in layoutProbe.ts, whose types mirror these structurally.
 */

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Collision {
  a: string;
  b: string;
  /** Text-free identity; the stability window and the quarantine key on it. */
  keyA: string;
  keyB: string;
  area: number;
}

export interface Escape {
  el: string;
  elKey: string;
  clip: string;
  /** The part of el's line box outside the clip rect. */
  escaped: Rect;
  probe: { x: number; y: number };
  hit: string;
  via: 'self' | 'descendant' | 'pointer-events-none-ancestor';
}

export interface StateFinding {
  /** 'base' | 'scroll:<label>@<fraction>' */
  state: string;
  collisions: Collision[];
  escapes: Escape[];
}

export interface StateRecord {
  state: string;
  candidates: number;
  escapeCandidates: number;
  elapsedMs: number;
  /** 'busy' = skeleton / aria-busy / loading <img>: recorded, not measured. */
  settled: 'stable' | 'capped' | 'busy';
  findings: number;
  restabilised: boolean;
}

/** How much the probe looked at, so an empty result can be told apart from a blind one. */
export interface LayoutLedger {
  candidates: number;
  escapeCandidates: number;
  scrollContainers: number;
  scrollContainersProbed: number;
  statesExercised: string[];
  statesSkipped: string[];
  statesUnsettled: string[];
  disconnectedAtRestore: string[];
  geometricEscapes: number;
  unprobeable: number;
  budgetExceededMs: number | null;
  navbarHeightPx: number;
  timersDeferred: number;
}

export interface LayoutReport {
  viewport: { width: number; height: number };
  docOverflow: number;
  /** Only states with findings; `states` has every state attempted. */
  findings: StateFinding[];
  states: StateRecord[];
  ledger: LayoutLedger;
  debugKeys?: { candidates: string[]; geometricEscapes: string[] };
}

export interface ProbeConfig {
  minOverlapArea: number;
  minEscapeArea: number;
  scrollFractions: number[];
  maxScrollContainers: number;
  budgetMs: number;
  settleCapMs: number;
  stabilityMs: number;
  /** Minimum quiet time before the base measure; set after a viewport change. */
  baseQuietMs: number;
  states: Array<'scroll'>;
  debugKeys: boolean;
}

export interface SweepOptions extends Partial<ProbeConfig> {
  viewports: Array<{ width: number; height: number }>;
  /** Throw on a budget overrun instead of recording skipped states. */
  budgetIsFatal?: boolean;
}

/** A quarantined finding: known, owned, and tracked by an issue. */
export interface KnownFinding {
  /** The AuditRoute name (a pattern such as `/events/:eventId`), never a resolved path. */
  route: string;
  viewport: string;
  state: string;
  kind: 'collision' | 'escape';
  /** collision: `${keyA} ${keyB}`; escape: elKey. */
  findingKey: string;
  owner: string;
  issue: string;
  note: string;
  added: string;
  /** The only exemption from the stale check. */
  intermittent?: boolean;
}

export const LAYOUT_VIEWPORTS = [
  { width: 375, height: 667 },
  { width: 1440, height: 900 },
];

export const KILL_ANIMATIONS = '*,*::before,*::after{animation:none!important;transition:none!important}';

const DEFAULTS: ProbeConfig = {
  // 64 = lucide `X` at size-4 (8x8); 256 = a 16x16 escape floor.
  minOverlapArea: 64,
  minEscapeArea: 256,
  scrollFractions: [0.5, 1],
  maxScrollContainers: 3,
  budgetMs: 6000,
  settleCapMs: 800,
  stabilityMs: 300,
  baseQuietMs: 0,
  states: [],
  debugKeys: false,
};

interface LayoutProbeGlobals {
  __layoutPrepared?: boolean;
  __layoutDeferred?: number;
  __layoutFreeze?: () => void;
  __layoutThaw?: () => void;
}

/**
 * Call once per document, after navigation and before any measurement. Installs a gate the
 * probe closes while it measures a state: timers of 250ms or more scheduled while closed are
 * held and started when it reopens, so polling cannot move boxes mid-measure and nothing
 * (query retries, debounced handlers) is lost for the rest of the page's life.
 */
export async function prepareLayoutProbe(page: Page): Promise<void> {
  await expect(page.getByTestId('nav-root')).toBeVisible({ timeout: 30_000 });
  await page.addStyleTag({ content: KILL_ANIMATIONS });

  await page.evaluate(() => {
    const w = window as unknown as LayoutProbeGlobals;
    if (w.__layoutPrepared) return;
    w.__layoutPrepared = true;
    w.__layoutDeferred = 0;

    interface Held {
      fn: TimerHandler;
      ms: number;
      args: unknown[];
      repeat: boolean;
      real: number | null;
      cancelled: boolean;
    }
    const realTimeout = window.setTimeout.bind(window);
    const realInterval = window.setInterval.bind(window);
    const realClearTimeout = window.clearTimeout.bind(window);
    const realClearInterval = window.clearInterval.bind(window);
    const held = new Map<number, Held>();
    let frozen = false;
    let fake = 1 << 24;

    const start = (h: Held): void => {
      h.real = h.repeat
        ? realInterval(h.fn, h.ms, ...h.args)
        : realTimeout(h.fn, h.ms, ...h.args);
    };
    const schedule = (fn: TimerHandler, ms: number | undefined, args: unknown[], repeat: boolean): number => {
      if (!frozen || (ms ?? 0) < 250) {
        return repeat ? realInterval(fn, ms, ...args) : realTimeout(fn, ms, ...args);
      }
      w.__layoutDeferred! += 1;
      fake += 1;
      held.set(fake, { fn, ms: ms ?? 0, args, repeat, real: null, cancelled: false });
      return fake;
    };
    const clear = (id: number | undefined, repeat: boolean): void => {
      const h = id === undefined ? undefined : held.get(id);
      if (!h) {
        if (repeat) realClearInterval(id);
        else realClearTimeout(id);
        return;
      }
      h.cancelled = true;
      if (h.real !== null) (h.repeat ? realClearInterval : realClearTimeout)(h.real);
      held.delete(id!);
    };

    window.setTimeout = ((fn: TimerHandler, ms?: number, ...a: unknown[]) =>
      schedule(fn, ms, a, false)) as typeof window.setTimeout;
    window.setInterval = ((fn: TimerHandler, ms?: number, ...a: unknown[]) =>
      schedule(fn, ms, a, true)) as typeof window.setInterval;
    window.clearTimeout = ((id?: number) => clear(id, false)) as typeof window.clearTimeout;
    window.clearInterval = ((id?: number) => clear(id, true)) as typeof window.clearInterval;

    w.__layoutFreeze = () => {
      frozen = true;
    };
    w.__layoutThaw = () => {
      frozen = false;
      // Entries stay mapped after starting so clearTimeout/clearInterval on the handed-out id
      // still reaches the real timer.
      for (const h of held.values()) {
        if (!h.cancelled && h.real === null) start(h);
      }
    };
  });

  await expect(page.getByTestId('nav-root')).toBeVisible({ timeout: 5_000 });
}

/** The `base` state's collisions at the current viewport. */
export async function collisions(page: Page, minArea = DEFAULTS.minOverlapArea): Promise<Collision[]> {
  const report = await sweepLayoutOnce(page, { minOverlapArea: minArea });
  return report.findings.find((f) => f.state === 'base')?.collisions ?? [];
}

/** The `base` state's clip escapes at the current viewport. */
export async function clipEscapes(page: Page, minArea = DEFAULTS.minEscapeArea): Promise<Escape[]> {
  const report = await sweepLayoutOnce(page, { minEscapeArea: minArea });
  return report.findings.find((f) => f.state === 'base')?.escapes ?? [];
}

export async function sweepLayoutOnce(page: Page, opts: Partial<ProbeConfig> = {}): Promise<LayoutReport> {
  return page.evaluate(layoutProbeMain, { ...DEFAULTS, ...opts });
}

/**
 * One probe per viewport on the same document. The first viewport must match the page's
 * current size; later ones are reached with setViewportSize.
 */
export async function sweepLayout(page: Page, opts: SweepOptions): Promise<LayoutReport[]> {
  const { viewports, budgetIsFatal, ...probeOpts } = opts;
  const cfg: ProbeConfig = { ...DEFAULTS, ...probeOpts };
  const out: LayoutReport[] = [];
  for (let i = 0; i < viewports.length; i += 1) {
    const vp = viewports[i];
    if (i > 0) await page.setViewportSize(vp);
    // After a resize, wait out debounced resize/media-query handlers before measuring.
    const report = await page.evaluate(layoutProbeMain, { ...cfg, baseQuietMs: i > 0 ? 400 : cfg.baseQuietMs });
    if (budgetIsFatal && report.ledger.budgetExceededMs !== null) {
      throw new Error(`layout probe exceeded ${cfg.budgetMs}ms at ${vp.width}x${vp.height}`);
    }
    out.push(report);
  }
  return out;
}

function fmtRect(r: Rect): string {
  return `x=${Math.round(r.x)} y=${Math.round(r.y)} w=${Math.round(r.width)} h=${Math.round(r.height)}`;
}

export function formatReports(
  reports: LayoutReport[],
  quarantined?: Array<{ state: string; kind: string; findingKey: string; issue: string }>,
): string {
  const lines: string[] = [];
  if (reports.length === 0) lines.push('no layout reports were produced');

  for (const r of reports) {
    lines.push(`${r.viewport.width}x${r.viewport.height}`);
    if (r.findings.length === 0) lines.push('  no findings');
    for (const state of r.findings) {
      lines.push(`  state ${state.state}`);
      for (const c of state.collisions) {
        lines.push(`    collision  ${c.area}px²  ${c.a}`);
        lines.push(`                   over  ${c.b}`);
      }
      for (const e of state.escapes) {
        lines.push(`    escape     ${e.el}  escapes  ${e.clip}`);
        lines.push(
          `               escaped rect  ${fmtRect(e.escaped)}   ` +
            `probe (${Math.round(e.probe.x)},${Math.round(e.probe.y)})  hit ${e.via}  ${e.hit}`,
        );
      }
    }
    const l = r.ledger;
    lines.push(
      `  ledger  unprobeable=${l.unprobeable}  unsettled=${l.statesUnsettled.length}  ` +
        `skipped=${l.statesSkipped.length}  timersDeferred=${l.timersDeferred}`,
    );
    if (r.docOverflow > 0) lines.push(`  docOverflow  ${r.docOverflow}px wider than the viewport`);
  }

  if (quarantined?.length) {
    lines.push('  known (quarantined)');
    for (const q of quarantined) lines.push(`    ${q.kind}  ${q.state}  ${q.findingKey}  (${q.issue})`);
  }
  return lines.join('\n');
}

const KNOWN_VIEWPORTS = new Set(LAYOUT_VIEWPORTS.map((v) => `${v.width}x${v.height}`));
const KNOWN_KINDS = new Set(['collision', 'escape']);

/** Reads and validates layout-known-findings.json; a bad row throws with its index and field. */
export function loadKnownFindings(): KnownFinding[] {
  const rows: unknown = knownFindingsData;
  if (!Array.isArray(rows)) throw new Error('layout-known-findings.json must be a JSON array');

  return rows.map((raw, i) => {
    const r = raw as Record<string, unknown>;
    const str = (field: string): string => {
      const v = r[field];
      if (typeof v !== 'string' || v.trim() === '') {
        throw new Error(`layout-known-findings.json[${i}]: \`${field}\` must be a non-empty string`);
      }
      return v;
    };
    if (typeof r.note !== 'string') {
      throw new Error(`layout-known-findings.json[${i}]: \`note\` must be a string`);
    }
    if (r.intermittent !== undefined && typeof r.intermittent !== 'boolean') {
      throw new Error(`layout-known-findings.json[${i}]: \`intermittent\` must be a boolean`);
    }
    const viewport = str('viewport');
    if (!KNOWN_VIEWPORTS.has(viewport)) {
      throw new Error(`layout-known-findings.json[${i}]: unknown \`viewport\` "${viewport}"`);
    }
    const kind = str('kind');
    if (!KNOWN_KINDS.has(kind)) {
      throw new Error(`layout-known-findings.json[${i}]: unknown \`kind\` "${kind}"`);
    }
    return {
      route: str('route'),
      viewport,
      state: str('state'),
      kind: kind as 'collision' | 'escape',
      findingKey: str('findingKey'),
      owner: str('owner'),
      issue: str('issue'),
      note: r.note,
      added: str('added'),
      intermittent: r.intermittent as boolean | undefined,
    };
  });
}

export interface FreshFinding {
  viewport: string;
  state: string;
  kind: string;
  findingKey: string;
  text: string;
}

/**
 * Splits a route's findings (`route` is the AuditRoute name): `fresh` gates, `matched` is quarantined, and `stale` (a quarantined
 * key that no longer fires) gates too so the file cannot quietly grow. Matching is exact.
 */
export function partitionFindings(
  reports: LayoutReport[],
  route: string,
  known: KnownFinding[] = loadKnownFindings(),
): { fresh: FreshFinding[]; matched: KnownFinding[]; stale: KnownFinding[] } {
  const scoped = known.filter((k) => k.route === route);

  const observed: FreshFinding[] = [];
  for (const r of reports) {
    const viewport = `${r.viewport.width}x${r.viewport.height}`;
    for (const state of r.findings) {
      for (const c of state.collisions) {
        observed.push({
          viewport,
          state: state.state,
          kind: 'collision',
          findingKey: `${c.keyA} ${c.keyB}`,
          text: `${c.area}px² ${c.a} over ${c.b}`,
        });
      }
      for (const e of state.escapes) {
        observed.push({
          viewport,
          state: state.state,
          kind: 'escape',
          findingKey: e.elKey,
          text: `${e.el} escapes ${e.clip} at ${fmtRect(e.escaped)} (via ${e.via})`,
        });
      }
    }
  }

  const id = (k: { viewport: string; state: string; kind: string; findingKey: string }) =>
    `${k.viewport} ${k.state} ${k.kind} ${k.findingKey}`;
  const seen = new Set(observed.map(id));
  const quarantined = new Set(scoped.map(id));

  return {
    fresh: observed.filter((o) => !quarantined.has(id(o))),
    matched: scoped.filter((k) => seen.has(id(k))),
    stale: scoped.filter((k) => !seen.has(id(k)) && k.intermittent !== true),
  };
}
