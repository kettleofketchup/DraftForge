// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
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
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import {
  leadershipSettings,
  traits,
} from '~/features/leadership/__tests__/fixtures';
import {
  deleteTrait,
  getLeadershipSettings,
  getTraits,
  patchLeadershipSettings,
  putTraits,
} from '~/features/leadership/api';
import type { Trait } from '~/features/leadership/schemas';
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

const ORG = {
  pk: 7,
  name: 'Org',
  owner_id: 1,
  admin_ids: [VIEWER],
  staff_ids: [],
  members_viewer_pk: VIEWER,
  standing_tracks: [
    {
      key: 'leadership',
      label: 'Leadership',
      metrics: [{ key: 'points', label: 'Points' }],
      can_view_rows: true,
      can_view_own: true,
      board_open: true,
      can_manage: true,
    },
  ],
} as unknown as OrganizationType;

const BASE = traits().traits;
const KEYS = BASE.map((t) => t.key);

function eightActive(): Trait[] {
  return Array.from({ length: 8 }, (_, i) => ({
    key: `t${i}`,
    label: `Trait ${i}`,
    order: i,
    active: true,
  }));
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

function Harness(): ReactNode {
  const section = useLeadershipSection(7, true, sectionsRef);
  unit = section.unit;
  return <>{section.content}</>;
}

async function loaded() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <Harness />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  await screen.findByTestId('leadership-trait-editor');
}

async function save(): Promise<boolean> {
  let ok = false;
  await act(async () => {
    ok = await unit.save();
  });
  return ok;
}

const row = (key: string) => screen.getByTestId(`leadership-trait-${key}`);
const label = (key: string) =>
  screen.getByTestId(`leadership-trait-${key}-label`) as HTMLInputElement;
const toggle = (key: string) =>
  screen.getByTestId(`leadership-trait-${key}-active`);

function addTrait(name: string) {
  fireEvent.change(screen.getByTestId('leadership-trait-new-label'), {
    target: { value: name },
  });
  fireEvent.click(screen.getByTestId('leadership-trait-add'));
}

async function confirmDelete(key: string) {
  fireEvent.click(screen.getByTestId(`leadership-trait-${key}-delete`));
  fireEvent.click(await screen.findByTestId('leadership-trait-delete-confirm'));
}

function putBody() {
  return vi.mocked(putTraits).mock.calls[0]?.[1];
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
  vi.mocked(getLeadershipSettings).mockResolvedValue(leadershipSettings());
  vi.mocked(getTraits).mockResolvedValue(BASE);
  vi.mocked(putTraits).mockImplementation(async (_org, items) =>
    items.map((t) => ({ ...t })),
  );
});

afterEach(() => {
  cleanup();
  for (const fn of [
    getLeadershipSettings,
    patchLeadershipSettings,
    getTraits,
    putTraits,
    deleteTrait,
    fetchOrganization,
  ]) {
    vi.mocked(fn).mockReset();
  }
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
  selectSection.mockClear();
});

