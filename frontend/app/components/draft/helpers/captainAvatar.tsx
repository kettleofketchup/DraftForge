import type { UserType } from '~/index';
import { AvatarUrl, DisplayName } from '~/components/user/avatar';

export const captainView = ({ user }: { user: UserType }) => {
  return (
    <div className="flex flex-row items-center gap-4 mb-4">
      <img
        src={AvatarUrl(user)}
        alt="User Avatar"
        className="w-12 h-12 rounded-full"
      />
      <span>
        Current Captain:
        {user ? DisplayName(user) : 'No captain selected'}
      </span>
    </div>
  );
};
