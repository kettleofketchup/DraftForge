import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type {
  GuildMember,
  UserType,
  UserClassType,
} from '~/components/user/types';
import { UserCard } from '~/components/user/userCard';
import axios from '~/components/api/axios';
import { useUserStore } from '~/store/userStore';
import {
  Combobox,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
} from '@headlessui/react';
import Footer from '~/components/footer';
import DiscordUserDropdown from '~/components/user/DiscordUserDropdown';
import { User } from '~/components/user/user';

interface Props {}

export const CreateUserButton = () => {
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
  const openCreateModal = () => setCreateModal(true);

  const closeCreateModal = () => setCreateModal(false);

  return (
    <>
      <label
        htmlFor="create_user_modal"
        className="btn outline outline-green-500 rounded-lg hover:bg-green-900/50 hover:shadow-xl/10 delay-10 duration-300 ease-in-out"
      >
        Create User
      </label>

      <input
        type="checkbox"
        id="create_user_modal"
        className="modal-toggle"
        onClick={openCreateModal}
      />

      <div className="modal" role="dialog">
        <div className="modal-box">
          <h3 className="text-lg font-bold">Select Discord User</h3>
          <DiscordUserDropdown onSelect={handleDiscordUserSelect} />
          <UserCard
            user={selectedDiscordUser}
            edit={true}
            saveFunc={'create'}
            key="modal_usercard"
          />
          <label className="modal-backdrop" htmlFor="my_modal_7">
            Close
          </label>
        </div>
        <button></button>
      </div>
    </>
  );
};
