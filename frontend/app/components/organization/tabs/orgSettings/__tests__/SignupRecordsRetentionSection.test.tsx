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
import { createRef, StrictMode, type ReactNode } from 'react';
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
import type { SettingsDialogHandle } from '~/components/patterns/SettingsDialog';
import type { SettingsFormUnit } from '~/components/patterns/settingsSaveBar';
import { useSignupRecordsRetentionSection } from '../SignupRecordsRetentionSection';
import { useStaffPlacementSection } from '../StaffPlacementSection';

vi.mock('~/components/api/orgSettingsAPI', async () => {
  const actual = await vi.importActual<
    typeof import('~/components/api/orgSettingsAPI')
  >('~/components/api/orgSettingsAPI');
  return { ...actual, getOrgSettings: vi.fn(), patchOrgSettings: vi.fn() };
});
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const SETTINGS: OrgSettings = {
  organization: 7,
  staff_override_policy: 'silent',
  staff_override_warning_codes: ['over_capacity'],
  available_warning_codes: [{ code: 'over_capacity', label: 'Over capacity' }],
  signup_record_retention_days: null,
  signup_record_min_retention_days: 30,
  updated_at: '2026-11-27T12:00:00Z',
};

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

let qc: QueryClient;
let unit: SettingsFormUnit;
let staffUnit: SettingsFormUnit;
const selectSection = vi.fn();
const sectionsRef = createRef<SettingsDialogHandle<string>>() as {
  current: SettingsDialogHandle<string> | null;
};

function Harness({ withStaff }: { withStaff: boolean }): ReactNode {
  const section = useSignupRecordsRetentionSection(7, true, sectionsRef);
  unit = section.unit;
  const staff = useStaffPlacementSection(7, withStaff, sectionsRef);
  staffUnit = staff.unit;
  return (
    <>
      <div data-testid="retention-root">{section.content}</div>
      {withStaff && staff.content}
    </>
  );
}

async function loaded(settings: Partial<OrgSettings> = {}, withStaff = false) {
  vi.mocked(getOrgSettings).mockResolvedValue({ ...SETTINGS, ...settings });
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <StrictMode>
      <QueryClientProvider client={qc}>
        <form>
          <Harness withStaff={withStaff} />
        </form>
      </QueryClientProvider>
    </StrictMode>,
  );
  await screen.findByTestId('signup-retention-days');
}

const forever = () => screen.getByTestId('signup-retention-forever');
const period = () => screen.getByTestId('signup-retention-period');
const days = () =>
  screen.getByTestId('signup-retention-days') as HTMLInputElement;

async function save(): Promise<boolean> {
  let ok = false;
  await act(async () => {
    ok = await unit.save();
  });
  return ok;
}

beforeEach(() => {
  selectSection.mockClear();
  vi.mocked(toast.error).mockClear();
  sectionsRef.current = {
    selectSection,
    revealField: vi.fn(),
    sectionOfField: () => undefined,
  };
});

afterEach(() => {
  cleanup();
  vi.mocked(getOrgSettings).mockReset();
  vi.mocked(patchOrgSettings).mockReset();
});

