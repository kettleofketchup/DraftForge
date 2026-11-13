/**
 * In-page half of the layout detector; fixtures/layout.ts is the Playwright half.
 *
 * `layoutProbeMain` is serialised by page.evaluate(), so it must close over nothing: every
 * helper lives inside its body. The types below mirror layout.ts structurally (an import would
 * survive serialisation as an undefined identifier); the call sites there catch drift.
 */

interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface Collision {
  a: string;
  b: string;
  keyA: string;
  keyB: string;
  area: number;
}

interface Escape {
  el: string;
  elKey: string;
  clip: string;
  escaped: Rect;
  probe: { x: number; y: number };
  hit: string;
  via: 'self' | 'descendant' | 'pointer-events-none-ancestor';
}

interface StateFinding {
  state: string;
  collisions: Collision[];
  escapes: Escape[];
}

interface StateRecord {
  state: string;
  candidates: number;
  escapeCandidates: number;
  elapsedMs: number;
  settled: 'stable' | 'capped' | 'busy';
  findings: number;
  restabilised: boolean;
}

interface LayoutLedger {
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

interface LayoutReport {
  viewport: { width: number; height: number };
  docOverflow: number;
  findings: StateFinding[];
  states: StateRecord[];
  ledger: LayoutLedger;
  debugKeys?: { candidates: string[]; geometricEscapes: string[] };
}

interface ProbeConfig {
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

/**
 * Measures one viewport across every requested state. Slow timers are deferred while a state
 * is measured, so the probe's own waits are rAF-driven.
 */
export async function layoutProbeMain(config: ProbeConfig): Promise<LayoutReport> {
  const t0 = performance.now();
  const elapsed = (): number => performance.now() - t0;

  // Deliberately layered surfaces: covering the page is their job, not a defect.
  const IGNORE =
    '[data-slot=dialog-overlay],[data-slot=dialog-content],' +
    '[data-slot=alert-dialog-overlay],[data-slot=alert-dialog-content],' +
    '[data-slot=popover-content],[data-slot=select-content],[data-slot=hover-card-content],' +
    '[data-slot=tooltip-content],[role=dialog],[role=alertdialog]';

  const FAR = 1e7;

  interface Box {
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  }
  /** `host: null` means nothing clips. */
  interface Clip {
    box: Box;
    host: Element | null;
  }
  /** The three clip chains a child can inherit, picked by its own `position`. */
  interface Ctx {
    stat: Clip;
    abs: Clip;
    fix: Clip;
  }
  interface CandidateBox {
    el: Element;
    frame: Element | null;
    top: number;
    bottom: number;
    left: number;
    right: number;
  }
  interface Scan {
    styleOf: Map<Element, CSSStyleDeclaration>;
    clipOf: Map<Element, Clip>;
    frameOf: Map<Element, Element | null>;
    collisionCandidates: Element[];
    escapeCandidates: Element[];
  }
  interface Measurement {
    collisions: Collision[];
    escapes: Escape[];
    candidates: number;
    escapeCandidates: number;
    candidateKeys: string[];
    geometricKeys: string[];
    unprobeable: number;
  }

  const area = (b: Box): number => Math.max(0, b.x2 - b.x1) * Math.max(0, b.y2 - b.y1);
  const intersect = (p: Box, q: Box): Box => ({
    x1: Math.max(p.x1, q.x1),
    y1: Math.max(p.y1, q.y1),
    x2: Math.min(p.x2, q.x2),
    y2: Math.min(p.y2, q.y2),
  });
  const toRect = (b: Box): Rect => ({
    x: Math.round(b.x1),
    y: Math.round(b.y1),
    width: Math.round(b.x2 - b.x1),
    height: Math.round(b.y2 - b.y1),
  });

  // `key` is text-free so the stability window and the quarantine survive seed-data changes;
  // `label` carries text for humans.
  /** A testid or a hand-written id; React/Radix generated ids (`:r1:`, `radix-…`) change per render. */
  const anchorName = (el: Element): string | null => {
    const testid = el.getAttribute('data-testid');
    if (testid) return `@${testid}`;
    const id = el.id;
    if (id && !id.includes(':') && !id.startsWith('radix-')) return `#${id}`;
    return null;
  };

  // Sibling indices up to the nearest named ancestor, so a conditional banner earlier in the
  // page does not shift the key of everything after it.
  const domPath = (el: Element): string => {
    const parts: number[] = [];
    let cur: Element | null = el;
    let anchor = '';
    while (cur && cur !== document.body && parts.length < 24) {
      const parent: Element | null = cur.parentElement;
      if (!parent) break;
      let i = 0;
      for (let k = 0; k < parent.children.length; k += 1) {
        if (parent.children[k] === cur) {
          i = k;
          break;
        }
      }
      parts.push(i);
      const named = parent === document.body ? null : anchorName(parent);
      if (named) {
        anchor = named;
        break;
      }
      cur = parent;
    }
    return `${anchor}/${parts.reverse().join('.')}`;
  };

  const key = (el: Element): string => {
    const testid = el.getAttribute('data-testid') ?? '';
    // getAttribute: on an SVGElement .className is an SVGAnimatedString.
    const cls = (el.getAttribute('class') ?? '').trim().split(/\s+/)[0] ?? '';
    return `${el.tagName.toLowerCase()}|${testid}|${cls}|${domPath(el)}`;
  };

  const label = (el: Element): string => {
    const text = (el.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 40);
    const testid = el.getAttribute('data-testid');
    return `<${el.tagName.toLowerCase()}${testid ? ` data-testid="${testid}"` : ''}>${text}`;
  };

  // Resolved by layout before any measure; probes inside this band would hit the sticky navbar.
  const navEl = document.querySelector('[data-testid=nav-root]');
  const navbarHeightPx = navEl ? Math.max(0, Math.round(navEl.getBoundingClientRect().bottom)) : 0;

  const ledger: LayoutLedger = {
    candidates: 0,
    escapeCandidates: 0,
    scrollContainers: 0,
    scrollContainersProbed: 0,
    statesExercised: [],
    statesSkipped: [],
    statesUnsettled: [],
    disconnectedAtRestore: [],
    geometricEscapes: 0,
    unprobeable: 0,
    budgetExceededMs: null,
    navbarHeightPx,
    timersDeferred: 0,
  };

  const geometryHash = (): number => {
    let h = 2166136261;
    const els = document.body.querySelectorAll('*');
    for (let i = 0; i < els.length; i += 1) {
      const r = els[i].getBoundingClientRect();
      const v = [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)];
      for (let k = 0; k < 4; k += 1) h = Math.imul(h ^ v[k], 16777619);
    }
    return h >>> 0;
  };

