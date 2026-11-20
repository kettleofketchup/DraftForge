// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import type { ManagedTeam } from '~/components/api/teamManagementAPI';
import { TooltipProvider } from '~/components/ui/tooltip';
import { DisplayName } from '~/components/user/avatar';
import { LeadershipProblemsBanner } from '../LeadershipProblemsBanner';
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

function rowButton(rowTestId: string, label: string): HTMLButtonElement {
  return within(screen.getByTestId(rowTestId)).getByRole('button', {
    name: label,
  }) as HTMLButtonElement;
}

const banner = () => within(screen.getByTestId('team-leadership-banner'));

describe('LeadershipProblemsBanner', () => {
  it('is absent without problems', () => {
    renderPanel(managedTeam);
    expect(screen.queryByTestId('team-leadership-banner')).toBeNull();
  });

  it('names the ghost captain and offers a reseat', () => {
    const spy = renderPanel(ghostCaptainTeam);
    const captain = ghostCaptainTeam.captain!;
    expect(banner().getByText('Leadership problems (1)')).toBeTruthy();
    expect(
      banner().getByText(`${name(captain)} is not a member of this team.`),
    ).toBeTruthy();
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
    expect(
      banner().getByText(`${name(people.captain)} is also the captain.`),
    ).toBeTruthy();
    expect(screen.getByTestId('team-manage-deputy-select').textContent).toBe(
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
    expect(banner().getByText('Leadership problems (2)')).toBeTruthy();
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
    expect(screen.getByTestId('team-manage-captain-select').textContent).toBe(
      `${name(ghostCaptainTeam.captain!)} (not a member)`,
    );
  });

  it('shows a ghost deputy as "(not a member)"', () => {
    renderPanel(ghostDeputyTeam);
    expect(screen.getByTestId('team-manage-deputy-select').textContent).toBe(
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
      .map((o) => o.textContent);
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
    expect(
      within(screen.getByTestId(memberRow(people.captain.pk))).queryByRole(
        'button',
        { name: 'Make captain' },
      ),
    ).toBeNull();
  });

  it('"Make captain" requests set_captain with the warning', () => {
    const spy = renderPanel(managedTeam);
    fireEvent.click(rowButton(memberRow(people.member.pk), 'Make captain'));
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
    fireEvent.click(rowButton(memberRow(people.member.pk), 'Mark dropout'));
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
    fireEvent.click(rowButton(memberRow(people.captain.pk), 'Mark dropout'));
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'mark_dropout', user: people.captain },
      title: 'Mark dropout?',
      summary: `Mark ${name(people.captain)} as a dropout of ${managedTeam.name}.`,
      confirmText: 'Mark dropout',
      destructive: true,
      warning: WARNING,
    });
  });

  it('"Restore" on a dropout requests restore_member', () => {
    const spy = renderPanel(managedTeam);
    fireEvent.click(
      rowButton(`team-dropout-row-${people.dropout.pk}`, 'Restore'),
    );
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'restore_member', user: people.dropout },
      title: 'Restore member?',
      summary: `Restore ${name(people.dropout)} as a member of ${managedTeam.name}.`,
      confirmText: 'Restore',
    });
  });

  it('"Remove" on a stand-in requests remove_standin', () => {
    const spy = renderPanel(managedTeam);
    fireEvent.click(
      rowButton(`team-standin-row-${people.standin.pk}`, 'Remove'),
    );
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
    fireEvent.click(
      rowButton(`team-standin-row-${people.standin.pk}`, 'Sub in'),
    );
    expect(lastRequest(spy)).toEqual({
      action: { kind: 'sub_in', standin: people.standin, replacing: null },
      title: 'Sub in stand-in?',
      summary: `Sub ${name(people.standin)} into ${managedTeam.name}.`,
      confirmText: 'Sub in',
      withReplacing: true,
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
  });

  it('renders the add stand-in slot', () => {
    renderPanel(managedTeam, { addStandinSlot: <span>picker slot</span> });
    expect(screen.getByText('picker slot')).toBeTruthy();
  });
});

describe('panel states', () => {
  it('disables "Mark dropout" for the last member, with a tooltip', async () => {
    const spy = renderPanel(singleMemberTeam);
    const button = rowButton(
      `team-member-row-${people.captain.pk}`,
      'Mark dropout',
    );
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(spy).not.toHaveBeenCalled();
    fireEvent.focus(button.parentElement!);
    expect(
      (await screen.findAllByText('A team needs at least one member')).length,
    ).toBeGreaterThan(0);
  });

  it('disables every action and select while pending', () => {
    renderPanel(ghostCaptainTeam, { pending: true });
    const ghostButtons = within(
      screen.getByTestId('team-leadership-banner'),
    ).getAllByRole('button');
    expect(ghostButtons.length).toBe(2);
    expectAllDisabled(ghostButtons);

    const panelButtons = screen.getAllByRole('button');
    expect(panelButtons.length).toBeGreaterThan(2);
    expectAllDisabled(panelButtons);
  });

  it('disables roster rows while pending', () => {
    const spy = renderPanel(managedTeam, { pending: true });
    const buttons = screen
      .getAllByRole('button')
      .concat(screen.getAllByRole('combobox'));
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
    fireEvent.click(
      rowButton(`team-member-row-${people.member.pk}`, 'Make captain'),
    );
    fireEvent.click(
      rowButton(`team-standin-row-${people.standin.pk}`, 'Sub in'),
    );
    expect(spy).toHaveBeenCalledTimes(2);
    expect(axiosMock.get).not.toHaveBeenCalled();
    expect(axiosMock.post).not.toHaveBeenCalled();
  });
});

function expectAllDisabled(elements: HTMLElement[]) {
  for (const el of elements) {
    expect((el as HTMLButtonElement).disabled, el.textContent ?? '').toBe(true);
  }
}