describe('useSignupRecordsRetentionSection', () => {
  it('hydrates null as Forever with the days input disabled', async () => {
    await loaded();
    expect(forever()).toHaveAttribute('data-state', 'checked');
    expect(period()).toHaveAttribute('data-state', 'unchecked');
    expect(days()).toBeDisabled();
    expect(days().value).toBe('');
    expect(unit.isDirty).toBe(false);
  });

  it('hydrates a period with its days', async () => {
    await loaded({ signup_record_retention_days: 400 });
    expect(period()).toHaveAttribute('data-state', 'checked');
    expect(days()).not.toBeDisabled();
    expect(days().value).toBe('400');
    expect(unit.isDirty).toBe(false);
  });

  it('switching to a period pre-fills 365', async () => {
    await loaded();
    fireEvent.click(period());
    await waitFor(() => expect(days().value).toBe('365'));
    expect(days()).not.toBeDisabled();
    expect(unit.isDirty).toBe(true);
  });

  it('switching back to Forever is pristine again', async () => {
    await loaded();
    fireEvent.click(period());
    await waitFor(() => expect(days().value).toBe('365'));
    fireEvent.click(forever());
    await waitFor(() => expect(days()).toBeDisabled());
    expect(unit.isDirty).toBe(false);
  });

  it('saving Forever PATCHes exactly null', async () => {
    vi.mocked(patchOrgSettings).mockResolvedValue(SETTINGS);
    await loaded({ signup_record_retention_days: 400 });
    fireEvent.click(forever());
    await waitFor(() => expect(days()).toBeDisabled());
    expect(await save()).toBe(true);
    expect(patchOrgSettings).toHaveBeenCalledWith(7, {
      signup_record_retention_days: null,
    });
    await waitFor(() => expect(unit.isDirty).toBe(false));
  });

  it('saving a period PATCHes the days', async () => {
    vi.mocked(patchOrgSettings).mockResolvedValue({
      ...SETTINGS,
      signup_record_retention_days: 90,
    });
    await loaded();
    fireEvent.click(period());
    await waitFor(() => expect(days().value).toBe('365'));
    fireEvent.change(days(), { target: { value: '90' } });
    expect(await save()).toBe(true);
    expect(patchOrgSettings).toHaveBeenCalledWith(7, {
      signup_record_retention_days: 90,
    });
  });

  it('rejects days below the minimum without a PATCH', async () => {
    await loaded({ signup_record_retention_days: 400 });
    fireEvent.change(days(), { target: { value: '29' } });
    expect(await save()).toBe(false);
    expect(patchOrgSettings).not.toHaveBeenCalled();
    expect(await screen.findByText('Minimum 30 days.')).toBeInTheDocument();
    expect(selectSection).toHaveBeenCalledWith('signup-records');
    expect(toast.error).toHaveBeenCalledWith(
      'Please fix the highlighted fields',
      expect.anything(),
    );
  });

  it('uses the server minimum from settings', async () => {
    await loaded({
      signup_record_retention_days: 400,
      signup_record_min_retention_days: 60,
    });
    expect(screen.getByText(/Minimum 60 days\. Records/)).toBeInTheDocument();
    fireEvent.change(days(), { target: { value: '45' } });
    expect(await save()).toBe(false);
    expect(await screen.findByText('Minimum 60 days.')).toBeInTheDocument();
    expect(patchOrgSettings).not.toHaveBeenCalled();
  });

  it('puts a server field error on the field', async () => {
    vi.mocked(patchOrgSettings).mockRejectedValue({
      response: {
        status: 400,
        data: {
          signup_record_retention_days: ['Retention must be at least 90 days.'],
        },
      },
    });
    await loaded({ signup_record_retention_days: 400 });
    fireEvent.change(days(), { target: { value: '45' } });
    expect(await save()).toBe(false);
    expect(
      await screen.findByText('Retention must be at least 90 days.'),
    ).toBeInTheDocument();
    expect(selectSection).toHaveBeenCalledWith('signup-records');
    expect(toast.error).not.toHaveBeenCalled();
    expect(unit.isDirty).toBe(true);
  });

  it('toasts a non-field server error', async () => {
    vi.mocked(patchOrgSettings).mockRejectedValue({
      response: { status: 403, data: { detail: 'Not allowed.' } },
    });
    await loaded({ signup_record_retention_days: 400 });
    fireEvent.change(days(), { target: { value: '45' } });
    expect(await save()).toBe(false);
    expect(toast.error).toHaveBeenCalledWith('Not allowed.');
  });

  it('writes only its own fields from the PATCH response to the shared cache', async () => {
    const saved: OrgSettings = {
      ...SETTINGS,
      staff_override_policy: 'block',
      signup_record_retention_days: 120,
      updated_at: '2026-11-27T12:10:00Z',
    };
    vi.mocked(patchOrgSettings).mockResolvedValue(saved);
    await loaded({}, true);
    fireEvent.click(period());
    await waitFor(() => expect(days().value).toBe('365'));
    fireEvent.change(days(), { target: { value: '120' } });
    await save();
    expect(qc.getQueryData(orgSettingsKey(7))).toEqual({
      ...SETTINGS,
      signup_record_retention_days: 120,
      updated_at: '2026-11-27T12:10:00Z',
    });
    expect(screen.getByTestId('org-settings-policy-select')).toHaveTextContent(
      'Silent',
    );
    expect(staffUnit.isDirty).toBe(false);
    expect(unit.isDirty).toBe(false);
  });

  it('keeps both saves when parallel PATCH responses arrive out of order', async () => {
    let resolveStaff: (v: OrgSettings) => void = () => undefined;
    let resolveRetention: (v: OrgSettings) => void = () => undefined;
    vi.mocked(patchOrgSettings).mockImplementation((_id, patch) =>
      'staff_override_policy' in patch
        ? new Promise((r) => (resolveStaff = r))
        : new Promise((r) => (resolveRetention = r)),
    );
    await loaded({}, true);
    fireEvent.pointerDown(screen.getByTestId('org-settings-policy-select'), {
      button: 0,
      ctrlKey: false,
      pointerType: 'mouse',
    });
    fireEvent.click(screen.getByRole('option', { name: /Block/ }));
    fireEvent.click(period());
    await waitFor(() => expect(days().value).toBe('365'));

    let saves: Promise<boolean[]> = Promise.resolve([]);
    act(() => {
      saves = Promise.all([staffUnit.save(), unit.save()]);
    });
    await waitFor(() => expect(patchOrgSettings).toHaveBeenCalledTimes(2));
    await act(async () => {
      resolveRetention({
        ...SETTINGS,
        signup_record_retention_days: 365,
        updated_at: '2026-11-27T12:10:00Z',
      });
      await Promise.resolve();
      resolveStaff({
        ...SETTINGS,
        staff_override_policy: 'block',
        updated_at: '2026-11-27T12:09:00Z',
      });
      await saves;
    });

    const cached = qc.getQueryData<OrgSettings>(orgSettingsKey(7));
    expect(cached?.staff_override_policy).toBe('block');
    expect(cached?.signup_record_retention_days).toBe(365);
    expect(days().value).toBe('365');
    expect(screen.getByTestId('org-settings-policy-select')).toHaveTextContent(
      'Block',
    );
  });

  it('renders no form element inside the section', async () => {
    await loaded();
    const root = screen.getByTestId('retention-root');
    expect(root.querySelector('form')).toBeNull();
  });

  it('discard restores the loaded values', async () => {
    await loaded({ signup_record_retention_days: 400 });
    fireEvent.click(forever());
    await waitFor(() => expect(days()).toBeDisabled());
    act(() => unit.discard());
    await waitFor(() => expect(days().value).toBe('400'));
    expect(unit.isDirty).toBe(false);
  });
});
