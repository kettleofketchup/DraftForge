// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getDiscordBotStatus, getDiscordInstallLink } from '../api';
import { DiscordConnectionCard } from '../DiscordConnectionCard';

vi.mock('../api', () => ({
  getDiscordBotStatus: vi.fn(),
  getDiscordInstallLink: vi.fn(),
}));

const assign = vi.fn();
Object.defineProperty(window, 'location', {
  value: { ...window.location, assign },
  writable: true,
});

function renderCard(
  props: Partial<Parameters<typeof DiscordConnectionCard>[0]> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <DiscordConnectionCard
        orgId={4}
        serverId={null}
        hasUnsavedChanges={false}
        {...props}
      />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.mocked(getDiscordBotStatus).mockReset();
  vi.mocked(getDiscordInstallLink).mockReset();
  assign.mockReset();
});

describe('DiscordConnectionCard', () => {
  it('connects an org with no server by sending the browser to Discord', async () => {
    vi.mocked(getDiscordBotStatus).mockResolvedValue({
      has_bot: false,
      reason: 'no_server_configured',
      guild_name: null,
    });
    vi.mocked(getDiscordInstallLink).mockResolvedValue({
      url: 'https://discord.com/oauth2/authorize?x=1',
    });
    renderCard();

    expect(await screen.findByTestId('org-discord-not-connected')).toBeTruthy();
    fireEvent.click(
      screen.getByRole('button', { name: /connect discord server/i }),
    );

    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith(
        'https://discord.com/oauth2/authorize?x=1',
      ),
    );
    expect(getDiscordInstallLink).toHaveBeenCalledWith(4);
  });

  it('shows the connected server name and offers to switch', async () => {
    vi.mocked(getDiscordBotStatus).mockResolvedValue({
      has_bot: true,
      reason: null,
      guild_name: 'Kettle Server',
    });
    renderCard({ serverId: '123456789012345678' });

    expect(
      (await screen.findByTestId('org-discord-connected')).textContent,
    ).toContain('Kettle Server');
    expect(
      screen.getByText(
        'Bot connected — action permissions are checked in event settings',
      ),
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: /switch server/i })).toBeTruthy();
  });

  it('flags a configured server the bot is missing from', async () => {
    vi.mocked(getDiscordBotStatus).mockResolvedValue({
      has_bot: false,
      reason: null,
      guild_name: null,
    });
    renderCard({ serverId: '123456789012345678' });

    expect(await screen.findByTestId('org-discord-bot-missing')).toBeTruthy();
    expect(
      screen.getByRole('button', { name: /add bot to server/i }),
    ).toBeTruthy();
  });

  it('blocks leaving for Discord while settings are unsaved', async () => {
    vi.mocked(getDiscordBotStatus).mockResolvedValue({
      has_bot: false,
      reason: 'no_server_configured',
      guild_name: null,
    });
    renderCard({ hasUnsavedChanges: true });

    const button = await screen.findByTestId('org-discord-connect-button');
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(
      screen.getByText(/save or discard your changes first/i),
    ).toBeTruthy();
  });
});