  // In the viewport, not merely sized: a below-the-fold `loading="lazy"` image never loads, and
  // counting it would mark every state busy.
  const inViewport = (el: Element): boolean => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 &&
      r.top < window.innerHeight && r.left < window.innerWidth;
  };

  const isBusy = (): boolean => {
    const pending = document.querySelectorAll('[aria-busy="true"],[data-slot="skeleton"]');
    for (let i = 0; i < pending.length; i += 1) {
      if (inViewport(pending[i])) return true;
    }
    const imgs = document.images;
    for (let i = 0; i < imgs.length; i += 1) {
      const img = imgs[i];
      if (img.getAttribute('src') && !img.complete && inViewport(img)) return true;
    }
    return false;
  };

  // Three identical geometry samples, not two: one lull between renders is a single equal pair.
  // `quietMs` additionally holds out for that long since the last change, which is what lets a
  // debounced resize handler land after a viewport change.
  const settle = (capMs: number, quietMs: number): Promise<'stable' | 'capped' | 'busy'> =>
    new Promise((resolve) => {
      const start = performance.now();
      const cap = Math.max(capMs, quietMs + capMs);
      let prev = geometryHash();
      let changedAt = start;
      let held = 0;
      const tick = (): void => {
        const now = performance.now();
        const next = geometryHash();
        const busy = isBusy();
        if (next === prev) {
          held += 1;
        } else {
          held = 0;
          changedAt = now;
        }
        if (held >= 2 && now - changedAt >= quietMs && !busy) {
          resolve('stable');
          return;
        }
        if (now - start >= cap) {
          resolve(busy ? 'busy' : 'capped');
          return;
        }
        prev = next;
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });

  const waitMs = (ms: number): Promise<void> =>
    new Promise((resolve) => {
      const start = performance.now();
      const tick = (): void => {
        if (performance.now() - start >= ms) {
          resolve();
          return;
        }
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });

  // One descent per measure builds the clip chain, positioning frame and both candidate sets;
  // getComputedStyle and getBoundingClientRect are the whole cost of the probe.
  const paddingBox = (cs: CSSStyleDeclaration, r: DOMRect): Box => ({
    x1: r.left + (parseFloat(cs.borderLeftWidth) || 0),
    y1: r.top + (parseFloat(cs.borderTopWidth) || 0),
    x2: r.right - (parseFloat(cs.borderRightWidth) || 0),
    y2: r.bottom - (parseFloat(cs.borderBottomWidth) || 0),
  });

  /** Anything that makes an element a containing block for out-of-flow descendants. */
  const transformLike = (cs: CSSStyleDeclaration): boolean =>
    cs.transform !== 'none' ||
    cs.perspective !== 'none' ||
    cs.filter !== 'none' ||
    /transform|perspective|filter/.test(cs.willChange || '') ||
    /paint|layout|strict|content/.test(cs.contain || '');

  const ownsText = (el: Element): boolean => {
    for (let i = 0; i < el.childNodes.length; i += 1) {
      const n = el.childNodes[i];
      if (n.nodeType === 3 && (n.textContent ?? '').trim()) return true;
    }
    return false;
  };

  const scan = (): Scan => {
    const styleOf = new Map<Element, CSSStyleDeclaration>();
    const clipOf = new Map<Element, Clip>();
    const frameOf = new Map<Element, Element | null>();
    const collisionCandidates: Element[] = [];
    const escapeCandidates: Element[] = [];
    const unclipped: Clip = { box: { x1: -FAR, y1: -FAR, x2: FAR, y2: FAR }, host: null };

    // <body>/<html> are not clip hosts: a viewport term here would silently limit the detector
    // to the first screen of every route.
    const walk = (node: Element, ctx: Ctx, frame: Element | null, colBlocked: boolean): void => {
      for (let i = 0; i < node.children.length; i += 1) {
        const child = node.children[i];
        if (child.matches(IGNORE)) continue;
        const cs = getComputedStyle(child);
        if (cs.display === 'none' || cs.opacity === '0') continue;
        // visibility:hidden does not paint, but a descendant set back to visible does, so the
        // subtree is still walked; each child checks its own visibility.
        const painted = cs.visibility !== 'hidden';

        const pos = cs.position;
        const own = pos === 'fixed' ? ctx.fix : pos === 'absolute' ? ctx.abs : ctx.stat;
        const positioned = pos === 'fixed' || pos === 'absolute' || pos === 'sticky';
        const childFrame = positioned ? child : frame;
        styleOf.set(child, cs);
        clipOf.set(child, own);
        frameOf.set(child, childFrame);

        const tag = child.tagName.toLowerCase();
        const isSvg = tag === 'svg';
        const r = child.getBoundingClientRect();
        const bigEnough = painted && r.width >= 2 && r.height >= 2;

        // An <svg> is one object: lucide's `X` is two crossing <path>s that would otherwise
        // collide with each other at exactly minOverlapArea.
        if (bigEnough && !positioned && !colBlocked && (ownsText(child) || isSvg || child.children.length === 0)) {
          collisionCandidates.push(child);
        }
        if (bigEnough && own.host !== null) escapeCandidates.push(child);

        if (isSvg) continue;

        const clips = cs.overflowX !== 'visible' || cs.overflowY !== 'visible';
        const base: Clip = clips ? { box: intersect(own.box, paddingBox(cs, r)), host: child } : own;
        walk(
          child,
          {
            stat: base,
            abs: pos !== 'static' || transformLike(cs) ? base : ctx.abs,
            fix: transformLike(cs) ? base : ctx.fix,
          },
          childFrame,
          // fixed/sticky subtrees ride over content by design. absolute subtrees are walked:
          // two static siblings inside an absolute panel overlapping each other is a real defect,
          // and the frame check keeps that from becoming cross-layer noise.
          colBlocked || pos === 'fixed' || pos === 'sticky',
        );
      }
    };
    walk(document.body, { stat: unclipped, abs: unclipped, fix: unclipped }, null, false);
    return { styleOf, clipOf, frameOf, collisionCandidates, escapeCandidates };
  };

  const findCollisions = (s: Scan): { hits: Collision[]; keys: string[] } => {
    // getClientRects(), not getBoundingClientRect(): a wrapped inline's bounding box spans every
    // line it touches and swallows its neighbours. Read once up front -- each call forces layout.
    const boxes: CandidateBox[] = [];
    const keys: string[] = [];
    for (const el of s.collisionCandidates) {
      keys.push(key(el));
      const clip = (s.clipOf.get(el) ?? { box: { x1: -FAR, y1: -FAR, x2: FAR, y2: FAR }, host: null }).box;
      const rects = el.getClientRects();
      const frame = s.frameOf.get(el) ?? null;
      for (let i = 0; i < rects.length; i += 1) {
        const r = rects[i];
        if (r.width < 2 || r.height < 2) continue;
        const b = intersect({ x1: r.left, y1: r.top, x2: r.right, y2: r.bottom }, clip);
        if (b.x2 - b.x1 < 2 || b.y2 - b.y1 < 2) continue;
        boxes.push({ el, frame, top: b.y1, bottom: b.y2, left: b.x1, right: b.x2 });
      }
    }
    boxes.sort((p, q) => p.top - q.top);

    // One entry per element pair: a wrapped inline overlapping a neighbour on two lines is one
    // defect, reported with its largest overlap.
    const byPair = new Map<string, Collision>();
    for (let i = 0; i < boxes.length; i += 1) {
      const a = boxes[i];
      for (let j = i + 1; j < boxes.length; j += 1) {
        const b = boxes[j];
        if (b.top >= a.bottom) break;
        if (a.el === b.el || a.el.contains(b.el) || b.el.contains(a.el)) continue;
        if (a.frame !== b.frame) continue;
        const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (w <= 0 || h <= 0) continue;
        const px = Math.round(w * h);
        if (px < config.minOverlapArea) continue;
        // Document order, so the pair's key does not depend on which line box sorted first.
        const [first, second] =
          a.el.compareDocumentPosition(b.el) & Node.DOCUMENT_POSITION_FOLLOWING ? [a.el, b.el] : [b.el, a.el];
        const keyA = key(first);
        const keyB = key(second);
        const pairKey = `${keyA} ${keyB}`;
        const prior = byPair.get(pairKey);
        if (prior && prior.area >= px) continue;
        byPair.set(pairKey, { a: label(first), b: label(second), keyA, keyB, area: px });
      }
    }
    return { hits: Array.from(byPair.values()), keys };
  };

  // Clip escapes. Geometry alone proves nothing (a scrolled-out box is outside its clip rect
  // too), so every reported escape is confirmed by elementFromPoint landing on the element.
  const slabsOutside = (r: Box, clip: Box): Box[] => {
    const band = { y1: Math.max(r.y1, clip.y1), y2: Math.min(r.y2, clip.y2) };
    return [
      { x1: r.x1, y1: r.y1, x2: r.x2, y2: Math.min(r.y2, clip.y1) },
      { x1: r.x1, y1: Math.max(r.y1, clip.y2), x2: r.x2, y2: r.y2 },
      { x1: r.x1, y1: band.y1, x2: Math.min(r.x2, clip.x1), y2: band.y2 },
      { x1: Math.max(r.x1, clip.x2), y1: band.y1, x2: r.x2, y2: band.y2 },
    ];
  };

  /**
   * Whether the element paints anything of its own. Radix ScrollArea wraps viewport children in
   * an invisible {minWidth:100%, display:table} that shrink-wraps past its clip host.
   */
  const paintable = (el: Element, cs: CSSStyleDeclaration): boolean => {
    const tag = el.tagName.toLowerCase();
    if (tag === 'svg' || tag === 'img' || tag === 'canvas' || tag === 'video' || tag === 'input' ||
        tag === 'textarea' || tag === 'select' || tag === 'hr') {
      return true;
    }
    if (ownsText(el)) return true;
    const bg = cs.backgroundColor;
    if (bg && bg !== 'transparent' && !/rgba\(\s*0,\s*0,\s*0,\s*0\s*\)/.test(bg)) return true;
    if (cs.backgroundImage && cs.backgroundImage !== 'none') return true;
    if (cs.boxShadow && cs.boxShadow !== 'none') return true;
    if ((parseFloat(cs.outlineWidth) || 0) > 0 && cs.outlineStyle !== 'none') return true;
    const border =
      (parseFloat(cs.borderTopWidth) || 0) +
      (parseFloat(cs.borderRightWidth) || 0) +
      (parseFloat(cs.borderBottomWidth) || 0) +
      (parseFloat(cs.borderLeftWidth) || 0);
    return border > 0;
  };

  const isScroller = (cs: CSSStyleDeclaration | undefined): boolean =>
    !!cs && /auto|scroll/.test(`${cs.overflowX} ${cs.overflowY}`);

  const isPageBackground = (el: Element): boolean =>
    el === document.body || el === document.documentElement;

  /** Every node from `el` up to (not including) `hit` has pointer-events:none. */
  const fellThroughTo = (el: Element, hit: Element): boolean => {
    let n: Element | null = el;
    let hops = 0;
    while (n && n !== hit && hops < 64) {
      if (getComputedStyle(n).pointerEvents !== 'none') return false;
      n = n.parentElement;
      hops += 1;
    }
    return n === hit;
  };

  const classifyHit = (el: Element, hit: Element): Escape['via'] | null => {
    if (hit === el) return 'self';
    if (el.contains(hit)) return 'descendant';
    // Must precede the page-background check: shadcn primitives put pointer-events:none on
    // their svgs, so an escaping icon resolves to its painting ancestor.
    if (hit.contains(el) && !isPageBackground(hit) && fellThroughTo(el, hit)) {
      return 'pointer-events-none-ancestor';
    }
    return null;
  };

  const findEscapes = (s: Scan): { hits: Escape[]; geometricKeys: string[]; unprobeable: number } => {
    const hits: Escape[] = [];
    const geometricKeys: string[] = [];
    let unprobeable = 0;
    const probeBand: Box = { x1: 1, y1: navbarHeightPx + 1, x2: window.innerWidth - 1, y2: window.innerHeight - 1 };

    for (const el of s.escapeCandidates) {
      const info = s.clipOf.get(el);
      const cs = s.styleOf.get(el);
      if (!info || !cs || !info.host) continue;
      const rects = el.getClientRects();
      let best: Box | null = null;
      let bestProbe: Box | null = null;
      let bestProbeSlab: Box | null = null;
      for (let i = 0; i < rects.length; i += 1) {
        const r = rects[i];
        const box: Box = { x1: r.left, y1: r.top, x2: r.right, y2: r.bottom };
        for (const slab of slabsOutside(box, info.box)) {
          // Sub-2px slivers are rounding against a pixel-snapped clip edge, not escapes.
          if (slab.x2 - slab.x1 < 2 || slab.y2 - slab.y1 < 2) continue;
          const a = area(slab);
          if (!best || a > area(best)) best = slab;
          const probeable = intersect(slab, probeBand);
          if (area(probeable) > 0 && (!bestProbe || area(probeable) > area(bestProbe))) {
            bestProbe = probeable;
            bestProbeSlab = slab;
          }
        }
      }
      if (!best || area(best) < config.minEscapeArea) continue;
      geometricKeys.push(key(el));
      if (!paintable(el, cs)) continue;
      if (!bestProbe || !bestProbeSlab) {
        // A strip nobody can probe is a blind spot, never a clean result -- except content
        // scrolled out of a scroll container, which the scroll walk brings into view.
        if (!isScroller(s.styleOf.get(info.host))) unprobeable += 1;
        continue;
      }
      const px = (bestProbe.x1 + bestProbe.x2) / 2;
      const py = (bestProbe.y1 + bestProbe.y2) / 2;
      const hit = document.elementFromPoint(px, py);
      if (!hit) {
        unprobeable += 1;
        continue;
      }
      const via = classifyHit(el, hit);
      if (!via) continue;
      hits.push({
        el: label(el),
        elKey: key(el),
        clip: label(info.host),
        escaped: toRect(bestProbeSlab),
        probe: { x: Math.round(px), y: Math.round(py) },
        hit: label(hit),
        via,
      });
    }
    return { hits, geometricKeys, unprobeable };
  };

  const measure = (): Measurement => {
    const s = scan();
    const c = findCollisions(s);
    const e = findEscapes(s);
    return {
      collisions: c.hits,
      escapes: e.hits,
      candidates: s.collisionCandidates.length,
      escapeCandidates: s.escapeCandidates.length,
      candidateKeys: c.keys,
      geometricKeys: e.geometricKeys,
      unprobeable: e.unprobeable,
    };
  };

  const findings: StateFinding[] = [];
  const stateRecords: StateRecord[] = [];
  const debugCandidates = new Set<string>();
  const debugGeometric = new Set<string>();
  let docOverflow = 0;

  const overBudget = (): boolean => {
    if (elapsed() <= config.budgetMs) return false;
    if (ledger.budgetExceededMs === null) ledger.budgetExceededMs = Math.round(elapsed());
    return true;
  };

  const timerGate = window as unknown as { __layoutFreeze?: () => void; __layoutThaw?: () => void };

  const runState = async (state: string): Promise<void> => {
    try {
      await runStateFrozen(state);
    } finally {
      // Timers deferred during the measure fire now; the next state settles after them.
      timerGate.__layoutThaw?.();
    }
  };

  const runStateFrozen = async (state: string): Promise<void> => {
    const started = performance.now();
    // Timers run while settling, so debounced handlers and query retries land first.
    const settled = await settle(config.settleCapMs, state === 'base' ? config.baseQuietMs : 0);
    timerGate.__layoutFreeze?.();
    let candidates = 0;
    let escapeCandidates = 0;
    let restabilised = false;
    let collisions: Collision[] = [];
    let escapes: Escape[] = [];

    if (settled === 'busy') {
      // Recorded, not measured: a half-rendered page reports boxes nobody could see.
      ledger.statesUnsettled.push(state);
    } else {
      const first = measure();
      candidates = first.candidates;
      escapeCandidates = first.escapeCandidates;
      collisions = first.collisions;
      escapes = first.escapes;
      ledger.unprobeable += first.unprobeable;
      ledger.geometricEscapes += first.geometricKeys.length;
      if (config.debugKeys) {
        for (const k of first.candidateKeys) debugCandidates.add(k);
        for (const k of first.geometricKeys) debugGeometric.add(k);
      }
      // Stability window: only findings that survive a re-measure are reported.
      if (collisions.length + escapes.length > 0) {
        await waitMs(config.stabilityMs);
        const second = measure();
        restabilised = true;
        const heldC = new Set(second.collisions.map((c) => `${c.keyA} ${c.keyB}`));
        const heldE = new Set(second.escapes.map((e) => e.elKey));
        collisions = collisions.filter((c) => heldC.has(`${c.keyA} ${c.keyB}`));
        escapes = escapes.filter((e) => heldE.has(e.elKey));
      }
      ledger.statesExercised.push(state);
      if (state === 'base') {
        ledger.candidates = candidates;
        ledger.escapeCandidates = escapeCandidates;
        docOverflow = Math.round(document.documentElement.scrollWidth - window.innerWidth);
      }
      if (collisions.length + escapes.length > 0) findings.push({ state, collisions, escapes });
    }

    stateRecords.push({
      state,
      candidates,
      escapeCandidates,
      elapsedMs: Math.round(performance.now() - started),
      settled,
      findings: collisions.length + escapes.length,
      restabilised,
    });
  };

  /** Own name, else nearest named ancestor plus the element's data-slot or tag. */
  const scrollerLabel = (el: Element): string => {
    const own = anchorName(el);
    if (own) return own.slice(1);
    const kind = el.getAttribute('data-slot') ?? el.tagName.toLowerCase();
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const named = anchorName(p);
      if (named) return `${named.slice(1)}>${kind}`;
    }
    return kind;
  };

  const scrollWalk = async (): Promise<void> => {
    interface Scroller {
      el: Element;
      extent: number;
      maxY: number;
      maxX: number;
      label: string;
    }
    const found: Scroller[] = [];
    const all = document.body.querySelectorAll('*');
    for (let i = 0; i < all.length; i += 1) {
      const el = all[i];
      if (el.closest(IGNORE)) continue;
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const maxY = (cs.overflowY === 'auto' || cs.overflowY === 'scroll') ? el.scrollHeight - el.clientHeight : 0;
      const maxX = (cs.overflowX === 'auto' || cs.overflowX === 'scroll') ? el.scrollWidth - el.clientWidth : 0;
      if (maxY <= 8 && maxX <= 8) continue;
      found.push({ el, extent: Math.max(maxY, maxX), maxY, maxX, label: scrollerLabel(el) });
    }
    // Two unnamed ScrollArea viewports under one anchor would otherwise share a state name,
    // and a quarantine row for one would cover the other. Suffixes follow document order.
    const seenLabels = new Map<string, number>();
    for (const sc of found) {
      const n = (seenLabels.get(sc.label) ?? 0) + 1;
      seenLabels.set(sc.label, n);
      if (n > 1) sc.label = `${sc.label}~${n}`;
    }
    ledger.scrollContainers = found.length;
    // Deepest range first: maxScrollContainers is a budget, not a sample.
    found.sort((p, q) => q.extent - p.extent);

    for (const sc of found.slice(0, config.maxScrollContainers)) {
      const el = sc.el;
      const originY = el.scrollTop;
      const originX = el.scrollLeft;
      let touched = false;
      for (const fraction of config.scrollFractions) {
        const state = `scroll:${sc.label}@${fraction}`;
        if (overBudget()) {
          ledger.statesSkipped.push(state);
          continue;
        }
        if (sc.maxY > 8) el.scrollTop = sc.maxY * fraction;
        if (sc.maxX > 8) el.scrollLeft = sc.maxX * fraction;
        touched = true;
        await runState(state);
      }
      if (touched) ledger.scrollContainersProbed += 1;
      if (!el.isConnected) {
        ledger.disconnectedAtRestore.push(sc.label);
        continue;
      }
      el.scrollTop = originY;
      el.scrollLeft = originX;
    }
  };

  await runState('base');
  if (config.states.indexOf('scroll') !== -1) await scrollWalk();

  const globals = window as unknown as { __layoutDeferred?: number };
  ledger.timersDeferred = globals.__layoutDeferred ?? 0;

  const report: LayoutReport = {
    viewport: { width: window.innerWidth, height: window.innerHeight },
    docOverflow,
    findings,
    states: stateRecords,
    ledger,
  };
  if (config.debugKeys) {
    report.debugKeys = {
      candidates: Array.from(debugCandidates),
      geometricEscapes: Array.from(debugGeometric),
    };
  }
  return report;
}
