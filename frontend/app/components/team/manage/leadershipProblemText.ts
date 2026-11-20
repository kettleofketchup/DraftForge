import type { DisplayName } from '~/components/user/avatar';

export type UserLike = NonNullable<Parameters<typeof DisplayName>[0]>;

type ProblemLike = { field?: string; code: string; message: string };
type LeadershipLike = {
  captain?: UserLike | null;
  deputy_captain?: UserLike | null;
};

const NOT_MEMBER = 'is not a member of this team.';

/** Splits a problem into a user to render with DisplayName and the text after it. */
export function leadershipProblemParts(
  problem: ProblemLike,
  team: LeadershipLike,
): { subject: UserLike | null; text: string } {
  switch (problem.code) {
    case 'captain_not_member':
      return { subject: team.captain ?? null, text: NOT_MEMBER };
    case 'deputy_not_member':
      return { subject: team.deputy_captain ?? null, text: NOT_MEMBER };
    case 'deputy_is_captain':
      return {
        subject: team.deputy_captain ?? null,
        text: 'is also the captain.',
      };
    default:
      return { subject: null, text: problem.message };
  }
}
