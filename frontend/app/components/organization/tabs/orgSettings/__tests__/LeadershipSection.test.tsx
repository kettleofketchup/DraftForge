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
import { useLeadershipSection } from '~/components/organization/tabs/orgSettings/LeadershipSection';
import type { SettingsDialogHandle } from '~/components/patterns/SettingsDialog';
import type { SettingsFormUnit } from '~/components/patterns/settingsSaveBar';
import type { UserType } from '~/components/user/types';
import {
  leadershipSettings,
  traits,
} from '~/features/leadership/__tests__/fixtures';
import {
  getLeadershipSettings,
  getTraits,
  patchLeadershipSettings,
} from '~/features/leadership/api';
import type { LeadershipSettings } from '~/features/leadership/schemas';
import { useUserStore } from '~/store/userStore';

vi.mock('~/features/leadership/api', async () => {
  const actual = await vi.importActual<
    typeof import('~/features/leadership/api')
  >('~/features/leadership/api');
  return {
    ...actual,
    getLeadershipSettings: vi.fn(),
    patchLeadershipSettings: vi.fn(),
    getTraits: vi.fn(),
    putTraits: vi.fn(),
    deleteTrait: vi.fn(),
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

function leadershipTrack(canManage: boolean) {
  return {
    key: 'leadership',
    label: 'Leadership',
    metrics: [{ key: 'points', label: 'Points' }],
    can_view_rows: true,
    can_view_own: true,
    board_open: true,
    can_manage: canManage,
  };
}

function org(canManage = true): OrganizationType {
  return {
    pk: 7,
    name: 'Org',
    owner_id: 1,
    admin_ids: [VIEWER],
    staff_ids: [],
    members_viewer_pk: VIEWER,
    standing_tracks: [leadershipTrack(canManage)],
  } as unknown as OrganizationType;
}

function withCaptained(points: number): LeadershipSettings {
  return leadershipSettings({
    points: leadershipSettings().points.map((k) =>
      k.kind === 'captained' ? { ...k, points, overridden: true } : k,
    ),
  });
}

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
  const section = useLeadershipSection(7, enabled, sectionsRef);
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
  return screen.getByTestId(`leadership-setting-${field}`) as HTMLInputElement;
}

async function loaded() {
  renderSection();
  await screen.findByTestId('leadership-setting-review_window_hours');
}

beforeEach(() => {
  sectionsRef.current = {
    selectSection,
    sectionOfField: () => undefined,
  } as unknown as SettingsDialogHandle<string>;
  useUserStore.setState({
    currentUser: { pk: VIEWER, username: 'viewer' } as UserType,
  });
  vi.mocked(fetchOrganization).mockResolvedValue(org());
  vi.mocked(getLeadershipSettings).mockResolvedValue(leadershipSettings());
  vi.mocked(getTraits).mockResolvedValue(traits().traits);
});

afterEach(() => {
  cleanup();
  vi.mocked(getLeadershipSettings).mockReset();
  vi.mocked(patchLeadershipSettings).mockReset();
  vi.mocked(getTraits).mockReset();
  vi.mocked(fetchOrganization).mockReset();
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
  selectSection.mockClear();
});

describe('LeadershipSection', () => {
  it('renders loaded values and point overrides', async () => {
    vi.mocked(getLeadershipSettings).mockResolvedValue({
      ...withCaptained(8),
      review_window_hours: 48,
    });
    await loaded();
    expect(getLeadershipSettings).toHaveBeenCalledWith(7);
    for (const title of ['Reviews', 'Points', 'Rating', 'Visibility']) {
      expect(screen.getByText(title, { selector: 'legend' })).toBeVisible();
    }
    expect(input('review_window_hours').value).toBe('48');
    expect(input('prior_rating').value).toBe('3');
    expect(input('points-captained').value).toBe('8');
    expect(screen.getByText('Captained a team')).toBeInTheDocument();
    expect(
      screen.queryByTestId('leadership-setting-points-captained-default'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId('leadership-setting-points-placement_1-default'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('leadership-setting-review_window_hours-default'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId('leadership-setting-half_life_days-default'),
    ).toBeInTheDocument();
    expect(unit.isDirty).toBe(false);
  });

  it('refuses min reviewers below 2 before calling the API', async () => {
    await loaded();
    fireEvent.change(input('rating_min_reviewers'), { target: { value: '1' } });
    expect(await save()).toBe(false);
    expect(await screen.findByText('At least 2')).toBeInTheDocument();
    expect(selectSection).toHaveBeenCalledWith('leadership');
    expect(patchLeadershipSettings).not.toHaveBeenCalled();
  });

  it('saves only changed fields', async () => {
    vi.mocked(patchLeadershipSettings).mockResolvedValue(
      leadershipSettings({ review_window_hours: 48, leaderboard_public: true }),
    );
    await loaded();
    fireEvent.change(input('review_window_hours'), {
      target: { value: '48' },
    });
    fireEvent.click(input('leaderboard_public'));
    expect(await save()).toBe(true);
    expect(patchLeadershipSettings).toHaveBeenCalledWith(7, {
      review_window_hours: 48,
      leaderboard_public: true,
    });
    await waitFor(() => expect(unit.isDirty).toBe(false));
  });

  it('resetting an override sends null', async () => {
    vi.mocked(getLeadershipSettings).mockResolvedValue(withCaptained(8));
    vi.mocked(patchLeadershipSettings).mockResolvedValue(leadershipSettings());
    await loaded();
    fireEvent.click(
      screen.getByTestId('leadership-setting-points-captained-reset'),
    );
    expect(input('points-captained').value).toBe('5');
    expect(await save()).toBe(true);
    expect(patchLeadershipSettings).toHaveBeenCalledWith(7, {
      points: { captained: null },
    });
  });

  it('shows a server field error beside its input', async () => {
    vi.mocked(patchLeadershipSettings).mockRejectedValue({
      response: { status: 400, data: { review_window_hours: ['Too big'] } },
    });
    await loaded();
    fireEvent.change(input('review_window_hours'), {
      target: { value: '300' },
    });
    expect(await save()).toBe(false);
    expect(await screen.findByText('Too big')).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
    expect(selectSection).toHaveBeenCalledWith('leadership');
    expect(input('review_window_hours').value).toBe('300');
    expect(unit.isDirty).toBe(true);
  });

  it('maps a points error onto the override input', async () => {
    vi.mocked(patchLeadershipSettings).mockRejectedValue({
      response: {
        status: 400,
        data: { points: { placement_1: ['Too many points'] } },
      },
    });
    await loaded();
    fireEvent.change(input('points-placement_1'), { target: { value: '12' } });
    expect(await save()).toBe(false);
    const message = await screen.findByText('Too many points');
    expect(input('points-placement_1')).toHaveAttribute(
      'aria-describedby',
      expect.stringContaining(message.id),
    );
  });

  it('maps the max age refusal onto max age', async () => {
    vi.mocked(patchLeadershipSettings).mockRejectedValue({
      response: {
        status: 400,
        data: { detail: 'Max age must be at least the half-life.' },
      },
    });
    await loaded();
    fireEvent.change(input('max_age_days'), { target: { value: '700' } });
    expect(await save()).toBe(false);
    expect(
      await screen.findByText('Max age must be at least the half-life.'),
    ).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('toasts an error that names no field', async () => {
    vi.mocked(patchLeadershipSettings).mockRejectedValue({
      response: { status: 403, data: { detail: 'Not allowed' } },
    });
    await loaded();
    fireEvent.change(input('review_window_hours'), {
      target: { value: '48' },
    });
    expect(await save()).toBe(false);
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Not allowed'),
    );
  });

  it('does not load without manage access', async () => {
    vi.mocked(fetchOrganization).mockResolvedValue(org(false));
    renderSection();
    await waitFor(() => expect(fetchOrganization).toHaveBeenCalled());
    await act(async () => {});
    expect(getLeadershipSettings).not.toHaveBeenCalled();
    expect(getTraits).not.toHaveBeenCalled();
  });

  it('discard restores the loaded values', async () => {
    await loaded();
    fireEvent.change(input('review_window_hours'), {
      target: { value: '48' },
    });
    expect(unit.isDirty).toBe(true);
    act(() => unit.discard());
    expect(input('review_window_hours').value).toBe('72');
    await waitFor(() => expect(unit.isDirty).toBe(false));
  });
});
