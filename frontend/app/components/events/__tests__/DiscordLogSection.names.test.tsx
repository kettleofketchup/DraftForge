// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { getEventDiscordState } from '~/components/api/api';
import api from '~/components/api/axios';
import { TooltipProvider } from '~/components/ui/tooltip';
import { DisplayOrgProvider } from '~/lib/displayOrgContext';
import { useUserCacheStore } from '~/store/userCacheStore';
import { DiscordLogSection } from '../DiscordLogSection';

vi.mock('~/components/api/api', () => ({
  getEventDiscordState: vi.fn(),
  fetchCurrentUser: vi.fn().mockRejectedValue(new Error('anonymous')),
}));

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => ({
    showPlayerPopover: vi.fn(),
    hidePopover: vi.fn(),
    openPlayerModal: vi.fn(),
    openTeamModal: vi.fn(),
  }),
}));

vi.mock('~/features/league-stats/queries', () => ({
  usePlayerLeagueSummary: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
  }),
}));

vi.mock('~/components/api/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

const dm = {
  id: 5,
  dm_type: 1,
  dm_type_display: 'Reminder',
  username: 'u',
  nickname: null,
  discordNickname: 'Gwaihir',
  guildNickname: 'DragonClaw',
  avatar: null,
  discord_user_id: '123',
  can_send: true,
  message_id: '',
  sent_at: '2026-11-16T00:00:00Z',
  delivered: true,
  responded: false,
  response_text: '',
  responded_at: null,
  created_at: '2026-11-16T00:00:00Z',
};

const log = {
  id: 9,
  category: 2,
  category_display: 'Interaction',
  action: 'Signed up',
  target_type: 'button',
  discord_user_id: '124',
  discord_username: 'raw_discord',
  nickname: null,
  discordNickname: 'Gwen',
  guildNickname: 'GwenServer',
  username: 'gwen',
  avatar: null,
  message_id: null,
  status_code: null,
  error_message: '',
  success: true,
  created_at: '2026-11-16T01:00:00Z',
};

const fired = {
  task: 'reminder',
  label: 'Reminder',
  fires_at: null,
  status: 'fired',
  description: '',
  check_interval: null,
  last_fired_at: '2026-11-16T00:00:00Z',
  fired_by: {
    pk: 3,
    username: 'kettle',
    nickname: null,
    discordNickname: 'KettleGlobal',
    discordId: null,
    avatar: null,
  },
  can_fire: false,
};

function wrapperFor(orgId: number | null) {
  return function Wrapper({ children }: { children: ReactNode }) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return (
      <QueryClientProvider client={qc}>
        <TooltipProvider>
          <DisplayOrgProvider orgId={orgId}>{children}</DisplayOrgProvider>
        </TooltipProvider>
      </QueryClientProvider>
    );
  };
}

function openTab(testId: string): void {
  const trigger = screen.getByTestId(testId);
  fireEvent.mouseDown(trigger, { button: 0, ctrlKey: false });
  fireEvent.click(trigger);
}

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  };
});

beforeEach(() => {
  useUserCacheStore.getState().reset();
  vi.mocked(getEventDiscordState).mockResolvedValue({
    id: 1,
    guild_id: 'g',
    scheduled_event_id: null,
    signup_message: null,
    announcement: null,
    logs: [log],
    dms: [dm],
    created_at: '2026-11-16T00:00:00Z',
    updated_at: '2026-11-16T00:00:00Z',
  });
  vi.mocked(api.get).mockResolvedValue({ data: [fired] });
});

describe('DiscordLogSection names', () => {
  it('shows DM recipients by server nickname in the org context', async () => {
    render(<DiscordLogSection eventId={1} isAdmin />, {
      wrapper: wrapperFor(7),
    });
    await screen.findByTestId('discord-subtab-dms');
    openTab('discord-subtab-dms');
    expect(await screen.findAllByText('DragonClaw')).not.toHaveLength(0);
    expect(screen.queryByText('Gwaihir')).toBeNull();
  });

  it('shows DM recipients by global name outside an org context', async () => {
    render(<DiscordLogSection eventId={1} isAdmin />, {
      wrapper: wrapperFor(null),
    });
    await screen.findByTestId('discord-subtab-dms');
    openTab('discord-subtab-dms');
    expect(await screen.findAllByText('Gwaihir')).not.toHaveLength(0);
    expect(screen.queryByText('DragonClaw')).toBeNull();
  });

  it('names activity log users by server nickname in the org context', async () => {
    render(<DiscordLogSection eventId={1} isAdmin />, {
      wrapper: wrapperFor(7),
    });
    await screen.findByTestId('discord-subtab-activity');
    openTab('discord-subtab-activity');
    const entry = await screen.findByTestId('discord-log-entry-9');
    expect(entry.textContent).toContain('GwenServer');
    const synthetic = screen.getByTestId('discord-log-entry--5');
    expect(synthetic.textContent).toContain('DragonClaw');
  });

  it('names the task firer by Discord name', async () => {
    render(<DiscordLogSection eventId={1} isAdmin />, {
      wrapper: wrapperFor(7),
    });
    expect(await screen.findByText('KettleGlobal')).toBeTruthy();
  });
});
