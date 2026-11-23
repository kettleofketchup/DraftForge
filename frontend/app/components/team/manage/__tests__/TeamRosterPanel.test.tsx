// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import type { ManagedTeam } from '~/components/api/teamManagementAPI';
import { TooltipProvider } from '~/components/ui/tooltip';
import { DisplayName } from '~/components/user/avatar';
import { LeadershipProblemsBanner } from '../LeadershipProblemsBanner';
import { CAPTAIN_SUCCESSION_WARNING } from '../teamActionCopy';
import { TeamRosterPanel, type PendingTeamAction } from '../TeamRosterPanel';
import {
  ghostCaptainDropoutTeam,
  ghostCaptainStandinTeam,
  ghostCaptainTeam,
  ghostDeputyTeam,
  managedTeam,
  people,
  singleMemberTeam,
} from './fixtures';

const axiosMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: axiosMock }));

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

const WARNING =
  'Ready and connected state resets for any live hero draft this team is in.';
const name = (user: { pk: number }) =>
  DisplayName(user as Parameters<typeof DisplayName>[0]);

type Props = Parameters<typeof TeamRosterPanel>[0];

function renderPanel(team: ManagedTeam, overrides: Partial<Props> = {}) {
  const onRequestAction = vi.fn<(r: PendingTeamAction) => void>();
  render(
    <TooltipProvider>
      <TeamRosterPanel
        team={team}
        pending={false}
        error={null}
        onRequestAction={onRequestAction}
        {...overrides}
      />
    </TooltipProvider>,
  );
  return onRequestAction;
}

function lastRequest(spy: ReturnType<typeof renderPanel>): PendingTeamAction {
  expect(spy).toHaveBeenCalledTimes(1);
  return spy.mock.calls[0][0];
}

