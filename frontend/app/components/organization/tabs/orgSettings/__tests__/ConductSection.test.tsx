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
import { createRef, type ReactNode } from 'react';
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
import { fetchOrganization } from '~/components/api/api';
import type { OrganizationType } from '~/components/organization/schemas';
import { useConductSection } from '~/components/organization/tabs/orgSettings/ConductSection';
import type { SettingsDialogHandle } from '~/components/patterns/SettingsDialog';
import type { SettingsFormUnit } from '~/components/patterns/settingsSaveBar';
import type { UserType } from '~/components/user/types';
import {
  getConductSettings,
  patchConductSettings,
} from '~/features/conduct/api';
import type {
  ConductSettings,
  ConductSettingsValues,
} from '~/features/conduct/schemas';
import { useUserStore } from '~/store/userStore';

vi.mock('~/features/conduct/api', async () => {
  const actual = await vi.importActual<typeof import('~/features/conduct/api')>(
    '~/features/conduct/api',
  );
  return {
    ...actual,
    getConductSettings: vi.fn(),
    patchConductSettings: vi.fn(),
  };
});
vi.mock('~/components/api/api', async () => {
  const actual = await vi.importActual<typeof import('~/components/api/api')>(
    '~/components/api/api',
  );
  return { ...actual, fetchOrganization: vi.fn() };
});
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

const VIEWER = 5;

const DEFAULTS: ConductSettingsValues = {
  late_cancel_hours: 2,
  late_cancel_weight: 0.5,
  half_life_days: 90,
  max_age_days: 365,
  prior_show_rate: 0.85,
  prior_strength: 3,
  min_events: 3,
  leaderboard_public: true,
  back_of_line_enabled: false,
  back_of_line_below: 0.75,
  require_approval_enabled: false,
  require_approval_below: 0.65,
  block_enabled: false,
  block_below: 0.4,
  enforce_on_new_members: false,
};

function settings(
  changes: Partial<ConductSettingsValues> = {},
): ConductSettings {
  return { ...DEFAULTS, ...changes, defaults: { ...DEFAULTS } };
}

const ORG = {
  pk: 7,
  name: 'Org',
  owner_id: 1,
  admin_ids: [VIEWER],
  staff_ids: [],
  members_viewer_pk: VIEWER,
  can_manage_conduct: true,
} as unknown as OrganizationType;

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

let unit: SettingsFormUnit;
const selectSection = vi.fn();
const sectionsRef = createRef<SettingsDialogHandle<string>>() as {
  current: SettingsDialogHandle<string> | null;
};

function Harness({ enabled }: { enabled: boolean }): ReactNode {
  const section = useConductSection(7, enabled, sectionsRef);
  unit = section.unit;
  return <>{section.content}</>;
}

function renderSection(enabled = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<Harness enabled={enabled} />, { wrapper });
}

async function save(): Promise<boolean> {
  let ok = false;
  await act(async () => {
    ok = await unit.save();
  });
  return ok;
}

function input(field: string): HTMLInputElement {
  return screen.getByTestId(`conduct-setting-${field}`) as HTMLInputElement;
}

async function loaded() {
  renderSection();
  await screen.findByTestId('conduct-setting-half_life_days');
}

beforeEach(() => {
  sectionsRef.current = {
    selectSection,
    sectionOfField: () => undefined,
  } as unknown as SettingsDialogHandle<string>;
  useUserStore.setState({
    currentUser: { pk: VIEWER, username: 'viewer' } as UserType,
  });
  vi.mocked(fetchOrganization).mockResolvedValue(ORG);
  vi.mocked(getConductSettings).mockResolvedValue(settings());
});

afterEach(() => {
  cleanup();
  vi.mocked(getConductSettings).mockReset();
  vi.mocked(patchConductSettings).mockReset();
  vi.mocked(fetchOrganization).mockReset();
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
  selectSection.mockClear();
});

