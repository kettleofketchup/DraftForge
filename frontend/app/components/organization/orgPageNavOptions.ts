import type { PageNavOption } from '~/store/pageNavStore';

export interface OrgPageNavInput {
  leaguesCount: number;
  eventsCount: number;
  userCountDisplay: number | string;
  canViewMembers: boolean;
  standingTabs: readonly { value: string; label: string }[];
  canUsePromotion: boolean;
  canViewClaims: boolean;
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
  for (const tab of input.standingTabs) {
    opts.push({ value: tab.value, label: tab.label });
  }
  if (input.canUsePromotion) {
    opts.push({ value: 'promotion', label: 'Promotion' });
  }
  if (input.canViewClaims) {
    opts.push({ value: 'claims', label: 'Claims' });
  }
  return opts;
}
