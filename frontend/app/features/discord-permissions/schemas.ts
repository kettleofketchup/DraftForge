import type {
  PermissionChecksRequest,
  PermissionCheckResult as ServerPermissionCheckResult,
} from './api.generated';
export * from './api.generated';
export type PermissionCheckResult = ServerPermissionCheckResult & {
  expired?: boolean;
};

export type PermissionScope = (
  | { kind: 'org'; orgId: number }
  | { kind: 'event'; eventId: number }
) & { guildId: string | null };
export type CheckDescriptor = PermissionChecksRequest['checks'][number];

export function isExpired(result: PermissionCheckResult, now: Date): boolean {
  if (result.expired) return true;
  if (!result.expires_at) return result.status === 'verified';
  const expiry = Date.parse(result.expires_at);
  return !Number.isFinite(expiry) || expiry <= now.getTime();
}
