import { useEffect, useState } from 'react'
import type { FormEvent } from 'react';
import type { GuildMember, UserType, UserClassType } from '~/components/user/types';
import { UserCard } from '~/components/user/userCard';
import axios from "~/components/api/axios"
import { useUserStore } from '~/store/userStore';
import { Combobox, ComboboxInput, ComboboxOption, ComboboxOptions } from '@headlessui/react'
import Footer from '~/components/footer';
import DiscordUserDropdown from "~/components/user/DiscordUserDropdown";
import { User } from '~/components/user/user';



export function UsersPage() {
  const user: UserType = useUserStore((state) => state.user); // Zustand setter
  const getUsers = useUserStore((state) => state.getUsers); // Zustand setter
  const users = useUserStore((state) => state.users); // Zustand setter

  const [createModal, setCreateModal] = useState<boolean>(false);

  const [query, setQuery] = useState('');
  const [selectedDiscordUser, setSelectedDiscordUser] = useState(new User({} as UserClassType));
  const [searchedPerson, setSearchedPerson] = useState(new User({} as UserClassType));

  const filteredUsers =
  query === ''
    ? users
    : users.filter((person) => {
        const q = query.toLowerCase();
        return (
          person.username?.toLowerCase().includes(q) ||
          person.nickname?.toLowerCase().includes(q)
        );
      });


    const handleSearchUserSelect = (user: User) => {
      setSearchedPerson(new User(user));

    };
  const handleDiscordUserSelect = (user: GuildMember) => {
    console.log(selectedDiscordUser)
    selectedDiscordUser.setFromGuildMember(user);
    //This is necessary because we need a new instance of user to trigger a re-render
    setSelectedDiscordUser(new User(selectedDiscordUser as UserClassType))


  };
  const openCreateModal = () => {
    setCreateModal(true);
  }
  const closeCreateModal = () => {
    setCreateModal(false);
  }
  const searchBar = () => {
    return (
      <div className="justify-self-top content-self-center align-middle ">

        {users && (
        <Combobox value={query} onChange={handleSearchUserSelect}>
                <ComboboxInput
                  className="input input-bordered w-full"
                  placeholder="Search DTX members..."
                  onChange={(event) => setQuery(event.target.value)}
                />
                <ComboboxOptions className="border bg-base-100 shadow-lg rounded-lg max-h-60 overflow-y-auto mt-2">
                  {filteredUsers && filteredUsers.length > 0
                   && filteredUsers.length < 20 ? (
                    filteredUsers.map((user) => (
                      <ComboboxOption
                        key={user.discordId}
                        value={user}
                        className={({ active }) =>
                          `cursor-pointer select-none p-2 ${
                            active ? "bg-primary text-primary-content" : ""
                          }`
                        }
                      >
                        <div className="flex items-center gap-2">
                          <img
                            src={
                              user.avatar
                                ? `https://cdn.discordapp.com/avatars/${user.discordId}/${user.avatar}`
                                : "https://via.placeholder.com/32"
                            }
                            alt={user.username}
                            className="w-8 h-8 rounded-full"
                          />
                          <span>{user.username}</span>
                        </div>
                      </ComboboxOption>
                    ))
                  ) : (
                    <div className="p-2 text-sm text-gray-500">No users or too many users found</div>
                  )}
                </ComboboxOptions>
              </Combobox>
        )}
      </div>
    );
  };

  if (!user || !user.is_staff)
    return (
      <div className="flex justify-center h-full content-center mb-0 mt-0 p-0">
        <div className="justify-self-center content-center align-middle">
          <span> You are not authorized to view this page</span>
        </div>
      </div>
    );

  useEffect(() => {
    getUsers();
  }, []);
  const addUserBtn = () => {
    return (
      <>
        <label
          htmlFor="create_user_modal"
          className="btn outline outline-green-500 rounded-lg hover:bg-green-900/50 hover:shadow-xl/10 delay-10 duration-300 ease-in-out"
        >
          Create User
        </label>

        <input type="checkbox" id="create_user_modal" className="modal-toggle" onClick={openCreateModal} />

        <div className="modal" role="dialog">
          <div className="modal-box">
            <h3 className="text-lg font-bold">Select Discord User</h3>
            <DiscordUserDropdown onSelect={handleDiscordUserSelect} />
            <UserCard user={selectedDiscordUser} edit={true} saveFunc={"create"} key="modal_usercard" />
            <label className="modal-backdrop" htmlFor="my_modal_7">
              Close
            </label>
          </div>
          <button></button>
        </div>

        </>
    );
  };

  return (
    <>
      <div className="flex flex-col items-start p-4 h-full  ">
        <div
          className="grid grid-flow-row-dense grid-auto-rows
        align-middle content-center justify-center
       grid-cols-4
         w-full "
        >
          <div className="flex">{searchBar()}</div>
          <div className="flex col-start-4 align-end content-end justify-end">
            {addUserBtn()}
          </div>
        </div>
        <div
          className="grid grid-flow-row-dense grid-auto-rows
        align-middle content-center justify-center
         grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4
         mb-0 mt-0 p-0 bg-base-900  w-full"
        >
          {filteredUsers?.map((u) => (
            <div className="grid" key={u.pk}>
              <UserCard user={u} saveFunc={'save'}/>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