function openSelect(testId: string): HTMLElement {
  fireEvent.pointerDown(screen.getByTestId(testId), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
  return screen.getByRole('listbox');
}

function pick(testId: string, label: string) {
  const listbox = openSelect(testId);
  fireEvent.click(within(listbox).getByRole('option', { name: label }));
}

function openRowMenu(pk: number): void {
  fireEvent.pointerDown(screen.getByTestId(`team-roster-actions-${pk}`), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
}

function rowAction(pk: number, label: string): HTMLElement {
  openRowMenu(pk);
  return screen.getByRole('menuitem', { name: new RegExp(`^${label}`) });
}

/** The selected leader's name in a select trigger, without the avatar. */
const selectedName = (testId: string): string | null | undefined =>
  screen.getByTestId(testId).querySelector('[data-testid="leader-option-name"]')
    ?.textContent;

const problemText = (code: string): string | null | undefined =>
  screen
    .getByTestId(`team-leadership-banner-row-${code}`)
    .querySelector('[data-testid="team-leadership-banner-text"]')?.textContent;

const banner = () => within(screen.getByTestId('team-leadership-banner'));

describe('LeadershipProblemsBanner', () => {
  it('is absent without problems', () => {
    renderPanel(managedTeam);
    expect(screen.queryByTestId('team-leadership-banner')).toBeNull();
  });

  it('names the ghost captain and offers a reseat', () => {
    const spy = renderPanel(ghostCaptainTeam);
    const captain = ghostCaptainTeam.captain!;
    expect(
      banner().getByRole('heading', { name: '1 leadership problem' }),
    ).toBeTruthy();
    expect(problemText('captain_not_member')).toBe(
      `Captain ${name(captain)} isn't on this team's roster.`,
    );
    fireEvent.click(
      banner().getByRole('button', {
        name: `Reseat ${name(captain)} as member`,
      }),
    );
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'set_captain', user: captain },
      title: 'Reseat captain?',
      summary: `Add ${name(captain)} back to the members and keep them captain`,
      confirmText: 'Reseat',
    });
  });

  it('lays out one readable row per problem on an opaque error surface', () => {
    renderPanel({
      ...ghostCaptainTeam,
      deputy_captain: people.outsider,
      leadership_problems: [
        ...ghostCaptainTeam.leadership_problems,
        ...ghostDeputyTeam.leadership_problems,
      ],
    });
    const panel = screen.getByTestId('team-leadership-banner');
    expect(panel).toHaveAttribute('role', 'alert');
    expect(panel).toHaveClass('bg-error-surface', 'text-error-tint');
    const heading = banner().getByRole('heading');
    expect(heading).toHaveTextContent('2 leadership problems');
    expect(heading).toHaveClass('text-base');
    const rows = banner().getAllByRole('listitem');
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual([
      'team-leadership-banner-row-captain_not_member',
      'team-leadership-banner-row-deputy_not_member',
    ]);
    for (const row of rows) {
      expect(
        row.querySelector('[data-testid="team-leadership-banner-avatar"]'),
      ).not.toBeNull();
      const text = row.querySelector(
        '[data-testid="team-leadership-banner-text"]',
      )!;
      expect(text).toHaveClass('text-sm');
      const actions = row.querySelector(
        '[data-testid="team-leadership-banner-actions"]',
      )!;
      expect(actions).toHaveClass('flex-col', 'sm:flex-row');
      for (const button of within(actions as HTMLElement).getAllByRole(
        'button',
      )) {
        expect(button).toHaveClass('w-full', 'min-h-11', 'sm:w-auto');
      }
    }
  });

  it('says a ghost captain who is a dropout will be restored', () => {
    const spy = renderPanel(ghostCaptainDropoutTeam);
    const captain = people.dropout;
    fireEvent.click(
      banner().getByRole('button', {
        name: `Reseat ${name(captain)} as member`,
      }),
    );
    const request = lastRequest(spy);
    expect(request.action).toEqual({ kind: 'set_captain', user: captain });
    expect(request.summary).toBe(
      `Restore ${name(captain)} (dropout) as a member and keep them captain`,
    );
  });

  it('says a ghost captain who is a stand-in will be moved', () => {
    const spy = renderPanel(ghostCaptainStandinTeam);
    const captain = people.standin;
    fireEvent.click(
      banner().getByRole('button', {
        name: `Reseat ${name(captain)} as member`,
      }),
    );
    const request = lastRequest(spy);
    expect(request.action).toEqual({ kind: 'set_captain', user: captain });
    expect(request.summary).toBe(
      `Move ${name(captain)} from stand-in to member and keep them captain`,
    );
  });

  it('"Choose another captain" focuses the select, whose pick explains the ghost', () => {
    const spy = renderPanel(ghostCaptainTeam);
    const captain = ghostCaptainTeam.captain!;
    const newCaptain = ghostCaptainTeam.members[0];
    fireEvent.click(
      banner().getByRole('button', { name: 'Choose another captain' }),
    );
    expect(document.activeElement).toBe(
      screen.getByTestId('team-manage-captain-select'),
    );
    expect(spy).not.toHaveBeenCalled();

    pick('team-manage-captain-select', name(newCaptain));
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'set_captain', user: newCaptain },
      title: 'Change captain?',
      summary: `Make ${name(newCaptain)} captain of ${ghostCaptainTeam.name}. ${name(captain)} is not a member, so they will no longer be connected to this team.`,
      confirmText: 'Make captain',
      warning: WARNING,
    });
  });

  it('offers clear and choose for a ghost deputy, with no reseat', () => {
    const spy = renderPanel(ghostDeputyTeam);
    const deputy = people.outsider;
    expect(banner().queryByRole('button', { name: /Reseat/ })).toBeNull();
    fireEvent.click(
      banner().getByRole('button', { name: 'Choose another deputy' }),
    );
    expect(document.activeElement).toBe(
      screen.getByTestId('team-manage-deputy-select'),
    );
    fireEvent.click(banner().getByRole('button', { name: 'Clear deputy' }));
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'set_deputy', user: null },
      title: 'Clear deputy?',
      summary: `Remove ${name(deputy)} as deputy captain of ${ghostDeputyTeam.name}.`,
      confirmText: 'Clear deputy',
    });
  });

  it('offers clear and choose when the deputy is the captain', () => {
    const team: ManagedTeam = {
      ...managedTeam,
      deputy_captain: people.captain,
      leadership_problems: [
        {
          field: 'deputy_captain',
          code: 'deputy_is_captain',
          message: 'The deputy captain cannot be the captain.',
        },
      ],
    };
    const spy = renderPanel(team);
    expect(problemText('deputy_is_captain')).toBe(
      `${name(people.captain)} is both captain and deputy.`,
    );
    expect(selectedName('team-manage-deputy-select')).toBe(
      `${name(people.captain)} (also captain)`,
    );
    fireEvent.click(banner().getByRole('button', { name: 'Clear deputy' }));
    expect(lastRequest(spy).action).toEqual({ kind: 'set_deputy', user: null });
  });

  it('calls the choose callbacks when rendered on its own', () => {
    const onChooseCaptain = vi.fn();
    const onChooseDeputy = vi.fn();
    const onRequestAction = vi.fn();
    render(
      <LeadershipProblemsBanner
        team={{
          ...ghostCaptainTeam,
          deputy_captain: people.outsider,
          leadership_problems: [
            ...ghostCaptainTeam.leadership_problems,
            ...ghostDeputyTeam.leadership_problems,
          ],
        }}
        onRequestAction={onRequestAction}
        onChooseCaptain={onChooseCaptain}
        onChooseDeputy={onChooseDeputy}
      />,
    );
    expect(
      banner().getByRole('heading', { name: '2 leadership problems' }),
    ).toBeTruthy();
    expect(problemText('deputy_not_member')).toBe(
      `Deputy ${name(people.outsider)} isn't on this team's roster.`,
    );
    fireEvent.click(
      banner().getByRole('button', { name: 'Choose another captain' }),
    );
    fireEvent.click(
      banner().getByRole('button', { name: 'Choose another deputy' }),
    );
    expect(onChooseCaptain).toHaveBeenCalledTimes(1);
    expect(onChooseDeputy).toHaveBeenCalledTimes(1);
    expect(onRequestAction).not.toHaveBeenCalled();
  });
});

