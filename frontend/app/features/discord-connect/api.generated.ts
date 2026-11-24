// GENERATED FILE - DO NOT EDIT.
// Source: backend/discordbot/install_schemas.py
// Regenerate with: just py::gen-discord-connect-api
import { z } from 'zod';

export const DiscordBotStatusSchema = z.object({
  has_bot: z.boolean(),
  reason: z.union([z.literal('no_server_configured'), z.null()]),
  guild_name: z.union([z.string(), z.null()]),
});
export type DiscordBotStatus = z.infer<typeof DiscordBotStatusSchema>;

export const DiscordConnectErrorSchema = z.enum([
  'cancelled',
  'expired',
  'forbidden',
  'invalid_server',
  'bot_missing',
]);
export type DiscordConnectError = z.infer<typeof DiscordConnectErrorSchema>;

export const DiscordInstallLinkSchema = z.object({ url: z.string() });
export type DiscordInstallLink = z.infer<typeof DiscordInstallLinkSchema>;

export const DiscordConnectApiSchema = z.object({
  install_link: DiscordInstallLinkSchema,
  bot_status: DiscordBotStatusSchema,
  connect_error: DiscordConnectErrorSchema,
});
export type DiscordConnectApi = z.infer<typeof DiscordConnectApiSchema>;
