// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import {
  getOrgSettings,
  type OrgSettings,
} from '~/components/api/orgSettingsAPI';
import type { OrganizationType } from '~/components/organization/schemas';
import { OrgSettingsTab } from '~/components/organization/tabs/OrgSettingsTab';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';

vi.mock('~/components/api/orgSettingsAPI', async () => {
  const actual = await vi.importActual<
    typeof import('~/components/api/orgSettingsAPI')
  >('~/components/api/orgSettingsAPI');
  return { ...actual, getOrgSettings: vi.fn(), patchOrgSettings: vi.fn() };
});
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

const CODES = [
  'gate_outside',
  'gate_out_of_range',
  'over_capacity',
  'special_seat_role_mismatch',
  'maybe_special_seat',
  'maybe_forced_main',
];

const SETTINGS: OrgSettings = {
  organization: 7,
  staff_override_policy: 'silent',
  staff_override_warning_codes: [...CODES],
  available_warning_codes: CODES.map((code) => ({
    code,
    label: `Label ${code}`,
  })),
  updated_at: '2026-11-17T12:00:00Z',
};

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

beforeEach(() => {
  vi.mocked(getOrgSettings).mockResolvedValue(SETTINGS);
});

afterEach(() => {
  cleanup();
  vi.mocked(getOrgSettings).mockReset();
});

describe('OrgSettingsTab', () => {
  const VIEWER = 5;

  function renderTab(overrides: Partial<OrganizationType>) {
    useUserStore.setState({
      currentUser: { pk: VIEWER, username: 'viewer' } as UserType,
    });
    const organization = {
      pk: 7,
      name: 'Org',
      owner_id: 1,
      admin_ids: [],
      staff_ids: [],
      members_viewer_pk: VIEWER,
      ...overrides,
    } as OrganizationType;
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <OrgSettingsTab organization={organization} />
        </QueryClientProvider>
      </MemoryRouter>,
    );
  }

  it('renders the staff placement section for an admin', async () => {
    renderTab({ admin_ids: [VIEWER] });
    expect(screen.getByTestId('org-settings-tab')).toBeInTheDocument();
    expect(
      await screen.findByTestId('org-settings-policy-select'),
    ).toBeInTheDocument();
    expect(getOrgSettings).toHaveBeenCalledWith(7);
  });

  it('renders no section for org staff', () => {
    renderTab({ staff_ids: [VIEWER] });
    expect(screen.getByTestId('org-settings-tab')).toBeInTheDocument();
    expect(
      screen.queryByTestId('org-settings-staff-placement'),
    ).not.toBeInTheDocument();
    expect(getOrgSettings).not.toHaveBeenCalled();
  });
});
