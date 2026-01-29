import React, { type FormEvent } from 'react';
import { toast } from 'sonner';
import {
  createTeam,
  deleteTeam,
  updateTeam,
} from '~/components/api/api';

import { AdminOnlyButton } from '~/components/reusable/adminButton';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/components/user/types';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '~/components/ui/alert-dialog';
import { SubmitButton } from '~/components/ui/buttons';
import { useUserStore } from '~/store/userStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';

interface CreateTeamsButtonProps {
  tournamentId: number | null;
  existingTeams: TeamType[];
  newTeams: TeamType[];
  dialogOpen: boolean;
  setDialogOpen: (open: boolean) => void;
}

export const CreateTeamsButton: React.FC<CreateTeamsButtonProps> = ({
  tournamentId,
  existingTeams,
  newTeams,
  dialogOpen,
  setDialogOpen,
}) => {
  const isStaff = useUserStore((state) => state.isStaff);
  const loadAll = useTournamentDataStore((state) => state.loadAll);

  const deleteExistingTeams = async () => {
    if (existingTeams.length === 0) {
      return;
    }
    for (const team of existingTeams) {
      if (!team.pk) continue;

      await toast.promise(deleteTeam(team.pk), {
        loading: `Deleting Team ${team.name}.`,
        success: () => {
          return `${team.name}(${team.pk}) has been deleted`;
        },
        error: (err) => `Failed to delete team: ${err.message}`,
      });
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    await deleteExistingTeams();
    const sortedTeams = [...newTeams].sort((a, b) => {
      if (a.name === b.name) return 0;
      if (!a.name || !b.name) return 0; // Handle undefined names
      return a.name.localeCompare(b.name);
    });
    for (const team of sortedTeams) {
      const submitTeam: TeamType = {
        member_ids: team.members?.map((user: UserType) => user.pk),
        captain_id: team.captain?.pk,
        pk: team.pk ? team.pk : undefined,
        name: team.name,
        tournament_id: tournamentId ?? undefined,
      };
      if (submitTeam.pk) {
        await toast.promise(updateTeam(submitTeam.pk, submitTeam), {
          loading: `Updating Team ${team.name}.`,
          success: () => {
            return `${submitTeam.name} has been updated`;
          },
          error: (err) => `Failed to update team: ${err.message}`,
        });
      } else {
        await toast.promise(createTeam(submitTeam), {
          loading: `Creating Team ${submitTeam.name}.`,
          success: () => {
            return `${submitTeam.name} has been created`;
          },
          error: (err) => `Failed to create team: ${err.message}`,
        });
      }
    }
    // Refresh tournament data from server
    loadAll();
    setDialogOpen(false);
  };

  if (!isStaff()) return <AdminOnlyButton />;

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <SubmitButton
          data-testid="submitTeamsBtn"
          aria-label="Submit and create teams"
        >
          Submit this
        </SubmitButton>
      </AlertDialogTrigger>
      <AlertDialogContent className="bg-red-900">
        <AlertDialogHeader>
          <AlertDialogTitle>Regenerate Teams? Are You Sure?</AlertDialogTitle>
          <AlertDialogDescription className="text-base-700">
            This action cannot be undone. This will permanently delete the
            previous teams and regenerate the new ones
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel data-testid="cancelTeamsCreationBtn">
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={handleSubmit}
            data-testid="confirmTeamsCreationBtn"
          >
            Continue
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};
