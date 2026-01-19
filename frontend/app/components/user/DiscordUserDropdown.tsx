import {
  Combobox,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
} from '@headlessui/react';
import React, { useCallback, useEffect, useState } from 'react';
import { Label } from '~/components/ui/label';
import { AvatarUrl } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '../../store/userStore';
import { get_dtx_members } from '../api/api';
import type { GuildMember, GuildMembers, UsersType } from '../user/types';

const log = getLogger('DiscordUserDropdown');
interface Props {
  query?: string;
  setQuery?: React.Dispatch<React.SetStateAction<string>>;
  onSelect: (user: GuildMember) => void;
  discrimUsers?: UsersType;
}

const DiscordUserDropdown: React.FC<Props> = ({
  query,
  setQuery,
  onSelect,
  discrimUsers,
}) => {
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const setDiscordUsers = useUserStore((state) => state.setDiscordUsers); // Zustand setter
  const discordUsers = useUserStore((state) => state.discordUsers); // Zustand setter
  const discordUser = useUserStore((state) => state.selectedDiscordUser); // Zustand setter

  const getDiscordUsers = useCallback(async () => {
    try {
      log.debug('User fetching');
      get_dtx_members()
        .then((response) => {
          setDiscordUsers(response);
        })
        .catch((error) => {
          log.error('Error fetching user:', error);

          setDiscordUsers([] as GuildMembers);
        });
    } catch (err) {
      setDiscordUsers([] as GuildMembers);
    } finally {
    }
  }, []);

  useEffect(() => {
    if (discordUsers.length > 0) {
      return;
    }
    getDiscordUsers();
  }, []);

  useEffect(() => {}, [discordUsers.length]);
  const filteredUsers =
    query === ''
      ? discordUsers
      : discordUsers.filter((person: GuildMember) => {
          if (!query) return false;

          const username = person.user.username
            .toLowerCase()
            .includes(query?.toLowerCase());

          const nickname = (person as any).user?.nick
            ?.toLowerCase()
            .includes(query?.toLowerCase());

          const global_name = person?.user?.global_name
            ?.toLowerCase()
            .includes(query?.toLowerCase());
          return username || nickname || global_name;
        });

  // Remove users that have a discordId in discrimUsers
  const filteredWithoutDiscrim: GuildMember[] = discrimUsers
    ? filteredUsers.filter(
        (user: GuildMember) =>
          !discrimUsers.some((du) => du?.discordId === user.user.id),
      )
    : filteredUsers;

  const isUserAlreadyAdded = useCallback(
    (user: GuildMember) => {
      return discrimUsers
        ? discrimUsers.some((du) => du?.discordId === user.user.id)
        : false;
    },
    [discrimUsers],
  );

  const filteredUserComboOption = (user: GuildMember) => {
    const getNickname = () => {
      if (!user || !user.nick) {
        return <></>;
      }
      return (
        <div className="flex justify-left ">
          <Label
            htmlFor={`global-nick-${user.user.id}`}
            className="justify-left text-xs text-gray-500 m-0 pl-1 w-10"
          >
            Nick:
          </Label>
          <p id={`global-nick-${user.user.id}`}>{user.nick} </p>
        </div>
      );
    };

    const getUsername = () => {
      if (!user || !user.user.username) {
        return <></>;
      }
      return (
        <div className=" justify-left flex">
          <Label
            htmlFor={`global-username-${user.user.id}`}
            className=" justify-left text-xs text-gray-500 m-0 pl-1 w-20"
          >
            Username:
          </Label>
          <p id={`global-username-${user.user.id}`}>{user.user.username} </p>
        </div>
      );
    };

    const getGlobalName = () => {
      if (!user || !user.user.global_name) {
        return <></>;
      }

      return (
        <div className="flex  justify-left ">
          <Label
            htmlFor={`global-name-${user.user.id}`}
            className="justify-left text-xs text-gray-500 m-0 pl-1 w-20"
          >
            Global:
          </Label>
          <p id={`global-name-${user.user.id}`}>{user.user.global_name} </p>
        </div>
      );
    };
    const userAddedBadge = () => {
      if (!isUserAlreadyAdded(user)) return <></>;
      return (
        <span className="rounded-full text-center bg-gray-900 text-sm text-red-200 p-1 ml-2">
          Already Added
        </span>
      );
    };
    return (
      <ComboboxOption
        key={user.user.id}
        data-testid={`combobox-option-${user.user.username}`}
        value={user}
        disabled={isUserAlreadyAdded(user)}
        className={({ focus, disabled }) =>
          `cursor-pointer select-none p-2
       ${focus ? 'bg-purple-900 text-primary-content' : ''}
        ${disabled ? 'opacity-50  bg-grey-100 hover:bg-gray-500' : ''}`
        }
      >
        <div className="flex items-center w-full">
          <img
            src={AvatarUrl(user)}
            alt={user.user.global_name ?? undefined}
            className="w-8 h-8 rounded-full"
          />
          <div className="flex w-full flex-col ">
            <div className="flex">
              {getGlobalName()}
              {userAddedBadge()}
            </div>

            <div className={`rounded-lg flex justify-left `}>
              {getNickname()}
            </div>
            <div className={`rounded-lg flex justify-left `}>
              {getUsername()}
            </div>
          </div>

          {/* TODO add a quickadd button*/}
          {/* {!isUserAlreadyAdded(user) && (
            <Button
              size="sm"
              className="justify-end btn bg-green-500 text-white hover:bg-green-600 disabled:bg-gray-300 disabled:text-gray-500"
            >
              <PlusCircleIcon color="green" />
              <p className="text-sm"> Quick Add</p>
            </Button>
          )} */}
        </div>
      </ComboboxOption>
    );
  };
  return (
    <div className="w-full max-w-md">
      <Combobox value={discordUser} onChange={onSelect}>
        <ComboboxInput
          className="input input-bordered w-full"
          placeholder="Search DTX members..."
          onChange={(event) => setQuery?.(event.target.value)}
          autoComplete="off"
        />
        <ComboboxOptions className="border bg-base-100 shadow-lg rounded-lg max-h-60 overflow-y-auto mt-2">
          {filteredUsers &&
          filteredUsers.length > 0 &&
          filteredUsers.length < 100 ? (
            filteredUsers.map((user) => {
              return filteredUserComboOption(user);
            })
          ) : (
            <div className="p-2 text-sm text-gray-500">
              {`${filteredUsers.length}`} users found. Results will show when
              less than 100 users are found.
            </div>
          )}
        </ComboboxOptions>
      </Combobox>
    </div>
  );
};

export default DiscordUserDropdown;
