export const discordKeys = {
  all: ['discord'] as const,
  roles: (orgId: number) => [...discordKeys.all, 'roles', orgId] as const,
  channels: (orgId: number) => [...discordKeys.all, 'channels', orgId] as const,
};
