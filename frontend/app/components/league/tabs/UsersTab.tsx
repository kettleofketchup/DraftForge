import { Plus } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { addLeagueMember } from '~/components/api/api';
import type { AddMemberPayload } from '~/components/api/api';
import { PrimaryButton } from '~/components/ui/buttons';
import { UserList } from '~/components/user';
import { AddUserModal } from '~/components/user/AddUserModal';
import type { UserType } from '~/components/user/types';
import { useIsLeagueAdmin } from '~/hooks/usePermissions';
import { useLeagueUsers } from '~/hooks/useLeagueUsers';
import { useLeagueStore } from '~/store/leagueStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useOrgStore } from '~/store/orgStore';

interface Props {
  leaguePk: number;
}

export const UsersTab: React.FC<Props> = ({ leaguePk }) => {
  const { leagueUserPks, leagueUsersLoading, getLeagueUsers } = useLeagueStore();
  const leagueUsers = useLeagueUsers(leaguePk);
  const currentLeague = useLeagueStore((s) => s.currentLeague);
  const currentOrg = useOrgStore((s) => s.currentOrg);
  const [showAddUser, setShowAddUser] = useState(false);

  const canEdit = useIsLeagueAdmin(currentLeague);

  useEffect(() => {
    if (leaguePk) {
      getLeagueUsers(leaguePk);
    }
  }, [leaguePk, getLeagueUsers]);

  // AddUserModal callbacks
  const handleAddMember = useCallback(
    async (payload: AddMemberPayload) => {
      if (!leaguePk) throw new Error('No league');
      const user = await addLeagueMember(leaguePk, payload);
      // Optimistic update: upsert into cache + append pk
      useUserCacheStore.getState().upsert(user, { leagueId: leaguePk });
      const { leagueUserPks } = useLeagueStore.getState();
      if (user.pk != null) {
        useLeagueStore.setState({ leagueUserPks: [...leagueUserPks, user.pk] });
      }
      return user;
    },
    [leaguePk]
  );

  const addedPkSet = useMemo(
    () => new Set(leagueUserPks),
    [leagueUserPks]
  );
  const isUserAdded = useCallback(
    (user: UserType) => user.pk != null && addedPkSet.has(user.pk),
    [addedPkSet]
  );

  const hasDiscordServer = Boolean(currentOrg?.discord_server_id);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">League Members</h2>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">
            {leagueUsers.length} {leagueUsers.length === 1 ? 'member' : 'members'}
          </span>
          {canEdit && (
            <PrimaryButton
              size="sm"
              onClick={() => setShowAddUser(true)}
              data-testid="league-add-member-btn"
            >
              <Plus className="w-4 h-4 mr-2" />
              Add Member
            </PrimaryButton>
          )}
        </div>
      </div>

      <UserList
        users={leagueUsers}
        isLoading={leagueUsersLoading}
        showSearch={leagueUsers.length > 5}
        searchPlaceholder="Search members..."
        emptyMessage="No members in this league"
      />

      {canEdit && (
        <AddUserModal
          open={showAddUser}
          onOpenChange={setShowAddUser}
          title={`Add Member to ${currentLeague?.name || 'League'}`}
          entityContext={{
            orgId: currentOrg?.pk,
            leagueId: leaguePk,
          }}
          onAdd={handleAddMember}
          isAdded={isUserAdded}
                    hasDiscordServer={hasDiscordServer}
        />
      )}
    </div>
  );
};
