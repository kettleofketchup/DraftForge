// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TeamType } from '~/components/tournament/types';
import { TeamLeadershipAlert } from '../TeamLeadershipAlert';

const u = (pk: number, nickname: string) => ({
  pk,
  username: `user${pk}`,
  nickname,
});

const ghost = u(9, 'Ghost');
const alice = u(1, 'Alice');
const bob = u(2, 'Bob');

const team = (o: Partial<TeamType> & { pk: number; name: string }) =>
  ({
    members: [alice, bob],
    captain: alice,
    deputy_captain: null,
    dropin_members: [],
    left_members: [],
    leadership_problems: [],
    ...o,
  }) as unknown as TeamType;

const healthy = team({ pk: 10, name: 'Healthy' });
const ghostCaptain = team({
  pk: 11,
  name: 'Ghosted',
  captain: ghost,
  leadership_problems: [
    {
      field: 'captain',
      code: 'captain_not_member',
      message: 'Captain is not a member',
    },
  ],
} as Partial<TeamType> & { pk: number; name: string });
const doubled = team({
  pk: 12,
  name: 'Doubled',
  deputy_captain: alice,
  leadership_problems: [
    {
      field: 'deputy_captain',
      code: 'deputy_is_captain',
      message: 'Deputy is captain',
    },
  ],
} as Partial<TeamType> & { pk: number; name: string });
const noProblemsField = {
  ...healthy,
  pk: 13,
  leadership_problems: undefined,
} as TeamType;

const teams = [healthy, ghostCaptain, doubled, noProblemsField];

describe('TeamLeadershipAlert', () => {
  it('lists only affected teams with a count', () => {
    render(<TeamLeadershipAlert teams={teams} canEdit onReview={vi.fn()} />);
    const alert = screen.getByTestId('team-leadership-alert');
    expect(alert).toHaveTextContent('Teams with leadership problems (2)');
    expect(screen.getByTestId('team-leadership-alert-row-11')).toBeTruthy();
    expect(screen.getByTestId('team-leadership-alert-row-12')).toBeTruthy();
    expect(screen.queryByTestId('team-leadership-alert-row-10')).toBeNull();
    expect(screen.queryByTestId('team-leadership-alert-row-13')).toBeNull();
  });

  it('names the team and the problem in each row', () => {
    render(<TeamLeadershipAlert teams={teams} canEdit onReview={vi.fn()} />);
    const row = screen.getByTestId('team-leadership-alert-row-11');
    expect(row).toHaveTextContent('Ghosted');
    expect(row).toHaveTextContent('Ghost is not a member of this team.');
    expect(
      screen.getByTestId('team-leadership-alert-row-12'),
    ).toHaveTextContent('Alice is also the captain.');
  });

  it('renders nothing for viewers who cannot edit', () => {
    const { container } = render(
      <TeamLeadershipAlert teams={teams} canEdit={false} onReview={vi.fn()} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when no team has problems', () => {
    const { container } = render(
      <TeamLeadershipAlert
        teams={[healthy, noProblemsField]}
        canEdit
        onReview={vi.fn()}
      />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('"Review" calls onReview with the team', () => {
    const onReview = vi.fn();
    render(<TeamLeadershipAlert teams={teams} canEdit onReview={onReview} />);
    const row = screen.getByTestId('team-leadership-alert-row-12');
    fireEvent.click(within(row).getByRole('button', { name: /review/i }));
    expect(onReview).toHaveBeenCalledTimes(1);
    expect(onReview).toHaveBeenCalledWith(doubled);
  });

  it('collapses and expands the list', () => {
    render(<TeamLeadershipAlert teams={teams} canEdit onReview={vi.fn()} />);
    const toggle = screen.getByTestId('team-leadership-alert-toggle');
    fireEvent.click(toggle);
    expect(screen.queryByTestId('team-leadership-alert-row-11')).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByTestId('team-leadership-alert-row-11')).toBeTruthy();
  });
});
