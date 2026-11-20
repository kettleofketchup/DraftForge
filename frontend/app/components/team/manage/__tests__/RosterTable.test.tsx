// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import type { ManagedTeam } from '~/components/api/teamManagementAPI';
import { setViewportWidth } from '~/components/ui/data-table/__tests__/viewport';
import { DisplayName } from '~/components/user/avatar';
import type { PendingTeamAction } from '../pendingTeamAction';
import { buildRosterRows, type RosterColumnId } from '../rosterColumns';
import { RosterTable } from '../RosterTable';
import {
  ghostCaptainStandinTeam,
  managedTeam,
  people,
  singleMemberTeam,
} from './fixtures';

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

afterEach(cleanup);

const name = (user: { pk: number }) =>
  DisplayName(user as Parameters<typeof DisplayName>[0]);

function renderTable(
  team: ManagedTeam = managedTeam,
  props: { pending?: boolean; columns?: readonly RosterColumnId[] } = {},
) {
  const onRequestAction = vi.fn<(r: PendingTeamAction) => void>();
  render(
    <RosterTable
      team={team}
      pending={props.pending ?? false}
      columns={props.columns}
      onRequestAction={onRequestAction}
      toolbarActions={<span>picker slot</span>}
    />,
  );
  return onRequestAction;
}

const rowIds = () =>
  within(screen.getByTestId('team-roster-table'))
    .getAllByRole('row')
    .slice(1)
    .map((r) => r.getAttribute('data-testid'));

