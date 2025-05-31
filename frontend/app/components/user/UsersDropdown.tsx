import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type {
  GuildMember,
  UserType,
  UserClassType,
} from '~/components/user/types';

import { User } from '~/components/user/user';

interface Props {
  users: UserType[];
}

export const UsersDropdown: React.FC<Props> = ({ users }) => {
  const [createModal, setCreateModal] = useState<boolean>(false);

  const [selectedDiscordUser, setSelectedDiscordUser] = useState(
    new User({} as UserClassType),
  );

  const handleDiscordUserSelect = (user: GuildMember) => {
    console.log(selectedDiscordUser);
    selectedDiscordUser.setFromGuildMember(user);
    //This is necessary because we need a new instance of user to trigger a re-render
    setSelectedDiscordUser(new User(selectedDiscordUser as UserClassType));
  };

  const showUser = (user: UserType) => {
    let avatarUrl: string;
    if (user.avatar) {
      avatarUrl = user.avatarUrl;
    } else {
      avatarUrl = `https://ui-avatars.com/api/?name=${encodeURIComponent(user.nickname || user.username)}`;
    }

    return (
      <>
        <li
          key={user.pk || user.username}
          className="flex items-center gap-3 py-2"
        >
          <div className="avatar">
            <div className="w-8 h-8 rounded-full">
              <img src={avatarUrl} alt={user.nickname || user.username} />
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
