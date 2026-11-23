import { afterEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';
import { getDiscordBotStatus, getDiscordInstallLink } from '../api';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: { get } }));

afterEach(() => get.mockReset());

describe('discord connect api', () => {
  it('parses the bot status', async () => {
    get.mockResolvedValue({
      data: { has_bot: true, reason: null, guild_name: 'Kettle Server' },
    });
    await expect(getDiscordBotStatus(4)).resolves.toEqual({
      has_bot: true,
      reason: null,
      guild_name: 'Kettle Server',
    });
    expect(get).toHaveBeenCalledWith('/discord/organizations/4/bot-status/');
  });

  it('rejects a bot status missing a field', async () => {
    get.mockResolvedValue({ data: { has_bot: false } });
    await expect(getDiscordBotStatus(4)).rejects.toBeInstanceOf(ZodError);
  });

  it('parses the install link', async () => {
    get.mockResolvedValue({
      data: { url: 'https://discord.com/oauth2/authorize?client_id=1' },
    });
    await expect(getDiscordInstallLink(4)).resolves.toEqual({
      url: 'https://discord.com/oauth2/authorize?client_id=1',
    });
    expect(get).toHaveBeenCalledWith('/discord/organizations/4/install-link/');
  });
});
