import type { UserType } from '~/index';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';

export const captainView = ({ user }: { user: UserType }) => {
  return (
    <div className="flex flex-row items-center gap-4 mb-4">
      <UserAvatar user={user} size="xl" />
      <span>
        Current Captain:
        {user ? DisplayName(user) : 'No captain selected'}
      </span>
    </div>
  );
};
