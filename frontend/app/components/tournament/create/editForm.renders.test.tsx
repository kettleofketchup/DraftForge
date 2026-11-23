// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { createElement, type ComponentType, type ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { updateTournament } from '~/components/api/api';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';
import type { TournamentClassType } from '../types';

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  updateTournament: vi.fn(),
  createTournament: vi.fn(),
}));

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

vi.mock('~/store/userStore', async () => {
  const { create } = await import('zustand');
  return {
    useUserStore: create(() => ({
      currentUser: { pk: 1, is_staff: true, is_superuser: false },
      leagues: [],
      leaguesOrgId: 'all',
      getLeagues: () => Promise.resolve(),
      getTournaments: () => Promise.resolve(),
    })),
  };
});

const renders = vi.hoisted(() => ({}) as Record<string, number>);
const counted = vi.hoisted(
  () =>
    <P extends object>(name: string, Component: ComponentType<P>) =>
    (props: P) => {
      renders[name] = (renders[name] ?? 0) + 1;
      return createElement(Component, props);
    },
);

vi.mock('~/components/events/LobbyConfigSection', async (importOriginal) => {
  const m =
    await importOriginal<
      typeof import('~/components/events/LobbyConfigSection')
    >();
  return { ...m, LobbyConfigSection: counted('lobby', m.LobbyConfigSection) };
});
vi.mock('./TournamentConfigSection', async (importOriginal) => {
  const m = await importOriginal<typeof import('./TournamentConfigSection')>();
  return {
    ...m,
    TournamentConfigSection: counted('tournament', m.TournamentConfigSection),
  };
});
vi.mock(
  '~/components/teamdraft/DraftSettingsSection',
  async (importOriginal) => {
    const m =
      await importOriginal<
        typeof import('~/components/teamdraft/DraftSettingsSection')
      >();
    return {
      ...m,
      DraftSettingsSection: counted('draft', m.DraftSettingsSection),
    };
  },
);
vi.mock('./DotaLobbyConfigSection', async (importOriginal) => {
  const m = await importOriginal<typeof import('./DotaLobbyConfigSection')>();
  return {
    ...m,
    DotaLobbyConfigSection: counted('dotaLobby', m.DotaLobbyConfigSection),
  };
});
vi.mock('./DiscordTournamentConfigSection', async (importOriginal) => {
  const m =
    await importOriginal<typeof import('./DiscordTournamentConfigSection')>();
  return {
    ...m,
    DiscordTournamentConfigSection: counted(
      'discord',
      m.DiscordTournamentConfigSection,
    ),
  };
});
vi.mock(
  '~/components/events/form/fields/TimezoneField',
  async (importOriginal) => {
    const m =
      await importOriginal<
        typeof import('~/components/events/form/fields/TimezoneField')
      >();
    return { ...m, TimezoneField: counted('timezone', m.TimezoneField) };
  },
);

import { TournamentEditForm } from './editForm';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= vi.fn();
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.releasePointerCapture ??= () => undefined;

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <I18nextProvider i18n={createI18nInstance('en')}>
      <QueryClientProvider client={qc}>
        <TooltipProvider>
          <MemoryRouter>{children}</MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </I18nextProvider>
  );
}

const tourn = {
  pk: 5,
  name: 'Cup',
  date_played: '2026-12-01T19:00:00',
  timezone: 'America/New_York',
  state: 'future',
  tournament_type: 'double_elimination',
  league: null,
  source_event: null,
} as unknown as TournamentClassType;

const reset = () => {
  for (const key of Object.keys(renders)) delete renders[key];
};

function chooseOption(trigger: HTMLElement, name: string | RegExp) {
  fireEvent.pointerDown(trigger, {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
  fireEvent.click(screen.getByRole('option', { name }));
}

const byId = (id: string) => screen.getByTestId(id);
const type = (id: string, value: string) =>
  fireEvent.change(byId(id), { target: { value } });
const openTab = (tab: string) =>
  fireEvent.mouseDown(byId(`tournament-form-tab-${tab}`), { button: 0 });

function renderForm() {
  render(
    <TournamentEditForm
      open
      onOpenChange={() => {}}
      title="Tournament"
      tourn={tourn}
      canEdit
    />,
    { wrapper: Wrapper },
  );
  reset();
}

async function submittedPayload(
  edit: () => void,
): Promise<Record<string, unknown>> {
  vi.mocked(updateTournament)
    .mockReset()
    .mockResolvedValue({} as never);
  renderForm();
  edit();
  fireEvent.submit(byId('tournament-form'));
  await waitFor(() => expect(updateTournament).toHaveBeenCalled());
  cleanup();
  return vi.mocked(updateTournament).mock.calls[0][1] as Record<
    string,
    unknown
  >;
}

beforeEach(reset);

describe('TournamentEditForm renders', () => {
  it('re-renders only the edited field, not the other tabs', () => {
    renderForm();

    for (const value of ['C', 'Cu', 'Cup!']) {
      type('tournament-name-input', value);
    }
    type('tournament-time-picker', '20:00');
    type('tournament-time-picker', '20:30');
    fireEvent.click(byId('config-auto-create-herodrafts'));
    fireEvent.click(byId('config-auto-create-herodrafts'));
    fireEvent.click(byId('discord-discord_send_draft_link'));
    chooseOption(byId('lobby-config-game-mode'), /captain/i);
    chooseOption(byId('config-dota-lobby-mode'), /^Manual/);

    expect(renders).toEqual({});
  });

  it('after a failed submit, edits still leave the other tabs alone', async () => {
    renderForm();
    type('tournament-name-input', '');
    fireEvent.submit(byId('tournament-form'));
    await waitFor(() =>
      expect(byId('tournament-form-tab-general')).toHaveAttribute(
        'data-invalid',
      ),
    );
    reset();

    fireEvent.click(byId('config-auto-create-herodrafts'));
    fireEvent.click(byId('config-auto-create-herodrafts'));
    fireEvent.click(byId('discord-discord_send_draft_link'));
    type('tournament-time-picker', '21:00');
    type('tournament-name-input', 'N');
    await waitFor(() =>
      expect(byId('tournament-form-tab-general')).not.toHaveAttribute(
        'data-invalid',
      ),
    );

    expect(renders).toEqual({});
  });

  it('keeps values across tab switches and changes nothing else on submit', async () => {
    const untouched = await submittedPayload(() => {
      type('tournament-name-input', 'Renamed');
    });

    const edited = await submittedPayload(() => {
      type('tournament-name-input', 'Renamed');
      type('tournament-time-picker', '20:30');
      openTab('config');
      fireEvent.click(byId('config-auto-create-herodrafts'));
      openTab('discord');
      fireEvent.click(byId('discord-discord_send_draft_link'));
      openTab('general');
      openTab('config');
      openTab('general');

      expect(byId('tournament-name-input')).toHaveValue('Renamed');
      expect(byId('tournament-time-picker')).toHaveValue('20:30');
      expect(byId('config-auto-create-herodrafts')).toBeChecked();
      expect(byId('discord-discord_send_draft_link')).toBeChecked();
    });

    expect(edited).toEqual({
      ...untouched,
      date_played: '2026-12-01T20:30:00',
      auto_create_hero_drafts: true,
      discord_send_draft_link: true,
    });
  });
});
