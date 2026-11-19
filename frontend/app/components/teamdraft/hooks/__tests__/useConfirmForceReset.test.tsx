// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { ConfirmForceReset } from '../initDraftHook';
import { useConfirmForceReset } from '../useConfirmForceReset';

let confirm: ConfirmForceReset;

function Harness() {
  const { confirmForce, confirmForceDialog } = useConfirmForceReset();
  confirm = confirmForce;
  return <TooltipProvider>{confirmForceDialog}</TooltipProvider>;
}

const references = {
  references: {
    'app.Game.radiant_team': 2,
    'app.Game.dire_team': 2,
    'app.Game.winning_team': 2,
  },
  usage: [
    {
      model: 'app.Game',
      label: 'game',
      label_plural: 'games',
      count: 2,
      teams: [
        { pk: 1, name: 'Team A' },
        { pk: 2, name: 'Team B' },
      ],
    },
    {
      model: 'app.HeroDraft',
      label: 'HeroDraft',
      label_plural: 'HeroDrafts',
      count: 1,
      teams: [{ pk: 2, name: 'Team B' }],
    },
  ],
};

describe('useConfirmForceReset', () => {
  afterEach(cleanup);

  it('shows the per-type breakdown and resolves true on confirm', async () => {
    render(<Harness />);
    let answer!: Promise<boolean>;
    act(() => {
      answer = confirm(references);
    });

    const dialog = screen.getByTestId('draft-force-reset-dialog');
    expect(dialog.textContent).toContain(
      '2 games and 1 HeroDraft use Team A and Team B.',
    );
    expect(dialog.textContent).not.toContain('6 games');
    const rows = screen.getAllByTestId('draft-force-reset-usage-row');
    expect(rows.map((r) => r.textContent)).toEqual([
      '2 gamesTeam A, Team B',
      '1 HeroDraftTeam B',
    ]);
    await act(async () => {
      fireEvent.click(screen.getByTestId('draft-force-reset-confirm'));
    });
    await expect(answer).resolves.toBe(true);
    expect(screen.queryByTestId('draft-force-reset-dialog')).toBeNull();
  });

  it('resolves false on cancel', async () => {
    render(<Harness />);
    let answer!: Promise<boolean>;
    act(() => {
      answer = confirm(references);
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('draft-force-reset-cancel'));
    });
    await expect(answer).resolves.toBe(false);
  });
});