describe('ConductSection', () => {
  it('renders loaded values', async () => {
    vi.mocked(getConductSettings).mockResolvedValue(
      settings({ half_life_days: 30 }),
    );
    await loaded();
    expect(input('half_life_days').value).toBe('30');
    expect(input('prior_show_rate').value).toBe('0.85');
    expect(getConductSettings).toHaveBeenCalledWith(7);
    expect(unit.isDirty).toBe(false);
  });

  it('refuses an out-of-range half-life', async () => {
    await loaded();
    fireEvent.change(input('half_life_days'), { target: { value: '5' } });
    expect(await save()).toBe(false);
    expect(await screen.findByText('At least 7')).toBeInTheDocument();
    expect(selectSection).toHaveBeenCalledWith('conduct');
    expect(patchConductSettings).not.toHaveBeenCalled();
  });

  it('refuses a max age below the half-life', async () => {
    await loaded();
    fireEvent.change(input('half_life_days'), { target: { value: '400' } });
    fireEvent.change(input('max_age_days'), { target: { value: '300' } });
    expect(await save()).toBe(false);
    expect(
      await screen.findByText('Max age must be at least the half-life'),
    ).toBeInTheDocument();
    expect(patchConductSettings).not.toHaveBeenCalled();
  });

  it('shows the default badge only for default values', async () => {
    vi.mocked(getConductSettings).mockResolvedValue(
      settings({ half_life_days: 30 }),
    );
    await loaded();
    expect(
      screen.queryByTestId('conduct-setting-half_life_days-default'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId('conduct-setting-min_events-default'),
    ).toBeInTheDocument();
  });

  it('reset restores the default and shows the badge', async () => {
    vi.mocked(getConductSettings).mockResolvedValue(
      settings({ half_life_days: 30 }),
    );
    await loaded();
    fireEvent.click(screen.getByTestId('conduct-setting-half_life_days-reset'));
    expect(input('half_life_days').value).toBe('90');
    expect(
      screen.getByTestId('conduct-setting-half_life_days-default'),
    ).toBeInTheDocument();
    expect(unit.isDirty).toBe(true);
  });

  it('collapses enforcement when every toggle is off', async () => {
    await loaded();
    expect(
      screen.queryByTestId('conduct-setting-block_enabled'),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('conduct-settings-enforcement-toggle'));
    expect(
      await screen.findByTestId('conduct-setting-block_enabled'),
    ).toBeInTheDocument();
  });

  it('expands enforcement when a toggle is on', async () => {
    vi.mocked(getConductSettings).mockResolvedValue(
      settings({ require_approval_enabled: true }),
    );
    await loaded();
    expect(
      screen.getByTestId('conduct-setting-require_approval_enabled'),
    ).toBeInTheDocument();
  });

  it('saves only changed fields', async () => {
    vi.mocked(patchConductSettings).mockResolvedValue(
      settings({ half_life_days: 60, leaderboard_public: false }),
    );
    await loaded();
    fireEvent.change(input('half_life_days'), { target: { value: '60' } });
    fireEvent.click(input('leaderboard_public'));
    expect(await save()).toBe(true);
    expect(patchConductSettings).toHaveBeenCalledWith(7, {
      half_life_days: 60,
      leaderboard_public: false,
    });
    await waitFor(() => expect(unit.isDirty).toBe(false));
  });

  it('shows a server field error beside its input', async () => {
    vi.mocked(patchConductSettings).mockRejectedValue({
      response: { status: 400, data: { min_events: ['At most 20'] } },
    });
    await loaded();
    fireEvent.change(input('min_events'), { target: { value: '5' } });
    expect(await save()).toBe(false);
    expect(await screen.findByText('At most 20')).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
    expect(selectSection).toHaveBeenCalledWith('conduct');
    expect(input('min_events').value).toBe('5');
    expect(unit.isDirty).toBe(true);
  });

  it('opens enforcement for a server error on a collapsed field', async () => {
    vi.mocked(patchConductSettings).mockRejectedValue({
      response: {
        status: 400,
        data: {
          block_below: ['Ensure this value is less than or equal to 1.'],
        },
      },
    });
    await loaded();
    fireEvent.change(input('min_events'), { target: { value: '5' } });
    expect(await save()).toBe(false);
    expect(
      await screen.findByText('Ensure this value is less than or equal to 1.'),
    ).toBeInTheDocument();
    expect(input('block_below')).toBeInTheDocument();
  });

  it('toasts an error that names no field', async () => {
    vi.mocked(patchConductSettings).mockRejectedValue({
      response: { status: 403, data: { detail: 'Not allowed' } },
    });
    await loaded();
    fireEvent.change(input('min_events'), { target: { value: '5' } });
    expect(await save()).toBe(false);
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Not allowed'),
    );
  });

  it('reopens enforcement when a hidden field is invalid', async () => {
    await loaded();
    fireEvent.click(screen.getByTestId('conduct-settings-enforcement-toggle'));
    fireEvent.change(await screen.findByTestId('conduct-setting-block_below'), {
      target: { value: '1.5' },
    });
    fireEvent.click(screen.getByTestId('conduct-settings-enforcement-toggle'));
    await waitFor(() =>
      expect(
        screen.queryByTestId('conduct-setting-block_below'),
      ).not.toBeInTheDocument(),
    );
    expect(await save()).toBe(false);
    expect(await screen.findByText('At most 1')).toBeInTheDocument();
    expect(input('block_below')).toBeInTheDocument();
    expect(patchConductSettings).not.toHaveBeenCalled();
  });

  it('rejects a threshold with three decimals before calling the API', async () => {
    await loaded();
    fireEvent.click(screen.getByTestId('conduct-settings-enforcement-toggle'));
    fireEvent.change(await screen.findByTestId('conduct-setting-block_below'), {
      target: { value: '0.405' },
    });
    expect(await save()).toBe(false);
    expect(
      await screen.findByText('At most two decimal places'),
    ).toBeInTheDocument();
    expect(patchConductSettings).not.toHaveBeenCalled();
  });

  it('defaults show every enforcement toggle off', async () => {
    await loaded();
    fireEvent.click(screen.getByTestId('conduct-settings-enforcement-toggle'));
    for (const field of [
      'back_of_line_enabled',
      'require_approval_enabled',
      'block_enabled',
    ]) {
      const toggle = await screen.findByTestId(`conduct-setting-${field}`);
      expect(toggle).toHaveAttribute('aria-checked', 'false');
    }
  });

  it('does not load settings without manage access', async () => {
    vi.mocked(fetchOrganization).mockResolvedValue({
      ...ORG,
      can_manage_conduct: false,
    } as OrganizationType);
    renderSection();
    await waitFor(() => expect(fetchOrganization).toHaveBeenCalled());
    expect(getConductSettings).not.toHaveBeenCalled();
  });

  it('does not load settings while the section is disabled', async () => {
    renderSection(false);
    await act(async () => {});
    expect(fetchOrganization).not.toHaveBeenCalled();
    expect(getConductSettings).not.toHaveBeenCalled();
    expect(unit.isDirty).toBe(false);
  });

  it('discard restores the loaded values', async () => {
    await loaded();
    fireEvent.change(input('half_life_days'), { target: { value: '60' } });
    expect(unit.isDirty).toBe(true);
    act(() => unit.discard());
    expect(input('half_life_days').value).toBe('90');
    await waitFor(() => expect(unit.isDirty).toBe(false));
  });
});
