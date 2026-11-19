import type {
  DraftResetConflict,
  DraftTeamUsage,
} from '~/components/api/types';

export const countOf = (count: number, singular: string, plural: string) =>
  `${count} ${count === 1 ? singular : plural}`;

export const joinAnd = (items: string[]) =>
  items.length <= 1
    ? (items[0] ?? '')
    : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;

export const usageCount = (usage: DraftTeamUsage) =>
  countOf(usage.count, usage.label, usage.label_plural);

/** "2 games, 1 HeroDraft and 4 bracket slots" */
export const usageBreakdown = (usage: DraftTeamUsage[]) =>
  joinAnd(usage.map(usageCount));

export const usageTeamNames = (usage: DraftTeamUsage[]) => {
  const names = new Map<number, string>();
  for (const kind of usage) {
    for (const team of kind.teams) names.set(team.pk, team.name);
  }
  return [...names.values()];
};

const usageTotal = (usage: DraftTeamUsage[]) =>
  usage.reduce((sum, kind) => sum + kind.count, 0);

export const forceResetMessage = ({ usage }: DraftResetConflict) => {
  const teams = usageTeamNames(usage);
  if (!usage.length || !teams.length) {
    return 'Games or other records use these teams. Resetting keeps those records, but these teams go back to just their captains.';
  }
  const verb = usageTotal(usage) === 1 ? 'uses' : 'use';
  const after =
    teams.length === 1
      ? 'this team goes back to just its captain'
      : 'these teams go back to just their captains';
  return `${usageBreakdown(usage)} ${verb} ${joinAnd(teams)}. Resetting keeps those records, but ${after}.`;
};

const REASONS: Record<string, string> = {
  no_captain: 'No captain',
  captain_not_in_pool: 'Captain is not in the player pool',
};

export const ineligibleReasonText = (reason: string) =>
  REASONS[reason] ?? reason;
