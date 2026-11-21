// @vitest-environment jsdom
import { render as rtlRender, screen, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { GAME_TYPE } from '~/components/game/constants';
import {
  CompletedTeamDraftView,
  TeamCard,
} from '~/components/teamdraft/CompletedTeamDraftView';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { DraftRoundType, TeamType } from '~/index';
import { user } from './fixtures';

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => ({ openTeamModal: vi.fn() }),
}));

const render = (ui: ReactElement) => rtlRender(ui);

const member = user(50);
const captain = user(7);
const team = {
  pk: 1,
  name: 'T1',
  captain,
  members: [captain, member],
} as unknown as TeamType;

describe('CompletedTeamDraftView', () => {
  it('shows pick duration and skip badges from the rounds', () => {
    const rounds = [
      {
        pk: 22,
        pick_number: 5,
        captain,
        choice: member,
        pick_duration_ms: 42_000,
        skip_count: 1,
      },
    ] as unknown as DraftRoundType[];
    render(
      <CompletedTeamDraftView
        gameType={GAME_TYPE.DOTA2}
        teams={[team]}
        leaguePk={null}
        rounds={rounds}
      />,
    );
    expect(screen.getByTestId('pick-duration-50')).toHaveTextContent('0:42');
    expect(screen.getByTestId('pick-skips-50')).toHaveTextContent('skipped ×1');
    expect(screen.queryByTestId('pick-duration-7')).toBeNull();
  });

  it('renders without rounds (untimed drafts)', () => {
    render(
      <CompletedTeamDraftView
        gameType={GAME_TYPE.DOTA2}
        teams={[team]}
        leaguePk={null}
      />,
    );
    expect(screen.queryByTestId(/pick-duration-/)).toBeNull();
  });
});

describe('TeamCard roster roles and leadership flags', () => {
  const deputy = user(8);
  const standin = user(60);
  const dropout = user(61);
  const ghost = user(99);
  const roster = {
    pk: 2,
    name: 'T2',
    captain,
    deputy_captain: deputy,
    members: [captain, deputy],
    dropin_members: [standin],
    left_members: [dropout],
    leadership_problems: [],
  } as unknown as TeamType;
  const ghostTeam = {
    ...roster,
    captain: ghost,
    leadership_problems: [
      {
        field: 'captain',
        code: 'captain_not_member',
        message: 'Captain is not a member',
      },
    ],
  } as unknown as TeamType;

  const renderCard = (t: TeamType, extra: Record<string, unknown> = {}) =>
    rtlRender(
      <TooltipProvider>
        <TeamCard
          gameType={GAME_TYPE.DOTA2}
          team={t}
          rank={1}
          leaguePk={null}
          {...extra}
        />
      </TooltipProvider>,
    );

  it('marks the deputy, stand-ins and dropouts', () => {
    renderCard(roster);
    expect(
      within(screen.getByTestId('team-card-member-8')).getByTestId(
        'roster-status-deputy',
      ),
    ).toBeTruthy();
    expect(
      within(screen.getByTestId('team-card-member-7')).queryByTestId(
        'roster-status-deputy',
      ),
    ).toBeNull();
    const standinRow = screen.getByTestId('team-card-standin-60');
    expect(standinRow).toHaveTextContent('User 60');
    expect(
      within(standinRow).getByTestId('roster-status-standin'),
    ).toBeTruthy();
    const dropoutRow = screen.getByTestId('team-card-dropout-61');
    expect(dropoutRow).toHaveTextContent('User 61');
    expect(
      within(dropoutRow).getByTestId('roster-status-dropout'),
    ).toBeTruthy();
  });

  it('uses one badge family, right-aligned, for every roster role', () => {
    renderCard(roster);
    const placements = [
      ['team-card-member-7', 'roster-status-captain'],
      ['team-card-member-8', 'roster-status-deputy'],
      ['team-card-standin-60', 'roster-status-standin'],
      ['team-card-dropout-61', 'roster-status-dropout'],
    ] as const;
    for (const [row, badge] of placements) {
      const el = within(screen.getByTestId(row)).getByTestId(badge);
      expect(el.parentElement).toHaveClass('justify-end');
    }
    for (const el of screen.getAllByText('Captain')) {
      expect(el).toHaveAttribute('data-testid', 'roster-status-captain');
    }
  });

  it('shows the leadership badge only when canEdit', () => {
    const { unmount } = renderCard(ghostTeam);
    expect(screen.queryByTestId('team-leadership-problem')).toBeNull();
    unmount();
    renderCard(ghostTeam, { canEdit: true });
    expect(screen.getByTestId('team-leadership-problem')).toHaveAccessibleName(
      /User 99 is not a member of this team\./,
    );
  });

  it('shows no leadership badge for a healthy team even when canEdit', () => {
    renderCard(roster, { canEdit: true });
    expect(screen.queryByTestId('team-leadership-problem')).toBeNull();
  });

  it('resolves a {pk} stub through tournament users', () => {
    const stubbed = {
      ...roster,
      dropin_members: [{ pk: 60 }],
    } as unknown as TeamType;
    renderCard(stubbed, { tournamentUsers: [standin] });
    expect(screen.getByTestId('team-card-standin-60')).toHaveTextContent(
      'User 60',
    );
  });

  it('labels an unresolvable stub as Player #pk', () => {
    const stubbed = {
      ...roster,
      left_members: [{ pk: 77 }],
    } as unknown as TeamType;
    renderCard(stubbed, { tournamentUsers: [standin] });
    const row = screen.getByTestId('team-card-dropout-77');
    expect(row).toHaveTextContent('Player #77');
    expect(within(row).getByTestId('roster-status-dropout')).toBeTruthy();
  });
});
