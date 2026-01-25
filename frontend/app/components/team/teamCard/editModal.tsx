import React, { useState } from 'react';
import type { UserType, UserClassType } from '~/components/user/types';
import { FormDialog } from '~/components/ui/dialogs';
import { EditIconButton } from '~/components/ui/buttons';
import { useUserStore } from '~/store/userStore';
import type { TeamType } from '~/components/tournament/types';
import { TeamEditForm } from './editTeam';

interface Props {
  team: TeamType;
}

export const TeamEditModal: React.FC<Props> = ({ team }) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<UserType>({} as UserType);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    // Form submission is handled by TeamEditForm internally
    // This is a placeholder for proper form integration
  };

  if (!currentUser || (!currentUser.is_staff && !currentUser.is_superuser)) {
    return <></>;
  }

  return (
    <>
      <EditIconButton tooltip="Edit Team" onClick={() => setOpen(true)} />
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title="Edit Team"
        description="Please fill in the details below to edit the team."
        submitLabel="Save"
        isSubmitting={isSubmitting}
        onSubmit={handleSubmit}
        size="md"
        showFooter={false}
      >
        <TeamEditForm user={team.captain as UserClassType} form={form} setForm={setForm} />
      </FormDialog>
    </>
  );
};

export default TeamEditModal;
