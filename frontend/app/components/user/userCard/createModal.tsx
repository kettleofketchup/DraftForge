import React, { useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { PlusCircleIcon } from 'lucide-react';

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { PrimaryButton } from '~/components/ui/buttons';
import { FormDialog } from '~/components/ui/dialogs';
import { Form } from '~/components/ui/form';
import DiscordUserDropdown from '~/components/user/DiscordUserDropdown';
import { User } from '~/components/user/user';
import type {
  GuildMember,
  UserClassType,
  UserType,
} from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useResolvedUsers } from '~/hooks/useResolvedUsers';
import { getLogger } from '~/lib/logger';

import {
  buildDefaults,
  EditUserSchema,
  type EditUserInput,
} from './editUserSchema';
import { UserEditForm } from './editForm';

const log = getLogger('createModal');

interface Props {
  query?: string;
  setQuery?: React.Dispatch<React.SetStateAction<string>>;
}

export const UserCreateModal: React.FC<Props> = ({ query, setQuery }) => {
  const currentUser = useUserStore((state) => state.currentUser);
  // Use addUser (not setUser) so the new user appears in globalUserPks-driven
  // grids like /users. setUser only upserts the cache and won't add a new pk.
  const addUser = useUserStore((state) => state.addUser);
  const globalUserPks = useUserStore((state) => state.globalUserPks);
  const users = useResolvedUsers(globalUserPks);

  const [open, setOpen] = useState(false);
  const [discordUser, setDiscordUser] = useState<User>(
    new User({} as UserClassType),
  );

  // Build initial empty defaults; reset when a Discord user is selected.
  const form = useForm<EditUserInput>({
    // Cast: matches the pattern used in editModal — z.coerce produces
    // input=unknown / output=EditUserInput, but our defaults are clean.
    resolver: zodResolver(EditUserSchema) as unknown as import('react-hook-form').Resolver<EditUserInput>,
    defaultValues: buildDefaults({} as UserClassType, { kind: 'global' }),
  });

  const handleDiscordUserSelect = (member: GuildMember) => {
    const fresh = new User({} as UserClassType);
    fresh.setFromGuildMember(member);
    setDiscordUser(new User(fresh as UserClassType));
    form.reset(buildDefaults(fresh as UserClassType, { kind: 'global' }));
  };

  async function onSubmit(data: EditUserInput) {
    // Discord identity (username, discordId, avatar) lives on the User class
    // built from the dropdown selection — merge it with form-edited fields
    // before calling dbCreate (which POSTs `this as UserType`).
    const merged = { ...(discordUser as UserType), ...data } as UserType;
    const newUser = new User(merged as UserClassType);
    try {
      const created = await toast
        .promise(newUser.dbCreate(), {
          loading: `Creating ${merged.username || 'user'}…`,
          success: `${merged.username || 'User'} created`,
          error: (err) =>
            err instanceof Error
              ? `Failed to create user: ${err.message}`
              : 'Failed to create user',
        })
        .unwrap();
      addUser(created);
      useUserCacheStore.getState().upsert([created]);
      setDiscordUser(new User({} as UserClassType));
      form.reset(buildDefaults({} as UserClassType, { kind: 'global' }));
      setOpen(false);
    } catch (err) {
      log.error('Failed to create user', err);
      // toast.promise already surfaced the error; nothing else to do here.
    }
  }

  if (!currentUser || (!currentUser.is_staff && !currentUser.is_superuser)) {
    return null;
  }

  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <PrimaryButton size="lg" onClick={() => setOpen(true)}>
              <PlusCircleIcon className="text-white" />
              Create User
            </PrimaryButton>
          </TooltipTrigger>
          <TooltipContent>
            <p>Create a new user from discord</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title="Create User"
        description="Please fill in the details below to create a new user."
        submitLabel="Create User"
        isSubmitting={form.formState.isSubmitting}
        onSubmit={form.handleSubmit(onSubmit)}
        size="lg"
        data-testid="create-user-modal"
      >
        <div className="flex flex-col w-full gap-4">
          <DiscordUserDropdown
            query={query}
            setQuery={setQuery}
            discrimUsers={users}
            onSelect={handleDiscordUserSelect}
          />
          <Form {...form}>
            <UserEditForm form={form} showMmr={false} mmrLabel="MMR" />
          </Form>
        </div>
      </FormDialog>
    </>
  );
};

export default UserCreateModal;
