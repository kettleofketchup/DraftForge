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
  'app.Game.radiant_team': 2,
  'app.BracketSlot.participant': 1,
};

describe('useConfirmForceReset', () => {
  afterEach(cleanup);

  it('shows the reference total and resolves true on confirm', async () => {
    render(<Harness />);
    let answer!: Promise<boolean>;
    act(() => {
      answer = confirm(references);
    });

    expect(
      screen.getByTestId('draft-force-reset-dialog').textContent,
    ).toContain(
      '3 games and other records use these teams. Resetting keeps them but rosters will change.',
    );
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
