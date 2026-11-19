// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { OrganizationType } from '../schemas';

const updateOrganization = vi.hoisted(() => vi.fn());
const toastError = vi.hoisted(() => vi.fn());

vi.mock('~/hooks/usePermissions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/hooks/usePermissions')>()),
  useIsOrganizationAdmin: () => true,
}));
vi.mock('../tabs/orgSettings/useOrgSettingsTabAccess', () => ({
  useOrgSettingsTabAccess: () => ({
    canView: true,
    settled: true,
    visibleSectionIds: ['staff-placement'],
  }),
}));
vi.mock('../tabs/orgSettings/StaffPlacementSection', () => ({
  StaffPlacementSection: () => <div data-testid="staff-placement-stub" />,
}));
vi.mock('~/components/admin-team', () => ({
  AdminTeamSection: () => <div data-testid="admin-team-section" />,
}));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  updateOrganization,
}));
vi.mock('sonner', () => ({
  toast: { error: toastError, success: vi.fn() },
}));

import { OrgSettingsTab } from '../tabs/OrgSettingsTab';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= vi.fn();

const org = {
  pk: 7,
  name: 'Org',
  description: '',
  logo: '',
  discord_link: '',
  discord_server_id: '',
  rules_template: '',
  timezone: 'America/New_York',
  members_private: false,
} as unknown as OrganizationType;

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <OrgSettingsTab organization={org} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

const tab = (value: string) => screen.getByTestId(`org-settings-tab-${value}`);
const isActive = (value: string) =>
  tab(value).getAttribute('data-state') === 'active';

describe('OrgSettingsTab as one settings page', () => {
  beforeEach(() => {
    updateOrganization.mockReset();
    toastError.mockClear();
  });

  it('lists the organization, admin team and settings sections in a sidebar', () => {
    renderTab();
    expect(screen.getByTestId('org-settings-sidebar')).toBeInTheDocument();
    const order = screen
      .getAllByRole('tab')
      .map((t) => t.getAttribute('data-testid'));
    expect(order).toEqual([
      'org-settings-tab-general',
      'org-settings-tab-discord',
      'org-settings-tab-members',
      'org-settings-tab-rules',
      'org-settings-tab-admins',
      'org-settings-tab-staff-placement',
    ]);
    expect(isActive('general')).toBe(true);
  });

  it('shows a save bar only after an edit, and saves the organization', async () => {
    updateOrganization.mockResolvedValue({});
    renderTab();
    expect(screen.queryByTestId('org-profile-save-bar')).toBeNull();

    fireEvent.change(screen.getByTestId('org-name-input'), {
      target: { value: 'Renamed' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('org-profile-save-bar')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId('org-profile-save'));

    await waitFor(() =>
      expect(updateOrganization).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ name: 'Renamed' }),
      ),
    );
    await waitFor(() =>
      expect(screen.queryByTestId('org-profile-save-bar')).toBeNull(),
    );
  });

  it('discards local edits', async () => {
    renderTab();
    const name = screen.getByTestId('org-name-input');
    fireEvent.change(name, { target: { value: 'Renamed' } });
    fireEvent.click(await screen.findByTestId('org-profile-discard'));
    await waitFor(() => expect(name).toHaveValue('Org'));
    expect(screen.queryByTestId('org-profile-save-bar')).toBeNull();
  });

  it('opens and marks the section of an invalid field on save', async () => {
    renderTab();
    fireEvent.change(screen.getByTestId('org-name-input'), {
      target: { value: '' },
    });
    fireEvent.mouseDown(tab('rules'), { button: 0 });
    fireEvent.click(await screen.findByTestId('org-profile-save'));
    await waitFor(() => expect(isActive('general')).toBe(true));
    expect(tab('general')).toHaveAttribute('data-invalid');
    expect(updateOrganization).not.toHaveBeenCalled();
  });

  it('mounts the admin team only when opened', () => {
    renderTab();
    expect(screen.queryByTestId('admin-team-section')).toBeNull();
    fireEvent.mouseDown(tab('admins'), { button: 0 });
    expect(screen.getByTestId('admin-team-section')).toBeInTheDocument();
  });
});
