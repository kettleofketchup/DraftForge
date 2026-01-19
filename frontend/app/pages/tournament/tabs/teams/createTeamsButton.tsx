import React, { type FormEvent } from 'react';
import { toast } from 'sonner';
import {
  createTeam,
  deleteTeam,
  fetchTournament,
  updateTeam,
} from '~/components/api/api';

import { AdminOnlyButton } from '~/components/reusable/adminButton';
import type { TeamType, TournamentType } from '~/components/tournament/types';
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
import { Button } from '~/components/ui/button';
import { useUserStore } from '~/store/userStore';
interface CreateTeamsButtonProps {
  tournament: TournamentType;
  teams: TeamType[];
  dialogOpen: boolean;
  setDialogOpen: (open: boolean) => void;
}

export const CreateTeamsButton: React.FC<CreateTeamsButtonProps> = ({
  tournament,
  teams,
  dialogOpen,
  setDialogOpen,
}) => {
  const setTournament = useUserStore((state) => state.setTournament);
  const isStaff = useUserStore((state) => state.isStaff);
  const deleteTeams = async () => {
    if (!tournament.teams || tournament.teams.length === 0) {
      return;
    }
    for (const team of tournament.teams) {
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

    await deleteTeams();
    teams = teams.sort((a, b) => {
      if (a.name === b.name) return 0;
      if (!a.name || !b.name) return 0; // Handle undefined names
      return a.name.localeCompare(b.name);
    });
    for (const team of teams) {
      const submitTeam: TeamType = {
        member_ids: team.members?.map((user: UserType) => user.pk),
        captain_id: team.captain?.pk,
        pk: team.pk ? team.pk : undefined,
        name: team.name,
        tournament_id: tournament?.pk,
      };
      if (submitTeam.pk) {
        await toast.promise(updateTeam(submitTeam.pk, submitTeam), {
          loading: `Updating Team ${team.name}.`,
          success: (data: TeamType) => {
            return `${submitTeam.name} has been updated`;
          },
          error: (err) => `Failed to update team: ${err.message}`,
        });
      } else {
        await toast.promise(createTeam(submitTeam), {
          loading: `Creating Team ${submitTeam.name}.`,
          success: (data: TeamType) => {
            return `${submitTeam.name} has been created`;
          },
          error: (err) => `Failed to create team: ${err.message}`,
        });
      }
    }
    if (tournament.pk) {
      tournament = await fetchTournament(tournament.pk);
      setTournament(tournament);
    }
    setDialogOpen(false);
  };

  if (!isStaff()) return <AdminOnlyButton />;

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          className="btn btn-success bg-green-900 text-white"
          data-testid="submitTeamsBtn"
          aria-label="Submit and create teams"
        >
          Submit this
        </Button>
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