describe('leadership selects', () => {
  it('shows a ghost captain as "(not a member)"', () => {
    renderPanel(ghostCaptainTeam);
    expect(selectedName('team-manage-captain-select')).toBe(
      `${name(ghostCaptainTeam.captain!)} (not a member)`,
    );
  });

  it('keeps the ghost captain warning icon inline with a truncating label', () => {
    renderPanel(ghostCaptainTeam);
    const value = screen
      .getByTestId('team-manage-captain-select')
      .querySelector('[data-slot=select-value]')!;
    const icon = value.querySelector('svg.lucide-triangle-alert');
    const label = value.querySelector('span.truncate');
    expect(icon).not.toBeNull();
    expect(label?.textContent).toBe(
      `${name(ghostCaptainTeam.captain!)} (not a member)`,
    );
    expect(icon!.parentElement).toBe(label!.parentElement);
  });

  it('shows a small avatar beside the selected captain and each option', () => {
    renderPanel(managedTeam);
    const trigger = screen.getByTestId('team-manage-captain-select');
    const value = trigger.querySelector('[data-slot=select-value]')!;
    const avatar = value.querySelector('[data-testid="leader-option-avatar"]');
    expect(avatar).not.toBeNull();
    expect(avatar!.querySelector('.h-4.w-4')).not.toBeNull();
    expect(selectedName('team-manage-captain-select')).toBe(
      name(people.captain),
    );
    const options = within(
      openSelect('team-manage-captain-select'),
    ).getAllByRole('option');
    expect(options).toHaveLength(3);
    for (const option of options) {
      expect(
        option.querySelector('[data-testid="leader-option-avatar"]'),
      ).not.toBeNull();
    }
    expect(
      within(screen.getByRole('listbox')).getByRole('option', {
        name: name(people.member),
      }),
    ).toBeTruthy();
  });

  it('shows avatars in the deputy select, and none on "No deputy"', () => {
    renderPanel(managedTeam);
    expect(
      screen
        .getByTestId('team-manage-deputy-select')
        .querySelector(
          '[data-slot=select-value] [data-testid="leader-option-avatar"]',
        ),
    ).not.toBeNull();
    const listbox = openSelect('team-manage-deputy-select');
    expect(
      within(listbox)
        .getByRole('option', { name: 'No deputy' })
        .querySelector('[data-testid="leader-option-avatar"]'),
    ).toBeNull();
    expect(
      within(listbox)
        .getByRole('option', { name: name(people.member) })
        .querySelector('[data-testid="leader-option-avatar"]'),
    ).not.toBeNull();
  });

  it('keeps the ghost icon, avatar and truncating name on one row', () => {
    renderPanel(ghostCaptainTeam);
    const row = screen
      .getByTestId('team-manage-captain-select')
      .querySelector('[data-slot=select-value] > span')!;
    expect(row).toHaveClass('flex', 'min-w-0', 'items-center');
    const kids = [...row.children];
    expect(kids[0].matches('svg.lucide-triangle-alert')).toBe(true);
    expect(
      kids[1].querySelector('[data-testid="leader-option-avatar"]'),
    ).not.toBeNull();
    expect(kids[2]).toHaveClass('truncate');
  });

  it('shows a ghost deputy as "(not a member)"', () => {
    renderPanel(ghostDeputyTeam);
    expect(selectedName('team-manage-deputy-select')).toBe(
      `${name(people.outsider)} (not a member)`,
    );
  });

  it('picking a member as captain requests set_captain with the warning', () => {
    const spy = renderPanel(managedTeam);
    pick('team-manage-captain-select', name(people.member));
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'set_captain', user: people.member },
      title: 'Change captain?',
      summary: `Make ${name(people.member)} captain of ${managedTeam.name}.`,
      confirmText: 'Make captain',
      warning: WARNING,
    });
  });

  it('lists members only in the captain select', () => {
    renderPanel(managedTeam);
    const options = within(openSelect('team-manage-captain-select'))
      .getAllByRole('option')
      .map(
        (o) =>
          o.querySelector('[data-testid="leader-option-name"]')?.textContent,
      );
    expect(options.sort()).toEqual(
      [people.captain, people.deputy, people.member].map(name).sort(),
    );
  });

  it('picking a member as deputy requests set_deputy', () => {
    const spy = renderPanel(managedTeam);
    pick('team-manage-deputy-select', name(people.member));
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'set_deputy', user: people.member },
      title: 'Change deputy?',
      summary: `Make ${name(people.member)} deputy captain of ${managedTeam.name}.`,
      confirmText: 'Make deputy',
    });
  });

  it('leaves the captain out of the deputy select', () => {
    renderPanel(managedTeam);
    const listbox = openSelect('team-manage-deputy-select');
    expect(
      within(listbox).queryByRole('option', { name: name(people.captain) }),
    ).toBeNull();
  });

  it('"No deputy" requests set_deputy with null', () => {
    const spy = renderPanel(managedTeam);
    pick('team-manage-deputy-select', 'No deputy');
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'set_deputy', user: null },
      title: 'Clear deputy?',
      summary: `Remove ${name(people.deputy)} as deputy captain of ${managedTeam.name}.`,
      confirmText: 'Clear deputy',
    });
  });
});

