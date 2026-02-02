import { useEffect } from 'react';
import { UserList } from '~/components/user';
import { useLeagueStore } from '~/store/leagueStore';

interface Props {
  leaguePk: number;
}

export const UsersTab: React.FC<Props> = ({ leaguePk }) => {
  const { leagueUsers, leagueUsersLoading, getLeagueUsers } = useLeagueStore();

  useEffect(() => {
    if (leaguePk) {
      getLeagueUsers(leaguePk);
    }
  }, [leaguePk, getLeagueUsers]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">League Members</h2>
        <span className="text-sm text-muted-foreground">
          {leagueUsers.length} {leagueUsers.length === 1 ? 'member' : 'members'}
        </span>
      </div>

      <UserList
        users={leagueUsers}
        isLoading={leagueUsersLoading}
        showSearch={leagueUsers.length > 5}
        searchPlaceholder="Search members..."
        emptyMessage="No members in this league"
      />
    </div>
  );
};
