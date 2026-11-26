import type { CheckDescriptor, PermissionScope } from './schemas';

export function normalizeDescriptors(
  descriptors: CheckDescriptor[],
): CheckDescriptor[] {
  return descriptors
    .map((d) => ({ ...d, role_ids: [...(d.role_ids ?? [])].sort() }))
    .sort((a, b) => a.key.localeCompare(b.key));
}

export const discordPermissionKeys = {
  all: ['discordPermissions'] as const,
  scope: (viewerPk: number, scope: PermissionScope) =>
    ['discordPermissions', viewerPk, scope] as const,
  draft: (
    viewerPk: number,
    scope: PermissionScope,
    descriptors: CheckDescriptor[],
  ) =>
    [
      ...discordPermissionKeys.scope(viewerPk, scope),
      'draft',
      normalizeDescriptors(descriptors),
    ] as const,
  saved: (viewerPk: number, eventId: number, guildId: string | null) =>
    [
      ...discordPermissionKeys.scope(viewerPk, {
        kind: 'event',
        eventId,
        guildId,
      }),
      'saved',
    ] as const,
};
