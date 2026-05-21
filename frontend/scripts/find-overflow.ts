// frontend/scripts/find-overflow.ts

/**
 * Result entry for one element that overflows the viewport.
 * Exposed as a plain object so it survives `page.evaluate()` serialization.
 */
export interface OverflowOffender {
  domPath: string;
  tagName: string;
  className: string;
  dataTestid: string | null;
  overshootPx: number;
  rectRight: number;
  viewportWidth: number;
  width: string;
  minWidth: string;
  transform: string;
  position: string;
}

/**
 * Browser-side: walk `document.body` and return every element whose right
 * edge exceeds `document.documentElement.clientWidth`, skipping elements
 * bounded by a scrollable ancestor (their overflow is intentional).
 *
 * Pasteable into DevTools console: `await findOverflow()` then JSON.stringify.
 * Callable from Playwright: `await page.evaluate(findOverflow)`.
 */
export function findOverflow(): OverflowOffender[] {
  const root = document.body;
  const viewportWidth = document.documentElement.clientWidth;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);

  function isBoundedByScrollableAncestor(el: Element): boolean {
    let cur: Element | null = el.parentElement;
    while (cur && cur !== document.body) {
      const style = window.getComputedStyle(cur);
      if (
        style.overflowX === 'auto' ||
        style.overflowX === 'hidden' ||
        style.overflowX === 'scroll'
      ) {
        return true;
      }
      cur = cur.parentElement;
    }
    return false;
  }

  function describePath(el: Element): string {
    const parts: string[] = [];
    let cur: Element | null = el;
    while (cur && cur !== document.body && parts.length < 6) {
      const tag = cur.tagName.toLowerCase();
      const cls = cur.className && typeof cur.className === 'string'
        ? '.' + cur.className.split(/\s+/).slice(0, 2).join('.')
        : '';
      parts.unshift(`${tag}${cls}`);
      cur = cur.parentElement;
    }
    return 'body > ' + parts.join(' > ');
  }

  const offenders: OverflowOffender[] = [];
  let node: Node | null = walker.currentNode;
  while (node) {
    const el = node as Element;
    if (el !== root) {
      const rect = el.getBoundingClientRect();
      if (rect.right > viewportWidth && !isBoundedByScrollableAncestor(el)) {
        const style = window.getComputedStyle(el);
        offenders.push({
          domPath: describePath(el),
          tagName: el.tagName.toLowerCase(),
          className: typeof el.className === 'string' ? el.className : '',
          dataTestid: el.getAttribute('data-testid'),
          overshootPx: Math.round(rect.right - viewportWidth),
          rectRight: Math.round(rect.right),
          viewportWidth,
          width: style.width,
          minWidth: style.minWidth,
          transform: style.transform,
          position: style.position,
        });
      }
    }
    node = walker.nextNode();
  }
  offenders.sort((a, b) => b.overshootPx - a.overshootPx);
  return offenders;
}