function openActions(pk: number): string[] {
  fireEvent.pointerDown(screen.getByTestId(`team-roster-actions-${pk}`), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
  return screen.getAllByRole('menuitem').map((i) => i.textContent ?? '');
}

describe('buildRosterRows', () => {
  it('lists members, then stand-ins, then dropouts, one row per user', () => {
    const rows = buildRosterRows(managedTeam);
    expect(rows.map((r) => [r.user.pk, r.status])).toEqual([
      [people.captain.pk, 'member'],
      [people.deputy.pk, 'member'],
      [people.member.pk, 'member'],
      [people.standin.pk, 'standin'],
      [people.dropout.pk, 'dropout'],
    ]);
    expect(rows[0].isCaptain).toBe(true);
    expect(rows[1].isDeputy).toBe(true);
  });

  it('marks a captain who sits on the stand-ins', () => {
    const standin = buildRosterRows(ghostCaptainStandinTeam).find(
      (r) => r.status === 'standin',
    )!;
    expect(standin.isCaptain).toBe(true);
  });
});

describe('RosterTable', () => {
  it('renders one row per user with the existing row test ids', () => {
    renderTable();
    expect(rowIds()).toEqual([
      `team-member-row-${people.captain.pk}`,
      `team-member-row-${people.deputy.pk}`,
      `team-member-row-${people.member.pk}`,
      `team-standin-row-${people.standin.pk}`,
      `team-dropout-row-${people.dropout.pk}`,
    ]);
  });

  it('shows the player with avatar and the role badges', () => {
    renderTable();
    const captain = within(
      screen.getByTestId(`team-member-row-${people.captain.pk}`),
    );
    expect(captain.getByText(name(people.captain))).toBeTruthy();
    expect(captain.getByTestId('roster-status-captain')).toBeTruthy();
    expect(
      within(
        screen.getByTestId(`team-member-row-${people.deputy.pk}`),
      ).getByTestId('roster-status-deputy'),
    ).toBeTruthy();
    expect(
      within(
        screen.getByTestId(`team-member-row-${people.member.pk}`),
      ).getByText('Member'),
    ).toBeTruthy();
    expect(
      within(
        screen.getByTestId(`team-standin-row-${people.standin.pk}`),
      ).getByTestId('roster-status-standin'),
    ).toBeTruthy();
    expect(
      within(
        screen.getByTestId(`team-dropout-row-${people.dropout.pk}`),
      ).getByTestId('roster-status-dropout'),
    ).toBeTruthy();
  });

  it('stacks MMR under the name for phones', () => {
    renderTable();
    const row = screen.getByTestId(`team-member-row-${people.member.pk}`);
    const stacked = within(row).getByTestId(
      `team-roster-mmr-stacked-${people.member.pk}`,
    );
    expect(stacked).toHaveClass('sm:hidden');
    expect(stacked).toHaveTextContent('3,000 MMR');
  });

  it('treats a zero MMR as not set', () => {
    renderTable({
      ...managedTeam,
      members: managedTeam.members.map((m) => ({ ...m, mmr: 0 })),
    });
    const row = screen.getByTestId(`team-member-row-${people.member.pk}`);
    expect(
      within(row).queryByTestId(`team-roster-mmr-stacked-${people.member.pk}`),
    ).toBeNull();
    expect(within(row).getAllByRole('cell')[2]).toHaveTextContent('—');
  });

  it('takes a custom column list', () => {
    renderTable(managedTeam, { columns: ['player', 'actions'] });
    const head = within(screen.getByTestId('team-roster-table'))
      .getAllByRole('columnheader')
      .map((h) => h.textContent);
    expect(head).toEqual(['Player', 'Actions']);
  });

  it('renders the toolbar slot and counts', () => {
    renderTable();
    const bar = screen.getByTestId('team-roster-actions');
    expect(bar).toHaveTextContent('3 members · 1 stand-in · 1 dropout');
    expect(within(bar).getByText('picker slot')).toBeTruthy();
  });

  it('re-sorts by player name', () => {
    renderTable();
    fireEvent.click(screen.getByTestId('data-table-sort-player'));
    expect(rowIds()[0]).toBe(`team-member-row-${people.captain.pk}`);
    expect(rowIds()).toContain(`team-dropout-row-${people.dropout.pk}`);
    const sorted = buildRosterRows(managedTeam)
      .map((r) => r.user)
      .sort((a, b) => name(a).localeCompare(name(b)))
      .map((u) => u.pk);
    expect(rowIds().map((id) => Number(id!.split('-').pop()))).toEqual(sorted);
  });
});

describe('row actions', () => {
  it('offers captain, deputy and dropout actions on a member', () => {
    renderTable();
    expect(openActions(people.member.pk)).toEqual([
      'Make captain',
      'Make deputy',
      'Mark dropout',
    ]);
  });

  it('offers no captain action on the captain', () => {
    renderTable();
    expect(openActions(people.captain.pk)).toEqual(['Mark dropout']);
  });

  it('offers to clear the deputy on the deputy', () => {
    renderTable();
    expect(openActions(people.deputy.pk)).toEqual([
      'Make captain',
      'Clear deputy',
      'Mark dropout',
    ]);
  });

  it('offers sub in and remove on a stand-in, restore on a dropout', () => {
    renderTable();
    expect(openActions(people.standin.pk)).toEqual([
      'Sub in',
      'Remove stand-in',
    ]);
    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
    expect(openActions(people.dropout.pk)).toEqual(['Restore']);
  });

  it.each([
    ['make-captain', people.member, 'set_captain', 'Change captain?'],
    ['make-deputy', people.member, 'set_deputy', 'Change deputy?'],
    ['clear-deputy', people.deputy, 'set_deputy', 'Clear deputy?'],
    ['mark-dropout', people.member, 'mark_dropout', 'Mark dropout?'],
    ['sub-in', people.standin, 'sub_in', 'Sub in stand-in?'],
    ['remove-standin', people.standin, 'remove_standin', 'Remove stand-in?'],
    ['restore', people.dropout, 'restore_member', 'Restore member?'],
  ])('%s requests %s', (action, user, kind, title) => {
    const spy = renderTable();
    openActions(user.pk);
    fireEvent.click(screen.getByTestId(`team-roster-${action}-${user.pk}`));
    expect(spy).toHaveBeenCalledTimes(1);
    const request = spy.mock.calls[0][0];
    expect(request.action.kind).toBe(kind);
    expect(request.title).toBe(title);
  });

  it('keeps "Mark dropout" disabled with its reason on the last member', () => {
    const spy = renderTable(singleMemberTeam);
    openActions(people.captain.pk);
    const item = screen.getByTestId(
      `team-roster-mark-dropout-${people.captain.pk}`,
    );
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(item).toHaveTextContent('A team needs at least one member');
    fireEvent.click(item);
    expect(spy).not.toHaveBeenCalled();
  });

  it('disables every row menu while pending', () => {
    renderTable(managedTeam, { pending: true });
    for (const pk of [2, 3, 4, 12, 5]) {
      expect(screen.getByTestId(`team-roster-actions-${pk}`)).toBeDisabled();
    }
  });

  it('names the player on each menu trigger', () => {
    renderTable();
    expect(
      screen.getByTestId(`team-roster-actions-${people.member.pk}`),
    ).toHaveAccessibleName(`Actions for ${name(people.member)}`);
  });
});

describe('row actions by viewport', () => {
  let restore: () => void = () => undefined;
  afterEach(() => restore());

  const inlineLabels = (pk: number): string[] =>
    within(screen.getByTestId(`team-roster-actions-${pk}`))
      .getAllByRole('button')
      .map((b) => b.textContent ?? '');

  it('shows inline buttons and no menu trigger from md up', () => {
    restore = setViewportWidth(1024);
    renderTable();
    expect(inlineLabels(people.member.pk)).toEqual([
      'Make captain',
      'Make deputy',
      'Mark dropout',
    ]);
    expect(inlineLabels(people.standin.pk)).toEqual([
      'Sub in',
      'Remove stand-in',
    ]);
    expect(inlineLabels(people.dropout.pk)).toEqual(['Restore']);
    expect(
      screen.queryAllByRole('button', { name: /^Actions for / }),
    ).toHaveLength(0);
  });

  it('runs an inline action by its test id', () => {
    restore = setViewportWidth(1024);
    const spy = renderTable();
    fireEvent.click(
      screen.getByTestId(`team-roster-make-captain-${people.member.pk}`),
    );
    expect(spy.mock.calls[0][0].action.kind).toBe('set_captain');
  });

  it('keeps the last-member dropout disabled inline, with its reason', () => {
    restore = setViewportWidth(1024);
    const spy = renderTable(singleMemberTeam);
    const button = screen.getByTestId(
      `team-roster-mark-dropout-${people.captain.pk}`,
    );
    expect(button).toBeDisabled();
    expect(button.parentElement).toHaveAccessibleDescription(
      'A team needs at least one member',
    );
    fireEvent.click(button);
    expect(spy).not.toHaveBeenCalled();
  });

  it('disables the inline buttons while pending', () => {
    restore = setViewportWidth(1024);
    renderTable(managedTeam, { pending: true });
    for (const b of within(
      screen.getByTestId(`team-roster-actions-${people.member.pk}`),
    ).getAllByRole('button')) {
      expect(b).toBeDisabled();
    }
  });

  it('shows only the menu below md', () => {
    restore = setViewportWidth(390);
    renderTable();
    expect(
      screen.getByTestId(`team-roster-actions-${people.member.pk}`),
    ).toHaveAccessibleName(`Actions for ${name(people.member)}`);
    expect(
      screen.queryByTestId(`team-roster-make-captain-${people.member.pk}`),
    ).toBeNull();
  });
});
