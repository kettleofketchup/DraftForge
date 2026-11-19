// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DraftResetReport } from '~/components/api/types';
import { TooltipProvider } from '~/components/ui/tooltip';
import { DraftResetSummaryDialog } from '../DraftResetSummaryDialog';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

const report: DraftResetReport = {
  reset_teams: [1, 2],
  reset_team_names: [
    { pk: 1, name: 'Team A' },
    { pk: 2, name: 'Team B' },
  ],
  dropped_teams: [
    {
      pk: 5,
      name: 'Old Roster',
      reason: 'captain_not_in_pool',
      captain: { pk: 50, username: 'old_cap', nickname: 'Old Cap' },
    },
    { pk: 6, name: 'Nobody', reason: 'no_captain', captain: null },
  ],
  kept_teams: [
    {
      pk: 8,
      name: 'Seeded',
      reason: 'no_captain',
      captain: null,
      usage: [
        {
          model: 'app.Game',
          label: 'game',
          label_plural: 'games',
          count: 2,
          teams: [{ pk: 8, name: 'Seeded' }],
        },
      ],
    },
  ],
  cleared_deputies: [],
};

function renderDialog(onOpenChange = vi.fn()) {
  render(
    <TooltipProvider>
      <DraftResetSummaryDialog report={report} onOpenChange={onOpenChange} />
    </TooltipProvider>,
  );
  return screen.getByTestId('draft-reset-summary');
}

describe('DraftResetSummaryDialog', () => {
  afterEach(cleanup);

  it('names dropped teams with their reason and captain', () => {
    const dropped = renderDialog().querySelector(
      '[data-testid="draft-reset-dropped"]',
    ) as HTMLElement;

    expect(dropped.textContent).toContain('Dropped (2)');
    expect(dropped.textContent).toContain('Old Roster');
    expect(dropped.textContent).toContain('Captain is not in the player pool');
    expect(dropped.textContent).toContain('Old Cap');
    expect(dropped.textContent).toContain('Nobody');
    expect(dropped.textContent).toContain('No captain');
  });

  it('says why kept teams were kept', () => {
    const kept = renderDialog().querySelector(
      '[data-testid="draft-reset-kept"]',
    ) as HTMLElement;

    expect(kept.textContent).toContain('Kept out of the draft (1)');
    expect(kept.textContent).toContain('Seeded');
    expect(kept.textContent).toContain('No captain');
    expect(kept.textContent).toContain('Kept because 2 games use it');
  });

  it('lists the reset teams and closes on demand', () => {
    const onOpenChange = vi.fn();
    const dialog = renderDialog(onOpenChange);

    expect(dialog.textContent).toContain(
      '2 teams reset to captains: Team A, Team B',
    );
    fireEvent.click(screen.getByTestId('draft-reset-summary-close'));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
