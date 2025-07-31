import { useState } from 'react';
import type { UserClassType, UserType } from '~/components/user/types';

import { User } from '~/components/user/user';
import { AvatarUrl } from '~/index';
interface Props {
  users: UserType[];
}

export const UsersDropdown: React.FC<Props> = ({ users }) => {
  const [createModal, setCreateModal] = useState<boolean>(false);

  const [selectedDiscordUser, setSelectedDiscordUser] = useState(
    new User({} as UserClassType),
  );

  const showUser = (user: UserType) => {
 

    return (
      <>
        <li
          key={`userdropdown-${user.pk || user.username}`}
          className="flex items-center gap-3 py-2"
        >
          <div className="avatar">
            <div className="w-8 h-8 rounded-full">
              <img src={AvatarUrl(user)} alt={user.nickname || user.username} />
            </div>
          </div>
          <a
            href={`/users/${user.pk ?? user.username}`}
            className="link link-primary"
          >
            {user.nickname || user.username}
          </a>
        </li>
      </>
    );
  };
  return (
    <>
      {users && users.length > 0 && (
        <div className="collapse collapse-arrow border border-base-300 bg-base-200 rounded-box">
          <input type="checkbox" />
          <div className="collapse-title text-md font-medium">
            Players ({users.length})
          </div>
          <div className="collapse-content">
            <ul className="list-disc list-inside ml-4">
              {users.map((user) => showUser(user))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
};
