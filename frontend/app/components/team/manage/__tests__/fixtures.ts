import teams from '~/components/api/__tests__/fixtures/managedTeam.json';
import historyJson from '~/components/api/__tests__/fixtures/teamHistoryPage.json';
import {
  ManagedTeamSchema,
  TeamHistoryPageSchema,
  type LeadershipProblem,
  type ManagedTeam,
  type TeamHistoryPage,
  type TeamLog,
} from '~/components/api/teamManagementAPI';

export const managedTeam: ManagedTeam = ManagedTeamSchema.parse(
  teams.managedTeam,
);
export const ghostCaptainTeam: ManagedTeam = ManagedTeamSchema.parse(
  teams.ghostCaptainTeam,
);
export const historyPage: TeamHistoryPage =
  TeamHistoryPageSchema.parse(historyJson);

const [captain, deputy, member] = managedTeam.members;
const dropout = managedTeam.left_members[0];
const standin = managedTeam.dropin_members[0];
// On no roster of managedTeam.
const outsider = ghostCaptainTeam.captain!;

const captainNotMember: LeadershipProblem =
  ghostCaptainTeam.leadership_problems[0];
const deputyNotMember: LeadershipProblem = {
  field: 'deputy_captain',
  code: 'deputy_not_member',
  message: 'Deputy captain must be a member of the team.',
};

export const ghostDeputyTeam: ManagedTeam = {
  ...managedTeam,
  deputy_captain: outsider,
  leadership_problems: [deputyNotMember],
};

export const ghostCaptainDropoutTeam: ManagedTeam = {
  ...managedTeam,
  captain: dropout,
  leadership_problems: [captainNotMember],
};

export const ghostCaptainStandinTeam: ManagedTeam = {
  ...managedTeam,
  captain: standin,
  leadership_problems: [captainNotMember],
};

export const singleMemberTeam: ManagedTeam = {
  ...managedTeam,
  members: [captain],
  dropin_members: [],
  left_members: [],
  deputy_captain: null,
};

export const UNRESOLVABLE_PK = 99;

const [standinRow, dropoutRow] = historyPage.results;

export const systemRow: TeamLog = {
  ...dropoutRow,
  id: 3,
  actor: null,
  via: 'system',
  action: 'system_succession',
};

export const violationsRow: TeamLog = {
  ...standinRow,
  id: 4,
  override_rules: ['team_standin_cap'],
  details: {
    ...standinRow.details,
    violations: [
      {
        code: 'team_standin_cap',
        rule: 'override-warning',
        message: 'The team already has 1 stand-ins (limit 1).',
        category: 'team',
        blocking: false,
        params: {},
      },
    ],
  },
};

export const overrideRulesOnlyRow: TeamLog = {
  ...standinRow,
  id: 5,
  override_rules: ['team_standin_cap'],
};

const before = dropoutRow.details.before as Record<string, unknown>;
export const unresolvableCaptainRow: TeamLog = {
  ...dropoutRow,
  id: 6,
  action: 'set_captain',
  target: null,
  details: {
    before,
    after: { ...before, captain_id: UNRESOLVABLE_PK },
  },
};

export const richHistoryPage: TeamHistoryPage = {
  ...historyPage,
  count: historyPage.count + 4,
  results: [
    unresolvableCaptainRow,
    overrideRulesOnlyRow,
    violationsRow,
    systemRow,
    ...historyPage.results,
  ],
};

export const people = { captain, deputy, member, dropout, standin, outsider };