describe('roster rows', () => {
  const memberRow = (pk: number) => `team-member-row-${pk}`;

  it('hides "Make captain" on the captain', () => {
    renderPanel(managedTeam);
    openRowMenu(people.captain.pk);
    expect(screen.queryByRole('menuitem', { name: 'Make captain' })).toBeNull();
  });

  it('"Make captain" requests set_captain with the warning', () => {
    const spy = renderPanel(managedTeam);
    fireEvent.click(rowAction(people.member.pk, 'Make captain'));
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'set_captain', user: people.member },
      title: 'Change captain?',
      summary: `Make ${name(people.member)} captain of ${managedTeam.name}.`,
      confirmText: 'Make captain',
      warning: WARNING,
    });
  });

  it('"Mark dropout" on a member has no warning', () => {
    const spy = renderPanel(managedTeam);
    fireEvent.click(rowAction(people.member.pk, 'Mark dropout'));
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'mark_dropout', user: people.member },
      title: 'Mark dropout?',
      summary: `Mark ${name(people.member)} as a dropout of ${managedTeam.name}.`,
      confirmText: 'Mark dropout',
      destructive: true,
    });
  });

  it('"Mark dropout" on the captain adds the warning', () => {
    const spy = renderPanel(managedTeam);
    fireEvent.click(rowAction(people.captain.pk, 'Mark dropout'));
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'mark_dropout', user: people.captain },
      title: 'Mark dropout?',
      summary: `Mark ${name(people.captain)} as a dropout of ${managedTeam.name}.`,
      confirmText: 'Mark dropout',
      destructive: true,
      warning: CAPTAIN_SUCCESSION_WARNING,
    });
  });

  it('"Restore" on a dropout requests restore_member', () => {
    const spy = renderPanel(managedTeam);
    fireEvent.click(rowAction(people.dropout.pk, 'Restore'));
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'restore_member', user: people.dropout },
      title: 'Restore member?',
      summary: `Restore ${name(people.dropout)} as a member of ${managedTeam.name}.`,
      confirmText: 'Restore',
    });
  });

  it('"Remove" on a stand-in requests remove_standin', () => {
    const spy = renderPanel(managedTeam);
    fireEvent.click(rowAction(people.standin.pk, 'Remove stand-in'));
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'remove_standin', user: people.standin },
      title: 'Remove stand-in?',
      summary: `Remove ${name(people.standin)} from the stand-ins of ${managedTeam.name}.`,
      confirmText: 'Remove',
      destructive: true,
    });
  });

  it('"Sub in" requests sub_in with no replacement and asks for one', () => {
    const spy = renderPanel(managedTeam);
    fireEvent.click(rowAction(people.standin.pk, 'Sub in'));
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'sub_in', standin: people.standin, replacing: null },
      title: 'Sub in stand-in?',
      summary: `Sub ${name(people.standin)} into ${managedTeam.name}.`,
      confirmText: 'Sub in',
      withReplacing: true,
      replacingCaptain: {
        pk: managedTeam.captain!.pk,
        warning: CAPTAIN_SUCCESSION_WARNING,
      },
    });
  });

  it('marks stand-ins, dropouts and the deputy', () => {
    renderPanel(managedTeam);
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
    expect(
      within(screen.getByTestId(memberRow(people.deputy.pk))).getByTestId(
        'roster-status-deputy',
      ),
    ).toBeTruthy();
    expect(
      within(
        screen.getByTestId(memberRow(managedTeam.captain!.pk)),
      ).getByTestId('roster-status-captain'),
    ).toBeTruthy();
  });

  it('renders the add stand-in slot in the table toolbar', () => {
    renderPanel(managedTeam, { addStandinSlot: <span>picker slot</span> });
    expect(
      within(screen.getByTestId('team-roster-actions')).getByText(
        'picker slot',
      ),
    ).toBeTruthy();
  });

  it('keeps the leadership selects above the roster table', () => {
    renderPanel(managedTeam);
    const select = screen.getByTestId('team-manage-captain-select');
    const table = screen.getByTestId('team-roster-table');
    expect(
      select.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});

describe('panel states', () => {
  it('disables "Mark dropout" for the last member, with the reason', () => {
    const spy = renderPanel(singleMemberTeam);
    const item = rowAction(people.captain.pk, 'Mark dropout');
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(item).toHaveTextContent('A team needs at least one member');
    fireEvent.click(item);
    expect(spy).not.toHaveBeenCalled();
  });

  it('disables every action and select while pending', () => {
    renderPanel(ghostCaptainTeam, { pending: true });
    const ghostButtons = within(
      screen.getByTestId('team-leadership-banner'),
    ).getAllByRole('button');
    expect(ghostButtons.length).toBe(2);
    expectAllDisabled(ghostButtons);

    const panelButtons = actionButtons();
    expect(panelButtons.length).toBeGreaterThan(2);
    expectAllDisabled(panelButtons);
  });

  it('disables roster rows while pending', () => {
    const spy = renderPanel(managedTeam, { pending: true });
    const buttons = actionButtons().concat(screen.getAllByRole('combobox'));
    expectAllDisabled(buttons);
    buttons.forEach((b) => fireEvent.click(b));
    expect(spy).not.toHaveBeenCalled();
  });

  it('shows the error in an alert', () => {
    renderPanel(managedTeam, { error: 'Pick a member' });
    const alert = screen.getByTestId('team-manage-error');
    expect(alert.textContent).toBe('Pick a member');
    expect(alert.getAttribute('role')).toBe('alert');
  });

  it('shows no error alert without an error', () => {
    renderPanel(managedTeam);
    expect(screen.queryByTestId('team-manage-error')).toBeNull();
  });

  it('never calls the API', () => {
    const spy = renderPanel(managedTeam);
    fireEvent.click(rowAction(people.member.pk, 'Make captain'));
    fireEvent.click(rowAction(people.standin.pk, 'Sub in'));
    expect(spy).toHaveBeenCalledTimes(2);
    expect(axiosMock.get).not.toHaveBeenCalled();
    expect(axiosMock.post).not.toHaveBeenCalled();
  });
});

/** Every button except the table's sort headers, which stay usable while pending. */
function actionButtons(): HTMLElement[] {
  return screen
    .getAllByRole('button')
    .filter(
      (b) => !b.getAttribute('data-testid')?.startsWith('data-table-sort-'),
    );
}

function expectAllDisabled(elements: HTMLElement[]) {
  for (const el of elements) {
    expect((el as HTMLButtonElement).disabled, el.textContent ?? '').toBe(true);
  }
}
