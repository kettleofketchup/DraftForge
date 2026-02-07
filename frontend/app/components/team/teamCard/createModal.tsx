import { getLogger } from '~/lib/logger';

import { PlusCircleIcon } from 'lucide-react';
import React, { useState } from 'react';
import { PrimaryButton } from '~/components/ui/buttons';
import { FormDialog } from '~/components/ui/dialogs';
import DiscordUserDropdown from '~/components/user/DiscordUserDropdown';
import { User } from '~/components/user/user';
import { UserEditForm } from '~/components/user/userCard/editForm';
import { useUserStore } from '~/store/userStore';

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';

import type {
  GuildMember,
  UserClassType,
  UserType,
} from '~/components/user/types';

const log = getLogger('createModal');

interface Props {}

export const TeamCreateModal: React.FC<Props> = (props) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser);
  const users: UserType[] = useUserStore((state) => state.users);

  const [open, setOpen] = useState(false);
  const [selectedDiscordUser, setSelectedDiscordUser] = useState<User>(
    new User({} as UserClassType),
  );
  const [form, setForm] = useState<UserType>({} as UserType);
  const [query, setQuery] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleDiscordUserSelect = (user: GuildMember) => {
    setForm({} as UserType);
    log.debug(selectedDiscordUser);
    selectedDiscordUser.setFromGuildMember(user);
    setSelectedDiscordUser(new User(selectedDiscordUser as UserType));
    setForm(selectedDiscordUser as UserType);
  };

  const handleSubmit = async () => {
    // Form submission is handled by UserEditForm internally
    // This is a placeholder for proper form integration
  };

  if (!currentUser || (!currentUser.is_staff && !currentUser.is_superuser)) {
    return <></>;
  }

  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <PrimaryButton
              size="lg"
              onClick={() => setOpen(true)}
            >
              <PlusCircleIcon size="lg" className="text-white p-2" />
              Create Team
            </PrimaryButton>
          </TooltipTrigger>
          <TooltipContent>
            <p>Create Team</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title="Create Team"
        description="Please fill in the details below to create a new team."
        submitLabel="Create"
        isSubmitting={isSubmitting}
        onSubmit={handleSubmit}
        size="md"
        showFooter={false}
      >
        <DiscordUserDropdown
          query={query}
          setQuery={setQuery}
          discrimUsers={users}
          onSelect={handleDiscordUserSelect}
        />

        <UserEditForm
          user={selectedDiscordUser}
          form={form}
          setForm={setForm}
        />
      </FormDialog>
    </>
  );
};

export default TeamCreateModal;
