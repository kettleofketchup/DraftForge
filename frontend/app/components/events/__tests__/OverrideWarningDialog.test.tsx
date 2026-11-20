// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { OverrideRequired } from '~/components/api/overridesAPI';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { OverrideWarningDialog } from '../OverrideWarningDialog';

const VIEWER = 5;

const confirmable: OverrideRequired = {
  code: 'override_required',
  blocked: false,
  violations: [
    {
      code: 'below_min_mmr',
      rule: 'staff-override',
      category: 'eligibility',
      message: "MMR 2,400 is below Roster A's 3,000 gate",
      blocking: false,
      params: {},
    },
    {
      code: 'team_standin_cap',
      rule: 'override-warning',
      category: 'team',
      message: 'Stand-in cap 2 reached',
      blocking: false,
      params: {},
    },
  ],
};

const blocked: OverrideRequired = {
  code: 'override_required',
  blocked: true,
  violations: [
    { ...confirmable.violations[0] },
    {
      code: 'over_capacity',
      rule: 'override-warning',
      category: 'seating',
      message: 'Roster A is over capacity (11/10)',
      blocking: true,
      params: {},
    },
  ],
};

function org(adminIds: number[]): OrganizationType {
  return {
    pk: 7,
    name: 'Org',
    owner_id: 1,
    admin_ids: adminIds,
    staff_ids: [VIEWER],
  } as unknown as OrganizationType;
}

function renderDialog(
  override: OverrideRequired,
  props: Partial<Parameters<typeof OverrideWarningDialog>[0]> = {},
) {
  const onConfirm = vi.fn().mockResolvedValue(undefined);
  render(
    <MemoryRouter>
      <OverrideWarningDialog
        open
        onOpenChange={vi.fn()}
        override={override}
        onConfirm={onConfirm}
        organization={org([])}
        {...props}
      />
    </MemoryRouter>,
  );
  return { onConfirm };
}

describe('OverrideWarningDialog', () => {
  beforeEach(() => {
    useUserStore.setState({
      currentUser: { pk: VIEWER, username: 'viewer' } as UserType,
    });
  });

  it('lists each violation by category label and message', () => {
    renderDialog(confirmable);
    const eligibility = screen.getByTestId(
      'override-violation-below_min_mmr-0',
    );
    expect(eligibility).toHaveTextContent(
      "Eligibility ruleMMR 2,400 is below Roster A's 3,000 gate",
    );
    expect(eligibility).not.toHaveTextContent('staff-override');
    expect(
      screen.getByTestId('override-violation-team_standin_cap-1'),
    ).toHaveTextContent('Team ruleStand-in cap 2 reached');
  });

  it('labels seating violations without the rule slug', () => {
    renderDialog(blocked);
    const row = screen.getByTestId('override-violation-over_capacity-1');
    expect(row).toHaveTextContent('Seating rule');
    expect(row).not.toHaveTextContent('override-warning');
  });

  it('renders every row when a code repeats', () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
    const capacity = {
      code: 'over_capacity',
      rule: 'override-warning',
      category: 'seating',
      blocking: false,
      params: {},
    } as const;
    renderDialog({
      code: 'override_required',
      blocked: false,
      violations: [
        { ...capacity, message: 'Roster A is over capacity (11/10)' },
        { ...capacity, message: 'Roster B is over capacity (6/5)' },
      ],
    });
    expect(
      screen.getByTestId('override-violation-over_capacity-0'),
    ).toHaveTextContent('Roster A');
    expect(
      screen.getByTestId('override-violation-over_capacity-1'),
    ).toHaveTextContent('Roster B');
    expect(errors.mock.calls.flat().join(' ')).not.toMatch(/same key/);
    errors.mockRestore();
  });

  it('requires a reason before confirming', async () => {
    const { onConfirm } = renderDialog(confirmable);
    fireEvent.change(screen.getByTestId('override-reason'), {
      target: { value: '   ' },
    });
    fireEvent.click(screen.getByTestId('override-confirm'));
    expect(await screen.findByText('A reason is required')).toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('confirms with the trimmed reason', async () => {
    const { onConfirm } = renderDialog(confirmable);
    fireEvent.change(screen.getByTestId('override-reason'), {
      target: { value: '  Known player  ' },
    });
    fireEvent.click(screen.getByTestId('override-confirm'));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith('Known player'));
  });

  it('shows a server reason error', async () => {
    renderDialog(confirmable, { reasonError: 'Server says no' });
    expect(await screen.findByText('Server says no')).toBeInTheDocument();
  });

  it('blocked: marks blocking rows, no confirm, asks an org admin', () => {
    renderDialog(blocked);
    expect(screen.queryByTestId('override-confirm')).toBeNull();
    expect(screen.queryByTestId('override-reason')).toBeNull();
    expect(
      screen.getByTestId('override-violation-over_capacity-1'),
    ).toHaveAttribute('data-blocking', 'true');
    expect(
      screen.getByTestId('override-violation-below_min_mmr-0'),
    ).toHaveAttribute('data-blocking', 'false');
    expect(screen.getAllByTestId('override-blocking-badge')).toHaveLength(1);
    expect(screen.getByTestId('override-blocked-policy')).toHaveTextContent(
      'Ask an org admin',
    );
    expect(screen.queryByTestId('override-settings-link')).toBeNull();
  });

  it('blocked: org admins get the settings link', () => {
    renderDialog(blocked, { organization: org([VIEWER]) });
    expect(screen.getByTestId('override-settings-link')).toHaveAttribute(
      'href',
      '/organizations/7?settings=staff-placement',
    );
  });
});
