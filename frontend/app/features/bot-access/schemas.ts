import type { BotAccessRow, ServiceState } from './schemas.generated';

export {
  BotAccessRowSchema,
  BotAccessSnapshotSchema,
  BotIdentitySchema,
  PlatformLinkSchema,
  ServiceStateSchema,
  type BotAccessRow,
  type BotAccessSnapshot,
  type BotIdentity,
  type PlatformLink,
  type ServiceState,
} from './schemas.generated';

export type BotStatus = NonNullable<BotAccessRow['status']>;
export type AccessState = BotAccessRow['access'];
export type ServiceStatus = ServiceState['status'];

export const ALLOWED_LINK_HOSTS = [
  'steamcommunity.com',
  'www.dota2.com',
] as const;

export function isAllowedExternalLink(url: string): boolean {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  return (
    parsed.protocol === 'https:' &&
    (ALLOWED_LINK_HOSTS as readonly string[]).includes(parsed.hostname)
  );
}