describe('LeadershipTraitEditor', () => {
  it('lists traits in order with an active counter', async () => {
    await loaded();
    expect(label('communication').value).toBe('Communication');
    expect(screen.getByTestId('leadership-traits-count')).toHaveTextContent(
      '4 of 8 active',
    );
    expect(unit.isDirty).toBe(false);
  });

  it('adds a trait with a slug key', async () => {
    await loaded();
    expect(screen.getByTestId('leadership-trait-add')).toBeDisabled();
    addTrait('Shot Calling');
    expect(label('shot_calling').value).toBe('Shot Calling');
    expect(
      (screen.getByTestId('leadership-trait-new-label') as HTMLInputElement)
        .value,
    ).toBe('');
    expect(unit.isDirty).toBe(true);
    expect(await save()).toBe(true);
    expect(putBody()).toEqual([
      ...BASE.map(({ key, label, order, active }) => ({
        key,
        label,
        order,
        active,
      })),
      { key: 'shot_calling', label: 'Shot Calling', order: 4, active: true },
    ]);
  });

  it('renames and reorders, then saves the ordered list', async () => {
    await loaded();
    fireEvent.click(screen.getByTestId('leadership-trait-drafting-up'));
    fireEvent.change(label('communication'), { target: { value: 'Comms' } });
    expect(
      screen.getByRole('button', { name: 'Move Drafting up' }),
    ).toBeDisabled();
    expect(await save()).toBe(true);
    expect(putBody()?.map((t) => [t.key, t.label, t.order])).toEqual([
      ['drafting', 'Drafting', 0],
      ['communication', 'Comms', 1],
      ['composure', 'Composure', 2],
      ['sportsmanship', 'Sportsmanship', 3],
    ]);
    await waitFor(() => expect(unit.isDirty).toBe(false));
  });

  it('refuses a ninth active trait', async () => {
    vi.mocked(getTraits).mockResolvedValue(eightActive());
    await loaded();
    addTrait('Ninth');
    expect(toggle('ninth')).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(toggle('ninth'));
    expect(await save()).toBe(false);
    expect(
      await screen.findByTestId('leadership-traits-error'),
    ).toHaveTextContent('At most 8 traits can be active');
    expect(putTraits).not.toHaveBeenCalled();
  });

  it('refuses deactivating the last active trait', async () => {
    await loaded();
    for (const key of KEYS) fireEvent.click(toggle(key));
    expect(await save()).toBe(false);
    expect(
      await screen.findByTestId('leadership-traits-error'),
    ).toHaveTextContent('Keep at least one trait active');
    expect(putTraits).not.toHaveBeenCalled();
  });

  it('deletes an unused trait after confirming', async () => {
    vi.mocked(deleteTrait).mockResolvedValue(undefined);
    await loaded();
    fireEvent.click(screen.getByTestId('leadership-trait-composure-delete'));
    expect(deleteTrait).not.toHaveBeenCalled();
    vi.mocked(getTraits).mockResolvedValue(
      BASE.filter((t) => t.key !== 'composure'),
    );
    fireEvent.click(
      await screen.findByTestId('leadership-trait-delete-confirm'),
    );
    await waitFor(() =>
      expect(screen.queryByTestId('leadership-trait-composure')).toBeNull(),
    );
    expect(deleteTrait).toHaveBeenCalledWith(7, 'composure');
  });

  it('deleting a trait leaves the section clean', async () => {
    vi.mocked(deleteTrait).mockResolvedValue(undefined);
    await loaded();
    vi.mocked(getTraits).mockResolvedValue(
      BASE.filter((t) => t.key !== 'composure').map((t) =>
        t.key === 'drafting' ? { ...t, label: 'Drafting (refetched)' } : t,
      ),
    );
    await confirmDelete('composure');
    await waitFor(() =>
      expect(screen.queryByTestId('leadership-trait-composure')).toBeNull(),
    );
    expect(unit.isDirty).toBe(false);
    await waitFor(() =>
      expect(label('drafting').value).toBe('Drafting (refetched)'),
    );
    expect(unit.isDirty).toBe(false);
  });

  it('deleting a trait keeps unsaved edits to other rows', async () => {
    vi.mocked(deleteTrait).mockResolvedValue(undefined);
    await loaded();
    fireEvent.change(label('communication'), { target: { value: 'Comms' } });
    addTrait('Vision');
    await confirmDelete('composure');
    await waitFor(() =>
      expect(screen.queryByTestId('leadership-trait-composure')).toBeNull(),
    );
    expect(label('communication').value).toBe('Comms');
    expect(label('vision').value).toBe('Vision');
    expect(unit.isDirty).toBe(true);
    expect(await save()).toBe(true);
    expect(putBody()?.map((t) => [t.key, t.label])).toEqual([
      ['communication', 'Comms'],
      ['drafting', 'Drafting'],
      ['sportsmanship', 'Sportsmanship'],
      ['vision', 'Vision'],
    ]);
  });

  it('removes an unsaved trait without calling the API', async () => {
    await loaded();
    addTrait('Vision');
    fireEvent.click(screen.getByTestId('leadership-trait-vision-delete'));
    expect(screen.queryByTestId('leadership-trait-vision')).toBeNull();
    expect(deleteTrait).not.toHaveBeenCalled();
    expect(unit.isDirty).toBe(false);
  });

  it('does not save settings when the trait list is invalid', async () => {
    await loaded();
    fireEvent.change(
      screen.getByTestId('leadership-setting-review_window_hours'),
      {
        target: { value: '48' },
      },
    );
    for (const key of KEYS) fireEvent.click(toggle(key));
    expect(await save()).toBe(false);
    expect(patchLeadershipSettings).not.toHaveBeenCalled();
    expect(putTraits).not.toHaveBeenCalled();
    expect(selectSection).toHaveBeenCalledWith('leadership');
    expect(toast.error).toHaveBeenCalledWith(
      'Please fix the highlighted fields',
    );
  });

  it('deactivates instead when the trait has scores', async () => {
    vi.mocked(deleteTrait).mockRejectedValue({
      response: {
        status: 409,
        data: {
          code: 'trait_in_use',
          detail: 'This trait has scores. Deactivate it instead.',
        },
      },
    });
    await loaded();
    await confirmDelete('composure');
    expect(
      await screen.findByTestId('leadership-trait-composure-error'),
    ).toHaveTextContent('This trait has scores. Deactivate it instead.');
    expect(toggle('composure')).toHaveAttribute('aria-checked', 'false');
    expect(putTraits).not.toHaveBeenCalled();
    expect(unit.isDirty).toBe(true);
    expect(await save()).toBe(true);
    expect(putBody()?.find((t) => t.key === 'composure')).toEqual({
      key: 'composure',
      label: 'Composure',
      order: 2,
      active: false,
    });
  });

  it('clears the in-use note when the trait is toggled again', async () => {
    vi.mocked(deleteTrait).mockRejectedValue({
      response: { status: 409, data: { code: 'trait_in_use' } },
    });
    await loaded();
    await confirmDelete('composure');
    await screen.findByTestId('leadership-trait-composure-error');
    fireEvent.click(toggle('composure'));
    fireEvent.click(toggle('composure'));
    expect(
      screen.queryByTestId('leadership-trait-composure-error'),
    ).not.toBeInTheDocument();
  });

  it('drops a trait another admin already deleted', async () => {
    vi.mocked(deleteTrait).mockRejectedValue({
      response: { status: 404, data: { detail: 'Not found.' } },
    });
    await loaded();
    await confirmDelete('composure');
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'That trait was already deleted.',
      ),
    );
    expect(
      screen.queryByTestId('leadership-trait-composure'),
    ).not.toBeInTheDocument();
    expect(unit.isDirty).toBe(false);
  });

  it('maps a server label error onto its row', async () => {
    vi.mocked(putTraits).mockRejectedValue({
      response: {
        status: 400,
        data: { traits: [{}, { label: ['Bad label'] }] },
      },
    });
    await loaded();
    fireEvent.change(label('drafting'), { target: { value: 'Draft' } });
    expect(await save()).toBe(false);
    expect(
      await within(row('drafting')).findByText('Bad label'),
    ).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
    expect(unit.isDirty).toBe(true);
  });

  it('shows a server detail under the list', async () => {
    vi.mocked(putTraits).mockRejectedValue({
      response: {
        status: 400,
        data: { detail: ['At most 8 traits can be active.'] },
      },
    });
    await loaded();
    fireEvent.change(label('drafting'), { target: { value: 'Draft' } });
    expect(await save()).toBe(false);
    expect(
      await screen.findByTestId('leadership-traits-error'),
    ).toHaveTextContent('At most 8 traits can be active.');
  });
});
