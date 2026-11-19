// @vitest-environment jsdom
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { OrganizationType } from '../schemas';

const isAdmin = vi.hoisted(() => ({ current: true }));
const toastError = vi.hoisted(() => vi.fn());

vi.mock('~/hooks/usePermissions', () => ({
  useIsOrganizationAdmin: () => isAdmin.current,
}));
vi.mock('~/components/admin-team', () => ({
  AdminTeamSection: () => <div data-testid="admin-team-section" />,
}));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  updateOrganization: vi.fn(),
}));
vi.mock('sonner', () => ({
  toast: { error: toastError, success: vi.fn() },
}));

import { EditOrganizationModal } from '../forms/EditOrganizationModal';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= vi.fn();

const org = {
  pk: 3,
  name: 'Org',
  description: '',
  logo: '',
  discord_link: '',
  discord_server_id: '',
  rules_template: '',
  timezone: 'America/New_York',
  members_private: false,
} as unknown as OrganizationType;

function renderModal(organization = org) {
  return render(
    <TooltipProvider>
      <EditOrganizationModal
        open
        onOpenChange={() => {}}
        organization={organization}
      />
    </TooltipProvider>,
  );
}

const tab = (value: string) => screen.queryByTestId(`edit-org-tab-${value}`);
const isActive = (value: string) =>
  tab(value)?.getAttribute('data-state') === 'active';

describe('EditOrganizationModal', () => {
  beforeEach(() => {
    isAdmin.current = true;
    toastError.mockClear();
  });

  it('splits the form into sidebar sections, General first', () => {
    renderModal();
    expect(screen.getByTestId('edit-org-sidebar')).toBeInTheDocument();
    for (const value of ['general', 'discord', 'members', 'rules', 'admins']) {
      expect(tab(value)).toBeInTheDocument();
    }
    expect(isActive('general')).toBe(true);
    expect(screen.getByTestId('org-name-input')).toBeVisible();
  });

  it('mounts the admin team only when its section is opened', () => {
    renderModal();
    expect(screen.queryByTestId('admin-team-section')).toBeNull();
    fireEvent.mouseDown(tab('admins')!, { button: 0 });
    expect(screen.getByTestId('admin-team-section')).toBeInTheDocument();
  });

  it('hides the admin team section from non-admins', () => {
    isAdmin.current = false;
    renderModal();
    expect(tab('admins')).toBeNull();
  });

  it('opens and marks the section of an invalid field', async () => {
    renderModal({ ...org, name: '' } as OrganizationType);
    fireEvent.mouseDown(tab('rules')!, { button: 0 });
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(isActive('general')).toBe(true));
    expect(tab('general')).toHaveAttribute('data-invalid');
    expect(toastError).toHaveBeenCalled();
  });

  it('finds a setting in another section from the search box', async () => {
    renderModal();
    fireEvent.change(screen.getByTestId('edit-org-search'), {
      target: { value: 'server id' },
    });
    const hit = screen.getAllByTestId('edit-org-search-hit')[0];
    expect(hit).toHaveTextContent('Discord Server ID');
    fireEvent.click(hit);
    await act(() => new Promise((r) => requestAnimationFrame(r)));
    expect(isActive('discord')).toBe(true);
  });
});
