import type { PageNavOption } from '~/store/pageNavStore';

export interface OrgPageNavInput {
  leaguesCount: number;
  eventsCount: number;
  userCountDisplay: number | string;
  canViewMembers: boolean;
  canViewContributions: boolean;
  canUsePromotion: boolean;
  canViewClaims: boolean;
  canViewSettings: boolean;
}

// Mobile page-nav entries; must match the desktop TabsList gates.
export function buildOrgPageNavOptions(
  input: OrgPageNavInput,
): PageNavOption[] {
  const opts: PageNavOption[] = [
    { value: 'leagues', label: `Leagues (${input.leaguesCount})` },
    { value: 'events', label: `Events (${input.eventsCount})` },
  ];
  if (input.canViewMembers) {
    opts.push({ value: 'users', label: `Users (${input.userCountDisplay})` });
  }
  if (input.canViewContributions) {
    opts.push({ value: 'contributions', label: 'Contributions' });
  }
  if (input.canUsePromotion) {
    opts.push({ value: 'promotion', label: 'Promotion' });
  }
  if (input.canViewClaims) {
    opts.push({ value: 'claims', label: 'Claims' });
  }
  if (input.canViewSettings) {
    opts.push({ value: 'settings', label: 'Settings' });
  }
  return opts;
}
