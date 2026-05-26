import { Plus, Upload } from 'lucide-react';
import { memo, useCallback, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { addTournamentMember } from '~/components/api/api';
import type { AddMemberPayload } from '~/components/api/api';
import type { TournamentType } from '~/components/tournament/types';
import { PrimaryButton } from '~/components/ui/buttons';
import { SearchUserDropdown } from '~/components/user/searchUser';
import type { UserType } from '~/components/user/types';
import { UserList } from '~/components/user';
import { AddUserModal } from '~/components/user/AddUserModal';
import { CSVImportModal } from '~/components/user/CSVImportModal';
import { hydrateTournament } from '~/lib/hydrateTournament';
import { useUserStore } from '~/store/userStore';
import { useOrgStore } from '~/store/orgStore';
import { useLeagueStore } from '~/store/leagueStore';
import { useIsLeagueStaff } from '~/hooks/usePermissions';
import { hasErrors } from '../hasErrors';

export const PlayersTab: React.FC = memo(() => {
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);
  const query = useUserStore((state) => state.userQuery);
  const setQuery = useUserStore((state) => state.setUserQuery);
  const isStaff = useUserStore((state) => state.isStaff);
  const currentOrg = useOrgStore((s) => s.currentOrg);
  const queryClient = useQueryClient();
  const [showAddUser, setShowAddUser] = useState(false);
  const [showCSVImport, setShowCSVImport] = useState(false);

  const tournamentUsers = tournament?.users ?? [];

  // AddUserModal callbacks
  const handleAddMember = useCallback(
    async (payload: AddMemberPayload): Promise<UserType> => {
      if (!tournament?.pk) throw new Error('No tournament');
      const oldPks = new Set(
        (useUserStore.getState().tournament?.users ?? []).map((u) => u.pk),
      );
      const rawTournament = await addTournamentMember(tournament.pk, payload);
      const hydrated = hydrateTournament(rawTournament as TournamentType & { _users?: Record<number, unknown> }) as TournamentType;
      setTournament(hydrated);
      // Invalidate React Query cache so useTournament refetches
      queryClient.invalidateQueries({ queryKey: ['tournament', tournament.pk] });
      // Return the newly added user to satisfy AddUserModal's onAdd contract
      const addedUser = (hydrated.users ?? []).find(
        (u) => u.pk != null && !oldPks.has(u.pk),
      );
      if (!addedUser) throw new Error('Added user not found in response');
      return addedUser;
    },
    [tournament?.pk, setTournament, queryClient]
  );

  const addedPkSet = useMemo(
    () => new Set(tournamentUsers.map((u) => u.pk)),
    [tournamentUsers]
  );
  const isUserAdded = useCallback(
    (user: UserType) => user.pk != null && addedPkSet.has(user.pk),
    [addedPkSet]
  );

  const currentLeague = useLeagueStore((s) => s.currentLeague);
  const isLeagueStaff = useIsLeagueStaff(currentLeague);
  const hasDiscordServer = Boolean(currentOrg?.discord_server_id);
  const canEdit = isStaff() || isLeagueStaff;

  // Grid columns for tournament players (mobile-first ColumnBreakpoints
  // for the virtualized UserList grid).
  const cols = { base: 1, sm: 2, lg: 3, xl: 4, '2xl': 5 } as const;
  return (
    <div className="py-5 px-3 mx-auto container">
      {hasErrors()}

      <div className="flex flex-col-reverse md:flex-row gap-3 items-stretch md:items-start pt-5">
        <div className="flex flex-1">
          <SearchUserDropdown
            users={tournamentUsers}
            query={query}
            setQuery={(val) => typeof val === 'string' ? setQuery(val) : setQuery(val(''))}
            data-testid="playerSearchDropdown"
          />
        </div>
        {canEdit && (
          <div className="flex flex-col sm:flex-row md:px-5 gap-2 shrink-0">
            <PrimaryButton
              onClick={() => setShowCSVImport(true)}
              data-testid="tournament-csv-import-btn"
              className="w-full sm:flex-1 md:flex-none md:w-auto"
            >
              <Upload className="w-4 h-4 mr-2" />
              Import CSV
            </PrimaryButton>
            <PrimaryButton
              onClick={() => setShowAddUser(true)}
              data-testid="tournamentAddPlayerBtn"
              className="w-full sm:flex-1 md:flex-none md:w-auto"
            >
              <Plus className="w-4 h-4 mr-2" />
              Add Player
            </PrimaryButton>
          </div>
        )}
      </div>

      <div className="mt-4">
        <UserList
          users={tournamentUsers}
          searchQuery={query}
          compact={true}
          deleteButtonType="tournament"
          cols={cols}
          emptyMessage="No players in this tournament"
        />
      </div>

      {canEdit && tournament?.pk && (
        <CSVImportModal
          open={showCSVImport}
          onOpenChange={setShowCSVImport}
          entityContext={{
            orgId: currentOrg?.pk,
            tournamentId: tournament.pk,
          }}
          onComplete={() => {
            // Invalidate React Query cache so useTournament refetches
            queryClient.invalidateQueries({ queryKey: ['tournament', tournament.pk] });
          }}
        />
      )}

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
                    hasDiscordServer={hasDiscordServer}
        />
      )}
    </div>
  );
});
