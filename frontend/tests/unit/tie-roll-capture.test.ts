// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { captureTieRoll } from '../playwright/helpers/tie-roll';

function showRoll(): HTMLElement {
  document.body.innerHTML = `
    <div data-testid="tie-roll-popup" data-pick-number="2" data-winner-id="160">
      <h3>Tie for pick #2</h3>
      <div data-testid="tie-roll-row-160" data-winner="false">
        Winner <svg data-testid="tie-roll-die-160"></svg>
      </div>
      <div data-testid="tie-roll-row-161" data-winner="false">
        Runner up <svg data-testid="tie-roll-die-161"></svg>
      </div>
      <div data-testid="tie-roll-row-162" data-winner="false">Earlier loser: out</div>
      <span data-testid="tie-roll-result">Rolling…</span>
    </div>`;
  return document.querySelector<HTMLElement>('[data-testid="tie-roll-popup"]')!;
}

function finishRoll(popup: HTMLElement): void {
  popup
    .querySelector('[data-testid="tie-roll-row-160"]')!
    .setAttribute('data-winner', 'true');
  popup
    .querySelector('[data-testid="tie-roll-die-160"]')!
    .setAttribute('data-face', '6');
  popup
    .querySelector('[data-testid="tie-roll-die-161"]')!
    .setAttribute('data-face', '2');
  popup.querySelector('[data-testid="tie-roll-result"]')!.textContent =
    'Winner picks next';
}

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
});

describe('captureTieRoll', () => {
  it('retains the complete result when assertions arrive after automatic dismissal', async () => {
    const capture = captureTieRoll();
    const popup = showRoll();
    await Promise.resolve();
    finishRoll(popup);
    await Promise.resolve();
    popup.remove();
    await Promise.resolve();

    expect(document.querySelector('[data-testid="tie-roll-popup"]')).toBeNull();
    const snapshot = await capture.result;
    expect(snapshot).toMatchObject({
      count: 1,
      pickNumber: '2',
      winnerId: '160',
      result: 'Winner picks next',
      continueCount: 0,
      rows: [
        { teamId: '160', winner: 'true', face: '6' },
        { teamId: '161', winner: 'false', face: '2' },
        { teamId: '162', winner: 'false', face: null },
      ],
    });
    expect(snapshot!.heading).toContain('Tie for pick #2');
    expect(snapshot!.rows[2].text).toContain('out');
  });

  it('does not mistake an intermediate animation frame for the final scores', async () => {
    const popup = showRoll();
    const capture = captureTieRoll();
    let settled = false;
    void capture.result.then(() => {
      settled = true;
    });
    popup
      .querySelector('[data-testid="tie-roll-die-160"]')!
      .setAttribute('data-face', '1');
    await Promise.resolve();
    await Promise.resolve();
    expect(settled).toBe(false);

    finishRoll(popup);
    expect((await capture.result)!.rows[0].face).toBe('6');
  });

  it('captures an already completed popup without waiting for another mutation', async () => {
    const popup = showRoll();
    finishRoll(popup);
    const capture = captureTieRoll();
    expect((await capture.result)!.winnerId).toBe('160');
  });

  it('preserves invalid rendered values instead of inferring the expected winner', async () => {
    const popup = showRoll();
    finishRoll(popup);
    popup
      .querySelector('[data-testid="tie-roll-row-160"]')!
      .setAttribute('data-winner', 'false');
    popup
      .querySelector('[data-testid="tie-roll-die-160"]')!
      .setAttribute('data-face', '1');
    popup.insertAdjacentHTML(
      'beforeend',
      '<button aria-label="Continue"></button>',
    );
    const snapshot = await captureTieRoll().result;
    expect(snapshot!.rows[0]).toMatchObject({ winner: 'false', face: '1' });
    expect(snapshot!.continueCount).toBe(1);
  });

  it('finishes with no snapshot when the result never appears', async () => {
    vi.useFakeTimers();
    const capture = captureTieRoll();
    await vi.advanceTimersByTimeAsync(15_000);
    expect(await capture.result).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('can cancel an observer if the pick fails before any popup arrives', async () => {
    const capture = captureTieRoll();
    capture.cancel();
    const popup = showRoll();
    finishRoll(popup);
    expect(await capture.result).toBeNull();
  });
});
