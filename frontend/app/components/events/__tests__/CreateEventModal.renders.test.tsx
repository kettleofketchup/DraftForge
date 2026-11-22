// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { createElement, type ComponentType } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { READY_CHECK_TEST_IDS } from '../form/testIds';
import { READY_CHECK_PRESET_ON } from '../schemas';
import { openTab, orgDefaults, submit, Wrapper } from './eventModalFixtures';

const api = vi.hoisted(() => ({
  createEvent: vi.fn(),
  getOrgEventDefaults: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  createEvent: api.createEvent,
  getOrgEventDefaults: api.getOrgEventDefaults,
  getDiscordChannels: vi.fn().mockResolvedValue([]),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
  getLeagues: vi.fn().mockResolvedValue([]),
}));

vi.mock('~/components/league/LeagueCombobox', () => ({
  LeagueCombobox: () => null,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

const renders = vi.hoisted(() => ({}) as Record<string, number>);
const counted = vi.hoisted(
  () =>
    <P extends object>(name: string, Component: ComponentType<P>) =>
    (props: P) => {
      renders[name] = (renders[name] ?? 0) + 1;
      return createElement(Component, props);
    },
);

vi.mock('../ReadyCheckConfigSection', async (importOriginal) => {
  const m = await importOriginal<typeof import('../ReadyCheckConfigSection')>();
  return {
    ...m,
    ReadyCheckConfigSection: counted('ready', m.ReadyCheckConfigSection),
  };
});
vi.mock('../ApprovalConfigSection', async (importOriginal) => {
  const m = await importOriginal<typeof import('../ApprovalConfigSection')>();
  return {
    ...m,
    ApprovalConfigSection: counted('approval', m.ApprovalConfigSection),
  };
});
vi.mock('../form/sections/EventLobbyFields', async (importOriginal) => {
  const m =
    await importOriginal<typeof import('../form/sections/EventLobbyFields')>();
  return { ...m, EventLobbyFields: counted('lobby', m.EventLobbyFields) };
});
vi.mock('../form/sections/EventTournamentFields', async (importOriginal) => {
  const m =
    await importOriginal<
      typeof import('../form/sections/EventTournamentFields')
    >();
  return {
    ...m,
    EventTournamentFields: counted('tournament', m.EventTournamentFields),
  };
});

import { CreateEventModal } from '../CreateEventModal';

const field = (name: string) =>
  document.querySelector<HTMLInputElement>(`[data-field="${name}"] input`)!;

async function submittedBody(
  fill: () => Promise<void>,
): Promise<Record<string, unknown>> {
  api.createEvent.mockClear();
  await fill();
  submit();
  await waitFor(() => expect(api.createEvent).toHaveBeenCalled());
  cleanup();
  return api.createEvent.mock.calls[0][0];
}

async function renderReady() {
  render(<CreateEventModal open onOpenChange={() => {}} organizationId={1} />, {
    wrapper: Wrapper,
  });
  return screen.findByTestId('event-name-input');
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.createEvent.mockResolvedValue({ id: 99 });
  api.getOrgEventDefaults.mockResolvedValue(orgDefaults);
});

describe('CreateEventModal renders', () => {
  it('re-renders only the edited field, not the other tabs', async () => {
    const name = await renderReady();
    for (const key of Object.keys(renders)) delete renders[key];

    for (const value of ['F', 'Fr', 'Fri']) {
      fireEvent.change(name, { target: { value } });
    }
    fireEvent.click(screen.getByTestId('signup-rules-allow_user_signups'));
    fireEvent.click(screen.getByTestId('signup-rules-allow_user_signups'));
    fireEvent.click(field('require_steam_id'));
    fireEvent.click(field('allow_active_mmr'));
    fireEvent.click(screen.getByTestId(READY_CHECK_TEST_IDS.toggle));

    expect(renders).toEqual({});
  });

  it('keeps values across tab switches and changes nothing else on submit', async () => {
    const untouched = await submittedBody(async () => {
      fireEvent.change(await renderReady(), { target: { value: 'Night 5' } });
    });

    const edited = await submittedBody(async () => {
      fireEvent.change(await renderReady(), { target: { value: 'Night 5' } });
      openTab(/approval/i);
      fireEvent.click(screen.getByTestId('signup-rules-allow_user_signups'));
      fireEvent.click(field('require_steam_id'));
      openTab(/ready check/i);
      fireEvent.click(screen.getByTestId(READY_CHECK_TEST_IDS.toggle));
      openTab(/^event$/i);
      openTab(/approval/i);
      openTab(/ready check/i);

      expect(screen.getByTestId('event-name-input')).toHaveValue('Night 5');
      expect(
        screen.getByTestId('signup-rules-allow_user_signups'),
      ).not.toBeChecked();
      expect(field('require_steam_id')).toBeChecked();
      expect(screen.getByTestId(READY_CHECK_TEST_IDS.toggle)).toHaveAttribute(
        'aria-checked',
        'true',
      );
    });

    expect(edited).toEqual({
      ...untouched,
      allow_user_signups: false,
      require_steam_id: true,
      ...READY_CHECK_PRESET_ON,
    });
  });
});
