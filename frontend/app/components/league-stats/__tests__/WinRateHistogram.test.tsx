// @vitest-environment jsdom
import { act, cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { LeagueDistribution } from '~/features/league-stats/schemas';
import { WinRateHistogram } from '../WinRateHistogram';

afterEach(cleanup);

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

const COUNTS = [1, 0, 2, 4, 8, 12, 9, 5, 2, 1];

const distribution: LeagueDistribution = {
  bucket_size: 10,
  buckets: COUNTS.map((count, i) => ({ min: i * 10, max: (i + 1) * 10, count })),
};

const POPULATION = COUNTS.reduce((a, b) => a + b, 0);

function renderHistogram(
  props: Partial<React.ComponentProps<typeof WinRateHistogram>> = {},
) {
  return render(
    <TooltipProvider>
      <WinRateHistogram
        distribution={distribution}
        population={POPULATION}
        minGames={5}
        highlightBucket={5}
        {...props}
      />
    </TooltipProvider>,
  );
}

function bars(): HTMLElement[] {
  return within(screen.getByTestId('win-rate-histogram')).getAllByTestId(
    'histogram-bar',
  );
}

describe('WinRateHistogram', () => {
  it('bars are focusable with a tooltip', async () => {
    renderHistogram();
    const all = bars();
    expect(all).toHaveLength(10);
    for (const bar of all) expect(bar.tabIndex).toBe(0);
    act(() => all[5].focus());
    const tooltip = await screen.findByRole('tooltip');
    expect(tooltip.textContent).toBe('50–60%: 12 players');
  });

  it('highlights bucket 9', () => {
    renderHistogram({ highlightBucket: 9 });
    const root = screen.getByTestId('win-rate-histogram');
    const highlighted = root.querySelectorAll('[data-highlighted="true"]');
    expect(highlighted).toHaveLength(1);
    expect(bars()[9].contains(highlighted[0])).toBe(true);
    expect(root.textContent).toContain('bucket 90–100%');
    const label = screen.getByText('this player');
    expect(label.className).toContain('col-start-10');
    expect(label.className).toContain('justify-self-end');
  });

  it('highlights bucket 0', () => {
    renderHistogram({ highlightBucket: 0 });
    const root = screen.getByTestId('win-rate-histogram');
    const highlighted = root.querySelectorAll('[data-highlighted="true"]');
    expect(highlighted).toHaveLength(1);
    expect(bars()[0].contains(highlighted[0])).toBe(true);
    expect(root.textContent).toContain('bucket 0–10%');
    const label = screen.getByText('this player');
    expect(label.className).toContain('col-start-1');
    expect(label.className).toContain('justify-self-start');
  });

  it('no highlight when unranked', () => {
    renderHistogram({ highlightBucket: null });
    const root = screen.getByTestId('win-rate-histogram');
    expect(root.querySelectorAll('[data-highlighted="true"]')).toHaveLength(0);
    expect(root.textContent).toContain('not ranked yet');
    expect(screen.queryByText('this player')).toBeNull();
  });

  it('population 0 shows "No ranked players yet" and no bars', () => {
    renderHistogram({
      population: 0,
      highlightBucket: null,
      distribution: {
        bucket_size: 10,
        buckets: COUNTS.map((_, i) => ({ min: i * 10, max: (i + 1) * 10, count: 0 })),
      },
    });
    const root = screen.getByTestId('win-rate-histogram');
    expect(root.textContent).toContain('No ranked players yet');
    expect(within(root).queryAllByTestId('histogram-bar')).toHaveLength(0);
  });

  it('title interpolates minGames=3', () => {
    renderHistogram({ minGames: 3 });
    const root = screen.getByTestId('win-rate-histogram');
    expect(root.textContent).toContain(
      `Win-rate distribution · ${POPULATION} ranked players (≥3 games)`,
    );
    expect(root.textContent).not.toContain('≥5');
  });

  it('empty buckets render a baseline tick, non-empty a scaled bar', () => {
    renderHistogram();
    const [, second, , , , sixth] = bars();
    const tick = second.querySelector('[data-empty="true"]') as HTMLElement;
    expect(tick).not.toBeNull();
    expect(tick.className).toContain('bg-border');
    const fill = sixth.querySelector('[data-fill]') as HTMLElement;
    expect(fill.getAttribute('height')).toBe('100%');
    const third = bars()[2].querySelector('[data-fill]') as Element;
    expect(third.getAttribute('height')).toBe(`${(2 / 12) * 100}%`);
  });

  it('centres the label on a middle bucket', () => {
    renderHistogram({ highlightBucket: 4 });
    const label = screen.getByText('this player');
    expect(label.className).toContain('col-start-5');
    expect(label.className).toContain('justify-self-center');
  });

  it('renders without inline styles', () => {
    renderHistogram();
    const root = screen.getByTestId('win-rate-histogram');
    expect(root.querySelectorAll('[style]')).toHaveLength(0);
  });

  it('sr-only table has 10 rows', () => {
    renderHistogram();
    const table = screen.getByRole('table');
    expect(table.className).toContain('sr-only');
    expect(within(table).getAllByRole('row').slice(1)).toHaveLength(10);
  });
});
