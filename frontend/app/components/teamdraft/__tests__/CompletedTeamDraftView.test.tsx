// @vitest-environment jsdom
import { render as rtlRender, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { DraftRoundType, TeamType } from '~/index';
import { CompletedTeamDraftView } from '~/components/teamdraft/CompletedTeamDraftView';
import { user } from './fixtures';

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => ({ openTeamModal: vi.fn() }),
}));

const render = (ui: ReactElement) => rtlRender(ui);

const member = user(50);
const captain = user(7);
const team = { pk: 1, name: 'T1', captain, members: [captain, member] } as unknown as TeamType;

describe('CompletedTeamDraftView', () => {
  it('shows pick duration and skip badges from the rounds', () => {
    const rounds = [
      { pk: 22, pick_number: 5, captain, choice: member, pick_duration_ms: 42_000, skip_count: 1 },
    ] as unknown as DraftRoundType[];
    render(<CompletedTeamDraftView teams={[team]} leaguePk={null} rounds={rounds} />);
    expect(screen.getByTestId('pick-duration-50')).toHaveTextContent('0:42');
    expect(screen.getByTestId('pick-skips-50')).toHaveTextContent('skipped ×1');
    expect(screen.queryByTestId('pick-duration-7')).toBeNull();
  });

  it('renders without rounds (untimed drafts)', () => {
    render(<CompletedTeamDraftView teams={[team]} leaguePk={null} />);
    expect(screen.queryByTestId(/pick-duration-/)).toBeNull();
  });
});
