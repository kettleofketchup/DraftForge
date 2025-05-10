import React, { useState, useEffect, useCallback } from "react";
import { Combobox, ComboboxInput, ComboboxOption, ComboboxOptions } from "@headlessui/react";
import { get_dtx_members } from "../api/api";
import type { GuildMembers, GuildMember } from "../user/types";
import { useUserStore } from '../../store/userStore';

interface Props {
  onSelect: (user: GuildMember) => void;
}



const DiscordUserDropdown: React.FC<Props> = ({ onSelect }) => {

  const [query, setQuery] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const setDiscordUsers = useUserStore((state) => state.setDiscordUsers); // Zustand setter
  const discordUsers = useUserStore((state) => state.discordUsers); // Zustand setter
  const discordUser = useUserStore((state) => state.discordUser); // Zustand setter

   const getDiscordUsers = useCallback(async () => {

    try {
        console.log("User fetching");
        get_dtx_members().then( (response) => {
            setDiscordUsers(response);
          })
          .catch((error) => {
              console.error('Error fetching user:', error);

              setDiscordUsers( [] as GuildMembers);
        });
      }
      catch (err) {
        setDiscordUsers( [] as GuildMembers);

        } finally {
    }

    }, []

)
  useEffect(() => {
    console.log("test");
    getDiscordUsers();
    console.log(discordUsers);

    }, []);

    const filteredUsers =
    query === ''
      ? discordUsers
      : discordUsers.filter((person) => {
          return person.user.username.toLowerCase().includes(query.toLowerCase());
        });


  return (
    <div className="w-full max-w-md" >
      <Combobox value={discordUser} onChange={onSelect}>
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
                key={user.user.id}
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
                      user.user.avatar
                        ? `https://cdn.discordapp.com/avatars/${user.user.id}/${user.user.avatar}`
                        : "https://via.placeholder.com/32"
                    }
                    alt={user.user.username}
                    className="w-8 h-8 rounded-full"
                  />
                  <span>{user.user.username}</span>
                </div>
              </ComboboxOption>
            ))
          ) : (
            <div className="p-2 text-sm text-gray-500">No users or too many users found</div>
          )}
        </ComboboxOptions>
      </Combobox>
    </div>
  );
};

export default DiscordUserDropdown;
