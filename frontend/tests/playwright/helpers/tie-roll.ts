export interface TieRollSnapshot {
  count: number;
  visible: boolean;
  pickNumber: string | null;
  heading: string;
  winnerId: string | null;
  result: string;
  continueCount: number;
  rows: Array<{
    teamId: string;
    winner: string | null;
    face: string | null;
    text: string;
  }>;
}

export function captureTieRoll(): {
  result: Promise<TieRollSnapshot | null>;
  cancel: () => void;
} {
  let settle!: (snapshot: TieRollSnapshot | null) => void;
  const result = new Promise<TieRollSnapshot | null>((resolve) => {
    settle = resolve;
  });
  const finish = (snapshot: TieRollSnapshot | null) => {
    observer.disconnect();
    clearTimeout(timeout);
    settle(snapshot);
  };
  const capture = () => {
    const popups = document.querySelectorAll<HTMLElement>(
      '[data-testid="tie-roll-popup"]',
    );
    const popup = popups[0];
    const resultText = popup
      ?.querySelector('[data-testid="tie-roll-result"]')
      ?.textContent?.trim();
    if (!popup || !resultText?.includes('picks next')) return;
    finish({
      count: popups.length,
      visible:
        popup.getClientRects().length > 0 &&
        getComputedStyle(popup).visibility !== 'hidden',
      pickNumber: popup.getAttribute('data-pick-number'),
      heading: popup.textContent ?? '',
      winnerId: popup.getAttribute('data-winner-id'),
      result: resultText,
      continueCount: Array.from(popup.querySelectorAll('button')).filter(
        (button) =>
          /continue/i.test(
            button.getAttribute('aria-label') ?? button.textContent ?? '',
          ),
      ).length,
      rows: Array.from(
        popup.querySelectorAll('[data-testid^="tie-roll-row-"]'),
        (row) => ({
          teamId: row
            .getAttribute('data-testid')!
            .slice('tie-roll-row-'.length),
          winner: row.getAttribute('data-winner'),
          face:
            row
              .querySelector('[data-testid^="tie-roll-die-"]')
              ?.getAttribute('data-face') ?? null,
          text: row.textContent ?? '',
        }),
      ),
    });
  };
  const observer = new MutationObserver(capture);
  const timeout = setTimeout(() => finish(null), 15_000);
  observer.observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
  });
  capture();
  return { result, cancel: () => finish(null) };
}
