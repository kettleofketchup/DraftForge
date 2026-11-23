import api from '~/components/api/axios';
import {
  DiscordBotStatusSchema,
  DiscordInstallLinkSchema,
  type DiscordBotStatus,
  type DiscordInstallLink,
} from './schemas';

export async function getDiscordBotStatus(
  orgId: number,
): Promise<DiscordBotStatus> {
  const response = await api.get(`/discord/organizations/${orgId}/bot-status/`);
  return DiscordBotStatusSchema.parse(response.data);
}

export async function getDiscordInstallLink(
  orgId: number,
): Promise<DiscordInstallLink> {
  const response = await api.get(
    `/discord/organizations/${orgId}/install-link/`,
  );
  return DiscordInstallLinkSchema.parse(response.data);
}
