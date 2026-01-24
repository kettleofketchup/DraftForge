import { useCallback, useEffect, useMemo, useState } from 'react';
import type { UserClassType, UserType } from '~/components/user';
import UserEditModal from '~/components/user/userCard/editModal';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
const log = getLogger('hasErrors');

interface UserIssue {
  user: UserType;
  issues: string[];
}

function hasNoPositions(user: UserType): boolean {
  const positions = user.positions;
  if (!positions) return true;
  // Check if all position values are 0 or undefined
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

  // Compute users with issues
  const usersWithIssues = useMemo(() => {
    if (!tournament?.users) return [];

    const issues: UserIssue[] = [];

    for (const user of tournament.users) {
      const userIssues: string[] = [];

      if (!user.mmr) {
        userIssues.push('No MMR');
      }
      if (!user.steamid) {
        userIssues.push('No Steam ID');
      }
      if (hasNoPositions(user)) {
        userIssues.push('No positions');
      }

      if (userIssues.length > 0) {
        issues.push({ user, issues: userIssues });
      }
    }

    log.debug('Users with issues:', issues.length, issues);
    return issues;
  }, [tournament?.users]);

  return (
    <>
      {usersWithIssues.length > 0 && (
        <div className="flex flex-col items-start justify-center p-4 bg-red-950 rounded-lg shadow-md w-full mb-4">
          <div className="flex flex-col sm:flex-row gap-5 w-full">
            <div className="text-red-500 font-bold text-center w-full pb-5">
              <span className="text-lg">⚠️</span> {usersWithIssues.length} player{usersWithIssues.length !== 1 ? 's have' : ' has'} incomplete profiles
            </div>
          </div>

          <div className="w-full">
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 w-full">
              {usersWithIssues.map(({ user, issues }) => (
                <div className="bg-red-500/80 p-3 rounded-lg" key={user.pk}>
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
                      user={user as UserClassType}
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
