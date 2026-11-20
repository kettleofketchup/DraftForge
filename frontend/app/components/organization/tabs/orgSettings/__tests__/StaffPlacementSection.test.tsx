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
import type { SettingsFormUnit } from '~/components/patterns/settingsSaveBar';
import { useStaffPlacementSection } from '../StaffPlacementSection';

vi.mock('~/components/api/orgSettingsAPI', async () => {
  const actual = await vi.importActual<
    typeof import('~/components/api/orgSettingsAPI')
  >('~/components/api/orgSettingsAPI');
  return { ...actual, getOrgSettings: vi.fn(), patchOrgSettings: vi.fn() };
});
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

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
let unit: SettingsFormUnit;

function Harness({ enabled = true }: { enabled?: boolean }): ReactNode {
  const section = useStaffPlacementSection(7, enabled);
  unit = section.unit;
  return <>{section.content}</>;
}

async function loaded(enabled = true) {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <Harness enabled={enabled} />
    </QueryClientProvider>,
  );
  return screen.findByTestId('org-settings-policy-select');
}

function checkbox(code: string): HTMLInputElement {
  return screen.getByTestId(`org-settings-code-${code}`) as HTMLInputElement;
}

function choosePolicy(label: string) {
  fireEvent.pointerDown(screen.getByTestId('org-settings-policy-select'), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
  fireEvent.click(screen.getByRole('option', { name: new RegExp(label) }));
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

beforeEach(() => {
  vi.mocked(getOrgSettings).mockResolvedValue(SETTINGS);
});

afterEach(() => {
  cleanup();
  vi.mocked(getOrgSettings).mockReset();
  vi.mocked(patchOrgSettings).mockReset();
});

describe('useStaffPlacementSection', () => {
  it('renders loaded values', async () => {
    const trigger = await loaded();
    expect(trigger).toHaveTextContent('Silent');
    for (const code of CODES) expect(checkbox(code).checked).toBe(true);
    expect(screen.getAllByRole('checkbox')).toHaveLength(6);
  });

  it('no Save button renders', async () => {
    await loaded();
    expect(screen.queryByTestId('org-settings-save')).not.toBeInTheDocument();
  });

  it('isDirty after toggling a code', async () => {
    await loaded();
    expect(unit.isDirty).toBe(false);
    fireEvent.click(checkbox('over_capacity'));
    expect(unit.isDirty).toBe(true);
  });

  it('untick_retick_stays_pristine', async () => {
    await loaded();
    fireEvent.click(checkbox('over_capacity'));
    fireEvent.click(checkbox('over_capacity'));
    expect(unit.isDirty).toBe(false);
  });

  it('save PATCHes only changed fields', async () => {
    const rest = CODES.filter((c) => c !== 'gate_outside');
    vi.mocked(patchOrgSettings).mockResolvedValue({
      ...SETTINGS,
      staff_override_warning_codes: rest,
    });
    await loaded();
    fireEvent.click(checkbox('gate_outside'));
    let ok = false;
    await act(async () => {
      ok = await unit.save();
    });
    expect(ok).toBe(true);
    expect(patchOrgSettings).toHaveBeenCalledWith(7, {
      staff_override_warning_codes: rest,
    });
  });

  it('saves changed policy and codes, then is pristine', async () => {
    vi.mocked(patchOrgSettings).mockResolvedValue({
      ...SETTINGS,
      staff_override_policy: 'block',
      staff_override_warning_codes: ['over_capacity'],
    });
    await loaded();
    choosePolicy('Block');
    for (const c of CODES.filter((x) => x !== 'over_capacity')) {
      fireEvent.click(checkbox(c));
    }
    await act(async () => {
      await unit.save();
    });
    expect(patchOrgSettings).toHaveBeenCalledWith(7, {
      staff_override_policy: 'block',
      staff_override_warning_codes: ['over_capacity'],
    });
    await waitFor(() => expect(unit.isDirty).toBe(false));
    expect(screen.getByTestId('org-settings-policy-select')).toHaveTextContent(
      'Block',
    );
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
    expect(unit.isDirty).toBe(false);
  });

  it('keeps local edits when a refetch lands', async () => {
    await loaded();
    fireEvent.click(checkbox('gate_outside'));
    refetched({ staff_override_policy: 'block' });
    expect(checkbox('gate_outside').checked).toBe(false);
    expect(unit.isDirty).toBe(true);
  });

  it('keeps values and resolves false on error', async () => {
    vi.mocked(patchOrgSettings).mockRejectedValue({
      response: {
        data: { staff_override_warning_codes: ['Unknown warning code(s): x'] },
      },
    });
    await loaded();
    choosePolicy('Confirm');
    let ok = true;
    await act(async () => {
      ok = await unit.save();
    });
    expect(ok).toBe(false);
    expect(screen.getByTestId('org-settings-policy-select')).toHaveTextContent(
      'Confirm',
    );
    expect(unit.isDirty).toBe(true);
  });

  it('does not fetch when disabled', async () => {
    qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <Harness enabled={false} />
      </QueryClientProvider>,
    );
    expect(getOrgSettings).not.toHaveBeenCalled();
    expect(unit.isDirty).toBe(false);
  });
});
