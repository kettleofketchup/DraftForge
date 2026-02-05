import { Plus } from 'lucide-react';
import { memo, useCallback, useMemo, useState } from 'react';
import { addTournamentMember } from '~/components/api/api';
import type { AddMemberPayload } from '~/components/api/api';
import { Button } from '~/components/ui/button';
import { SearchUserDropdown } from '~/components/user/searchUser';
import type { UserType } from '~/components/user/types';
import { UserList } from '~/components/user';
import { AddUserModal } from '~/components/user/AddUserModal';
import { useUserStore } from '~/store/userStore';
import { useOrgStore } from '~/store/orgStore';
import { hasErrors } from '../hasErrors';

export const PlayersTab: React.FC = memo(() => {
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);
  const query = useUserStore((state) => state.userQuery);
  const setQuery = useUserStore((state) => state.setUserQuery);
  const isStaff = useUserStore((state) => state.isStaff);
  const currentOrg = useOrgStore((s) => s.currentOrg);
  const [showAddUser, setShowAddUser] = useState(false);

  const tournamentUsers = tournament?.users ?? [];

  // AddUserModal callbacks
  const handleAddMember = useCallback(
    async (payload: AddMemberPayload) => {
      if (!tournament?.pk) throw new Error('No tournament');
      const user = await addTournamentMember(tournament.pk, payload);
      // Optimistic update — append user to tournament's users array
      const current = useUserStore.getState().tournament;
      if (current) {
        setTournament({
          ...current,
          users: [...(current.users ?? []), user],
        });
      }
      return user;
    },
    [tournament?.pk, setTournament]
  );

  const addedPkSet = useMemo(
    () => new Set(tournamentUsers.map((u) => u.pk)),
    [tournamentUsers]
  );
  const isUserAdded = useCallback(
    (user: UserType) => user.pk != null && addedPkSet.has(user.pk),
    [addedPkSet]
  );

  const hasDiscordServer = Boolean(currentOrg?.discord_server_id);
  const canEdit = isStaff();

  // Grid columns for tournament players
  const gridCols = 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5';
  return (
    <div className="py-5 px-3 mx-auto container">
      {hasErrors()}

      <div className="grid grid-cols-2 gap-5 items-start pt-5  ">
        <div className="flex self-center place-self-stretch">
          <SearchUserDropdown
            users={tournamentUsers}
            query={query}
            setQuery={(val) => typeof val === 'string' ? setQuery(val) : setQuery(val(''))}
            data-testid="playerSearchDropdown"
          />
        </div>
        <div className="flex px-5 place-self-end">
          {canEdit && (
            <Button
              onClick={() => setShowAddUser(true)}
              data-testid="tournamentAddPlayerBtn"
            >
              <Plus className="w-4 h-4 mr-2" />
              Add Player
            </Button>
          )}
        </div>
      </div>

      <div className="mt-4">
        <UserList
          users={tournamentUsers}
          searchQuery={query}
          compact={true}
          deleteButtonType="tournament"
          gridCols={gridCols}
          emptyMessage="No players in this tournament"
        />
      </div>

      {canEdit && (
        <AddUserModal
          open={showAddUser}
          onOpenChange={setShowAddUser}
          title={`Add Player to ${tournament?.name || 'Tournament'}`}
          entityContext={{
            orgId: currentOrg?.pk,
            leagueId: tournament?.league_pk ?? undefined,
            tournamentId: tournament?.pk ?? undefined,
          }}
          onAdd={handleAddMember}
          isAdded={isUserAdded}
          entityLabel={tournament?.name || 'Tournament'}
          hasDiscordServer={hasDiscordServer}
        />
      )}
    </div>
  );
});
