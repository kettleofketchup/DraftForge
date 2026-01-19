import React, { useEffect, useState } from 'react';
import type { UserClassType, UserType } from '~/components/user/types';

import { User } from '~/components/user';

import { useUserStore } from '~/store/userStore';

import { ScrollArea } from '@radix-ui/react-scroll-area';
import { UserRoundPlusIcon } from 'lucide-react';
import { toast } from 'sonner';
import { SCROLLAREA_CSS_SMALL } from '~/components/reusable/modal';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { ScrollBar } from '~/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { getLogger } from '~/lib/logger';
const log = getLogger('editForm');

interface Props {
  user: UserClassType; // Accepts both UserClassType and UserType
  form: UserType;
  setForm: React.Dispatch<React.SetStateAction<UserType>>;
  setDiscordUser?: React.Dispatch<React.SetStateAction<User>>;
}
export const UserToast = (title: string) => {
  const toastTitle = () => {
    return (
      <div>
        <UserRoundPlusIcon className="mr-2 h-4 w-4 inline-block" />
        <span className="font-semibold">{title}</span>
      </div>
    );
  };
  toast(toastTitle(), {
    description: 'Sunday, December 03, 2023 at 9:00 AM',
  });
};
export const UserEditForm: React.FC<Props> = ({ user, form, setForm }) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser); // Zustand setter
  const [errorMessage, setErrorMessage] = useState<
    Partial<Record<keyof UserType, string>>
  >({});
  const isStaff = useUserStore((state) => state.isStaff);

  const [statusMsg, setStatusMsg] = useState<string | null>('null');

  const handleChange = (field: string, value: any) => {
    log.debug('User form field changed:', field, value);
    setForm((prev) => {
      const newForm = { ...prev };
      const fields = field.split('.');
      if (fields.length > 1) {
        // Handle nested properties
        let current: any = newForm;
        for (let i = 0; i < fields.length - 1; i++) {
          if (!current[fields[i]]) {
            current[fields[i]] = {};
          }
          current = current[fields[i]];
        }
        current[fields[fields.length - 1]] = value;
        return newForm;
      } else {
        return { ...prev, [field]: value };
      }
    });
  };

  useEffect(() => {
    setForm(user as UserClassType); // Initialize form with user data

    if (
      user.username !== form.username ||
      user.discordId !== form.discordId ||
      user.nickname !== form.nickname
    ) {
      log.debug('User data changed, resetting form');
      setForm(user as UserClassType); // Ensure form is set to the user data
    }
  }, [user, form.discordId, form.username]);

  useEffect(() => {}, [user]);
  if (!currentUser || (!currentUser.is_staff && !currentUser.is_superuser)) {
    return (
      <div className="text-error">
        You do not have permission to edit users.
      </div>
    );
  }

  const inputView = (key: string & keyof UserClassType, label: string, type: string = 'text') => {
    return (
      <div className="w-full">
        <Label className="font-semibold">{label}</Label>
        <Input
          type={type}
          placeholder={String(user[key] ?? '')}
          value={String(form[key as keyof UserType] ?? '')}
          onFocus={() => handleChange(key, user[key])}
          disabled={!isStaff}
          onChange={(e) =>
            handleChange(key, e.target.value)
          }
          className={`input input-bordered w-full mt-1 ${errorMessage[key as keyof UserType] ? 'input-error' : ''}`}
        />
        {errorMessage[key as keyof UserType] && (
          <p className="text-error text-sm mt-1">{errorMessage[key as keyof UserType]}</p>
        )}
      </div>
    );
  };
  const positionChoices = () => {
    return (
      <SelectContent>
        <SelectItem value="0">0: Don't show this role </SelectItem>
        <SelectItem value="1">1: Favorite</SelectItem>
        <SelectItem value="2">2: Can play</SelectItem>
        <SelectItem value="3">3: If the team needs</SelectItem>
        <SelectItem value="4">4: I would rather not but I guess</SelectItem>
        <SelectItem value="5">5: Least Favorite </SelectItem>
      </SelectContent>
    );
  };

  const positionSelection = () => {
    return (
      <div className="form-control mt-5 align-center text-center mb-5 shadow-md p-4 rounded-lg bg-gray-800 hover:shadow-lg hover:shadow-gray-500/50 p-4 rounded-lg">
        <label className="label font-bold">Positions</label>
        <div className="flex flex-col md:flex-row md:cols-2 xl:cols-3 flex-wrap w-full items-center align-middle w-full gap-6 justify-center mt-2 ">
          <div className="flex flex-col align-center items-center justify-center gap-2  ">
            <Label className="carry-select font-semibold">Carry</Label>
            <Select
              onValueChange={(value) =>
                handleChange('positions.carry', parseInt(value, 10))
              }
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={form.positions?.carry?.toString()}
                  id="carry-select"
                  className={`select select-bordered w-full mt-1 `}
                />
              </SelectTrigger>
              {positionChoices()}
            </Select>
          </div>
          <div className="flex flex-col align-center items-center justify-center gap-2  ">
            <Label className="offlane-select font-semibold">Mid</Label>
            <Select
              onValueChange={(value) =>
                handleChange('positions.mid', parseInt(value, 10))
              }
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={form.positions?.mid?.toString()}
                  id="mid-select"
                  className={`select select-bordered w-full mt-1`}
                />
              </SelectTrigger>
              {positionChoices()}
            </Select>
          </div>
          <div className="flex flex-col align-center items-center justify-center gap-2  ">
            <Label className="mid-select font-semibold">Offlane</Label>
            <Select
              onValueChange={(value) =>
                handleChange('positions.offlane', parseInt(value, 10))
              }
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={form.positions?.offlane?.toString()}
                  id="offlane-select"
                  className={`select select-bordered w-full mt-1 `}
                />
              </SelectTrigger>
              {positionChoices()}
            </Select>
          </div>
          <div className="flex flex-col align-center items-center justify-center gap-2  ">
            <Label className="mid-select font-semibold">Soft Support</Label>
            <Select
              onValueChange={(value) =>
                handleChange('positions.soft_support', parseInt(value, 10))
              }
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={form.positions?.soft_support?.toString()}
                  id="soft-support-select"
                  className={`select select-bordered w-full mt-1 `}
                />
              </SelectTrigger>
              {positionChoices()}
            </Select>
          </div>
          <div className="flex flex-col align-center items-center justify-center gap-2  ">
            <Label className="mid-select font-semibold">Hard Support</Label>
            <Select
              onValueChange={(value) =>
                handleChange('positions.hard_support', parseInt(value, 10))
              }
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={form.positions?.hard_support?.toString()}
                  id="hard-support-select"
                  className={`select select-bordered w-full mt-1 `}
                />
              </SelectTrigger>
              {positionChoices()}
            </Select>
          </div>
        </div>
      </div>
    );
  };
  const title = () => {
    var msg = 'Status: ';

    if (statusMsg && statusMsg !== null && statusMsg !== 'null')
      msg = statusMsg;
    else {
      msg += 'Editing ...';
    }
    log.debug('title', msg);

    return msg;
  };

  return (
    <>
      <ScrollArea className={`${SCROLLAREA_CSS_SMALL}`}>
        <div className="flex flex-col justify-center align-center items-center w-full gap-4">
          {inputView('nickname', 'Nickname: ')}
          {inputView('mmr', 'MMR: ', 'number')}
          {/* Position selection using checkboxes for PositionEnum */}
          {positionSelection()}
          {inputView('steamid', 'Steam ID: ', 'number')}
          {/* {inputView('discordId', 'Discord ID: ', 'number')} */}
          {inputView('guildNickname', 'Discord Guild Nickname: ')}
        </div>
        <ScrollBar orientation="vertical" />
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
    </>
  );
};
