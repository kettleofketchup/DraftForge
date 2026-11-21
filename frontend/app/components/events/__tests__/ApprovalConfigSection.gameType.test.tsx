// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GAME_TYPE } from '~/components/game/constants';
import type { EventType } from '../schemas';
import { event, orgDefaults, submit, Wrapper } from './eventModalFixtures';

const api = vi.hoisted(() => ({
  createEvent: vi.fn(),
  getOrgEventDefaults: vi.fn(),
  updateEvent: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  createEvent: api.createEvent,
  getOrgEventDefaults: api.getOrgEventDefaults,
  fetchCurrentUser: vi.fn().mockResolvedValue({}),
  getDiscordChannels: vi.fn().mockResolvedValue([]),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
  getLeagues: vi.fn().mockResolvedValue([]),
}));

vi.mock('~/hooks/useEvent', () => ({
  useUpdateEventMutation: () => ({
    mutateAsync: api.updateEvent,
    isPending: false,
  }),
}));

vi.mock('~/hooks/useLobbyPassword', () => ({
  useEventLobbyPassword: () => ({ data: undefined }),
  useRegenerateEventLobbyPassword: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

vi.mock('~/components/league/LeagueCombobox', () => ({
  LeagueCombobox: () => null,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

import { CreateEventModal } from '../CreateEventModal';
import { EditEventModal } from '../EditEventModal';

Element.prototype.scrollIntoView ??= vi.fn();

const RANK_TYPE_LABELS = [
  'Allowed Rank Types',
  'Active MMR Players',
  'Previously Ranked Players',
  'Battle Cup Players (Never Ranked)',
];

const deadlockEvent: EventType = {
  ...event,
  game_type: GAME_TYPE.DEADLOCK,
  allow_previous_rank: false,
  discord_require_rank_screenshot: true,
  min_mmr: 3000,
};

function renderEdit(e: EventType) {
  render(<EditEventModal event={e} open onOpenChange={() => {}} />, {
    wrapper: Wrapper,
  });
}

function search(prefix: string, value: string) {
  fireEvent.change(screen.getByTestId(`${prefix}-search`), {
    target: { value },
  });
  return screen
    .queryAllByTestId(`${prefix}-search-hit`)
    .map((el) => el.querySelector('span')?.textContent);
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.createEvent.mockResolvedValue({ id: 99 });
  api.updateEvent.mockResolvedValue({});
  api.getOrgEventDefaults.mockResolvedValue(orgDefaults);
});

describe('Approval rank types by game', () => {
  it('shows the Dota rank types on a Dota event', () => {
    renderEdit(event);
    for (const label of RANK_TYPE_LABELS) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(search('edit-event', 'battle cup')).toContain(
      'Battle Cup Players (Never Ranked)',
    );
  });

  it('hides the Dota rank types on a Deadlock event', () => {
    renderEdit(deadlockEvent);
    for (const label of RANK_TYPE_LABELS) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
    expect(screen.getByText('General Requirements')).toBeInTheDocument();
  });

  it('leaves the Dota rank types out of the settings search on a Deadlock event', () => {
    renderEdit(deadlockEvent);
    for (const term of ['battle cup', 'previously ranked', 'minimum mmr']) {
      expect(search('edit-event', term)).toEqual([]);
    }
  });

  it('keeps the stored rank-type values when saving a Deadlock event', async () => {
    renderEdit(deadlockEvent);
    submit();
    await waitFor(() => expect(api.updateEvent).toHaveBeenCalled());
    expect(api.updateEvent.mock.calls[0][0]).toMatchObject({
      allow_active_mmr: true,
      allow_previous_rank: false,
      allow_battlecup_rating: true,
      discord_require_rank_screenshot: true,
      min_mmr: 3000,
    });
  });

  it('hides the Dota rank types when creating a Deadlock event', async () => {
    api.getOrgEventDefaults.mockResolvedValue({
      ...orgDefaults,
      game_type: GAME_TYPE.DEADLOCK,
    });
    render(
      <CreateEventModal open onOpenChange={() => {}} organizationId={1} />,
      { wrapper: Wrapper },
    );
    await screen.findByTestId('event-name-input');
    await waitFor(() =>
      expect(screen.queryByText('Allowed Rank Types')).not.toBeInTheDocument(),
    );
    expect(search('event-modal', 'battle cup')).toEqual([]);
  });

  it('shows the Dota rank types when creating a Dota event', async () => {
    render(
      <CreateEventModal open onOpenChange={() => {}} organizationId={1} />,
      { wrapper: Wrapper },
    );
    await screen.findByTestId('event-name-input');
    expect(await screen.findByText('Allowed Rank Types')).toBeInTheDocument();
  });
});
