import { useMemo } from 'react';
import type { UserClassType, UserType } from '~/components/user';
import { brandErrorBg, brandErrorCard } from '~/components/ui/buttons';
import UserEditModal from '~/components/user/userCard/editModal';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import type { UserEntry } from '~/store/userCacheTypes';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
const log = getLogger('hasErrors');

interface UserIssue {
  user: UserClassType;
  issues: string[];
}

/** Convert a UserEntry to a UserType-like object with org-scoped fields flattened. */
function toUserType(entry: UserEntry, orgId?: number): UserClassType {
  const orgData = orgId ? entry.orgData[orgId] : undefined;
  return {
    ...entry,
    orgUserPk: orgData?.id,
    mmr: orgData?.mmr,
  } as unknown as UserClassType;
}

function hasNoPositions(user: UserEntry): boolean {
  const positions = user.positions;
  if (!positions) return true;
  const totalPreference =
    (positions.carry || 0) +
    (positions.mid || 0) +
    (positions.offlane || 0) +
    (positions.soft_support || 0) +
    (positions.hard_support || 0);
  return totalPreference === 0;
}

export const hasErrors = () => {
  const tournament = useUserStore((state) => state.tournament);
  const entities = useUserCacheStore((state) => state.entities);

  const orgId = tournament?.organization_pk ?? undefined;

  // Resolve users from entity cache — the single source of truth
  const usersWithIssues = useMemo(() => {
    if (!tournament?.users) return [];

    const issues: UserIssue[] = [];

    for (const userRef of tournament.users) {
      const pk = typeof userRef === 'number' ? userRef : (userRef as UserType)?.pk;
      if (!pk) continue;

      const cached = entities[pk];
      if (!cached) continue;

      const userIssues: string[] = [];

      // Check org-scoped MMR from the entity cache
      const mmr = orgId ? cached.orgData[orgId]?.mmr : undefined;
      if (!mmr) {
        userIssues.push('No MMR');
      }
      if (!cached.steam_account_id) {
        userIssues.push('No Friend ID');
      }
      if (hasNoPositions(cached)) {
        userIssues.push('No positions');
      }

      if (userIssues.length > 0) {
        issues.push({ user: toUserType(cached, orgId), issues: userIssues });
      }
    }

    log.debug('Users with issues:', issues.length, issues);
    return issues;
  }, [tournament?.users, entities, orgId]);

  return (
    <>
      {usersWithIssues.length > 0 && (
        <div className={cn('flex flex-col items-start justify-center p-4 rounded-lg shadow-md w-full mb-4', brandErrorBg)}>
          <div className="flex flex-col sm:flex-row gap-5 w-full">
            <div className="text-red-500 font-bold text-center w-full pb-5">
              <span className="text-lg">⚠️</span> {usersWithIssues.length} player{usersWithIssues.length !== 1 ? 's have' : ' has'} incomplete profiles
            </div>
          </div>

          <div className="w-full">
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 w-full">
              {usersWithIssues.map(({ user, issues }) => (
                <div className={cn('p-3 rounded-lg', brandErrorCard)} key={user.pk}>
                  <div className="text-white text-center underline underline-offset-2 font-bold mb-2">
                    {user.nickname || user.username}
                  </div>
                  <div className="flex flex-col gap-1 text-center text-sm text-red-100">
                    {issues.map((issue) => (
                      <span key={issue}>{issue}</span>
                    ))}
                  </div>
                  <div className="flex justify-center mt-3">
                    <UserEditModal
                      user={user}
                      key={`UserEditModal-${user.pk}`}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
};
