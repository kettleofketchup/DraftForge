import { useCallback, useEffect, useState } from 'react';
import type { UserClassType, UserType } from '~/components/user';
import UserEditModal from '~/components/user/userCard/editModal';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
const log = getLogger('hasErrors');

export const hasErrors = () => {
  const allUsers = useUserStore((state) => state.users); // Zustand setter
  const [badUsers, setBadUsers] = useState([] as UserType[]);
  const tournament = useUserStore((state) => state.tournament);
  const getCurrentTournament = useUserStore(
    (state) => state.getCurrentTournament,
  ); // Zustand setter

  const createBadUsers = useCallback(async () => {
    setBadUsers([]); // Reset bad users

    var newBadUsers = [] as UserType[];

    for (const user of tournament.users || []) {
      if (!user.mmr) {
        newBadUsers.push(user);
      }
    }
    setBadUsers(newBadUsers);
    log.debug('Getting bad users', newBadUsers, tournament.users);
  }, [tournament.users]);

  useEffect(() => {
    if (!tournament || !tournament.users) {
      return;
    }
    createBadUsers();
  }, [tournament.users, allUsers]);

  return (
    <>
      {badUsers.length > 0 && (
        <div className="flex flex-col  items-start justify-center align-centerzs p-4 h-full bg-red-950 rounded-lg shadow-md w-full mb-4 content-center">
          <div className="flex flex-col sm:flex-row gap-5 w-full ">
            <div className="text-red-500 font-bold text-center w-full pb-5">
              <span className="text-lg">⚠️</span> Some players have no MMR.
            </div>
          </div>

          <div
            className="flex
        align-middle content-center justify-center
       grid-cols-4
         w-full "
          >
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-5 w-full items-center justify-center content-center align-center">
              {badUsers.map((user: UserType) => (
                <div className="bg-red-500 p-2 rounded-lg" key={user.pk}>
                  <span key={user.pk} className="text-white-500">
                    {!user.mmr && (
                      <>
                        <div
                          key={user.pk}
                          className="text-white-500 text-center underline  underline-offset-2 font-bold "
                        >
                          {user.nickname || user.username}
                        </div>

                        <div className="flex w-full justify-center text-center">
                          <pre>Has no MMR.</pre>
                        </div>
                      </>
                    )}
                  </span>
                  <div className="flex self-center content-center align-middle justify-center mt-2">
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
