// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { toast } from 'sonner';
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
  orgSettingsKey,
  patchOrgSettings,
  type OrgSettings,
} from '~/components/api/orgSettingsAPI';
import type { OrganizationType } from '~/components/organization/schemas';
import { OrgSettingsTab } from '~/components/organization/tabs/OrgSettingsTab';
import { StaffPlacementSection } from '~/components/organization/tabs/orgSettings/StaffPlacementSection';
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

let qc: QueryClient;

function renderSection() {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<StaffPlacementSection organizationId={7} />, { wrapper });
}

async function loaded() {
  renderSection();
  return screen.findByTestId('org-settings-policy-select');
}

function refetched(changes: Partial<OrgSettings>) {
  act(() => {
    qc.setQueryData(orgSettingsKey(7), {
      ...SETTINGS,
      ...changes,
      updated_at: '2026-11-17T12:10:00Z',
    });
  });
}

function checkbox(code: string): HTMLInputElement {
  return screen.getByTestId(`org-settings-code-${code}`) as HTMLInputElement;
}

function saveButton(): HTMLButtonElement {
  return screen.getByTestId('org-settings-save') as HTMLButtonElement;
}

function choosePolicy(label: string) {
  fireEvent.pointerDown(screen.getByTestId('org-settings-policy-select'), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
  fireEvent.click(screen.getByRole('option', { name: new RegExp(label) }));
}

beforeEach(() => {
  vi.mocked(getOrgSettings).mockResolvedValue(SETTINGS);
});

afterEach(() => {
  cleanup();
  vi.mocked(getOrgSettings).mockReset();
  vi.mocked(patchOrgSettings).mockReset();
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

describe('StaffPlacementSection', () => {
  it('renders loaded values', async () => {
    const trigger = await loaded();
    expect(trigger).toHaveTextContent('Silent');
    for (const code of CODES) expect(checkbox(code).checked).toBe(true);
    expect(screen.getAllByRole('checkbox')).toHaveLength(6);
  });

  it('save disabled when pristine', async () => {
    await loaded();
    expect(saveButton()).toBeDisabled();
  });

  it('saves changed policy and codes', async () => {
    const rest = CODES.filter((c) => c !== 'gate_outside');
    vi.mocked(patchOrgSettings).mockResolvedValue({
      ...SETTINGS,
      staff_override_policy: 'confirm',
      staff_override_warning_codes: rest,
      updated_at: '2026-11-17T12:05:00Z',
    });
    await loaded();
    choosePolicy('Confirm');
    fireEvent.click(checkbox('gate_outside'));
    fireEvent.click(saveButton());
    await waitFor(() =>
      expect(patchOrgSettings).toHaveBeenCalledWith(7, {
        staff_override_policy: 'confirm',
        staff_override_warning_codes: rest,
      }),
    );
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('Settings saved'),
    );
  });

  it('is pristine after save', async () => {
    vi.mocked(patchOrgSettings).mockResolvedValue({
      ...SETTINGS,
      staff_override_policy: 'block',
      staff_override_warning_codes: ['over_capacity'],
      updated_at: '2026-11-17T12:05:00Z',
    });
    await loaded();
    choosePolicy('Block');
    fireEvent.click(checkbox('gate_outside'));
    fireEvent.click(saveButton());
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    await waitFor(() => expect(saveButton()).toBeDisabled());
    expect(screen.getByTestId('org-settings-policy-select')).toHaveTextContent(
      'Block',
    );
    for (const code of CODES) {
      expect(checkbox(code).checked).toBe(code === 'over_capacity');
    }
  });

  it('untick_retick_stays_pristine', async () => {
    await loaded();
    fireEvent.click(checkbox('over_capacity'));
    expect(saveButton()).toBeEnabled();
    fireEvent.click(checkbox('over_capacity'));
    expect(checkbox('over_capacity').checked).toBe(true);
    expect(saveButton()).toBeDisabled();
  });

  it('no-op save with unchanged updated_at stays pristine', async () => {
    vi.mocked(patchOrgSettings).mockResolvedValue(SETTINGS);
    await loaded();
    fireEvent.click(checkbox('over_capacity'));
    fireEvent.click(saveButton());
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    await waitFor(() => expect(saveButton()).toBeDisabled());
    expect(checkbox('over_capacity').checked).toBe(true);
  });

  it('adopts refetched values while pristine', async () => {
    await loaded();
    refetched({
      staff_override_policy: 'block',
      staff_override_warning_codes: ['over_capacity'],
    });
    await waitFor(() =>
      expect(
        screen.getByTestId('org-settings-policy-select'),
      ).toHaveTextContent('Block'),
    );
    for (const code of CODES) {
      expect(checkbox(code).checked).toBe(code === 'over_capacity');
    }
    expect(saveButton()).toBeDisabled();
  });

  it('keeps local edits when a refetch lands', async () => {
    await loaded();
    fireEvent.click(checkbox('gate_outside'));
    refetched({ staff_override_policy: 'block' });
    expect(checkbox('gate_outside').checked).toBe(false);
    expect(saveButton()).toBeEnabled();
  });

  it('patches only dirty fields', async () => {
    const rest = CODES.filter((c) => c !== 'gate_outside');
    vi.mocked(patchOrgSettings).mockResolvedValue({
      ...SETTINGS,
      staff_override_warning_codes: rest,
    });
    await loaded();
    fireEvent.click(checkbox('gate_outside'));
    fireEvent.click(saveButton());
    await waitFor(() =>
      expect(patchOrgSettings).toHaveBeenCalledWith(7, {
        staff_override_warning_codes: rest,
      }),
    );
  });

  it('keeps values on error', async () => {
    vi.mocked(patchOrgSettings).mockRejectedValue({
      response: {
        data: {
          staff_override_warning_codes: ['Unknown warning code(s): x'],
        },
      },
    });
    await loaded();
    choosePolicy('Confirm');
    fireEvent.click(saveButton());
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Unknown warning code(s): x'),
    );
    expect(screen.getByTestId('org-settings-policy-select')).toHaveTextContent(
      'Confirm',
    );
    expect(saveButton()).toBeEnabled();
  });
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
      <QueryClientProvider client={qc}>
        <OrgSettingsTab organization={organization} />
      </QueryClientProvider>,
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
