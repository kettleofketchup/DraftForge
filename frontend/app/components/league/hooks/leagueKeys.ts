export const leagueKeys = {
  all: ['leagues'] as const,
  list: (orgId?: number) => ['leagues', 'list', orgId ?? 'all'] as const,
};
