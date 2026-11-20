// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TeamHistoryPage } from '~/components/api/teamManagementAPI';
import { TooltipProvider } from '~/components/ui/tooltip';
import { DisplayName } from '~/components/user/avatar';
import { resolveLogUser } from '../resolveLogUser';
import { TeamHistoryTable, teamLogChanges } from '../TeamHistoryTable';
import {
  historyPage,
  managedTeam,
  overrideRulesOnlyRow,
  people,
  richHistoryPage,
  systemRow,
  UNRESOLVABLE_PK,
  unresolvableCaptainRow,
  violationsRow,
} from './fixtures';

const resolveUser = (pk: number) => resolveLogUser(pk, { team: managedTeam });

function renderTable(
  page: TeamHistoryPage | null = richHistoryPage,
  extra: { onNext?: () => void; onPrevious?: () => void } = {},
) {
  const onNext = extra.onNext ?? vi.fn();
  const onPrevious = extra.onPrevious ?? vi.fn();
  render(
    <TooltipProvider>
      <TeamHistoryTable
        page={page ?? undefined}
        resolveUser={resolveUser}
        onNext={onNext}
        onPrevious={onPrevious}
      />
    </TooltipProvider>,
  );
  return { onNext, onPrevious };
}

const rowFor = (id: number): HTMLElement => {
  const rows = screen.getAllByTestId('team-history-row');
  const index = richHistoryPage.results.findIndex((r) => r.id === id);
  return rows[index];
};

describe('TeamHistoryTable', () => {
  it('renders one row per entry with action labels and the reason', () => {
    renderTable(historyPage);
    const rows = screen.getAllByTestId('team-history-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Added stand-in')).toBeTruthy();
    expect(within(rows[0]).getByText('cover')).toBeTruthy();
    expect(within(rows[1]).getByText('Marked dropout')).toBeTruthy();
    expect(within(rows[1]).getByText('left early')).toBeTruthy();
  });

  it('shows the actor, the target player and the channel', () => {
    renderTable(historyPage);
    const row = screen.getAllByTestId('team-history-row')[0];
    expect(within(row).getAllByText('api_site_staff').length).toBeGreaterThan(
      0,
    );
    expect(within(row).getByText('roster_standin')).toBeTruthy();
    expect(within(row).getByText('Web')).toBeTruthy();
  });

  it('shows the absolute time in a title', () => {
    renderTable(historyPage);
    const row = screen.getAllByTestId('team-history-row')[0];
    const when = within(row).getByTestId('team-history-when');
    expect(when.getAttribute('title')).toBeTruthy();
    expect(when.getAttribute('dateTime')).toBe(
      historyPage.results[0].created_at,
    );
  });

  it('shows "System" when there is no actor', () => {
    renderTable();
    const row = rowFor(systemRow.id);
    expect(within(row).getAllByText('System').length).toBeGreaterThan(0);
    expect(within(row).getByText('Automatic captain succession')).toBeTruthy();
  });

  it('summarizes the roster change between before and after', () => {
    renderTable(historyPage);
    const [standinRow, dropoutRow] = screen.getAllByTestId('team-history-row');
    expect(within(standinRow).getByText('stand-ins: 0 -> 1')).toBeTruthy();
    expect(within(dropoutRow).getByText('members: 4 -> 3')).toBeTruthy();
    expect(within(dropoutRow).getByText('dropouts: 0 -> 1')).toBeTruthy();
  });

  it('resolves captain pks and falls back to "Player #<pk>"', () => {
    renderTable();
    const row = rowFor(unresolvableCaptainRow.id);
    expect(
      within(row).getByText(
        `captain: ${DisplayName(people.captain)} -> Player #${UNRESOLVABLE_PK}`,
      ),
    ).toBeTruthy();
  });

  it('shows override badges from details.violations', () => {
    renderTable();
    const row = rowFor(violationsRow.id);
    const badge = within(row).getByTestId('team-history-override');
    expect(badge.textContent).toContain('override-warning');
    expect(badge.getAttribute('aria-label')).toContain(
      'The team already has 1 stand-ins (limit 1).',
    );
  });

  it('falls back to override_rules codes when there are no violations', () => {
    renderTable();
    const row = rowFor(overrideRulesOnlyRow.id);
    const badge = within(row).getByTestId('team-history-override');
    expect(badge.textContent).toContain('team_standin_cap');
  });

  it('shows no override badge for an ordinary change', () => {
    renderTable(historyPage);
    expect(screen.queryByTestId('team-history-override')).toBeNull();
  });

  it('shows the total count', () => {
    renderTable();
    expect(screen.getByText('6 changes')).toBeTruthy();
  });

  it('disables both pager buttons on a single page', () => {
    renderTable();
    expect(screen.getByTestId('team-history-prev')).toBeDisabled();
    expect(screen.getByTestId('team-history-next')).toBeDisabled();
  });

  it('calls onNext and onPrevious when more pages exist', () => {
    const { onNext, onPrevious } = renderTable({
      ...historyPage,
      count: 60,
      next: '/api/teams/1/history/?page=3',
      previous: '/api/teams/1/history/?page=1',
    });
    fireEvent.click(screen.getByTestId('team-history-next'));
    fireEvent.click(screen.getByTestId('team-history-prev'));
    expect(onNext).toHaveBeenCalledTimes(1);
    expect(onPrevious).toHaveBeenCalledTimes(1);
  });

  it('shows the empty state', () => {
    renderTable({ count: 0, next: null, previous: null, results: [] });
    expect(screen.getByText('No changes recorded yet.')).toBeTruthy();
    expect(screen.queryByTestId('team-history-row')).toBeNull();
  });

  it('shows a loading line before the first page arrives', () => {
    renderTable(null);
    expect(screen.getByText('Loading history…')).toBeTruthy();
  });
});

describe('teamLogChanges', () => {
  it('returns nothing when the snapshots are missing or malformed', () => {
    expect(teamLogChanges({}, resolveUser)).toEqual([]);
    expect(
      teamLogChanges({ before: 'x', after: { captain_id: 2 } }, resolveUser),
    ).toEqual([]);
  });

  it('reports renames and a cleared deputy', () => {
    const before = {
      name: 'Old',
      captain_id: 2,
      deputy_captain_id: 3,
      member_ids: [2, 3],
    };
    const after = { ...before, name: 'New', deputy_captain_id: null };
    expect(teamLogChanges({ before, after }, resolveUser)).toEqual([
      'name: Old -> New',
      `deputy: ${DisplayName(people.deputy)} -> none`,
    ]);
  });
});
