import React, { useState } from 'react';
import { toast } from 'sonner';
import {
  createTeam,
  deleteTeam,
  fetchTeamUsage,
  fetchTournament,
  updateTeam,
} from '~/components/api/api';

import { AdminOnlyButton } from '~/components/reusable/adminButton';
import type { TeamType, TournamentType } from '~/components/tournament/types';
import { SubmitButton } from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs';
import type { UserType } from '~/components/user/types';
import { deleteTeamsInOrder, deleteTeamsMessage } from '~/lib/deleteTeams';
import { hydrateTournament } from '~/lib/hydrateTournament';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('createTeamsButton');

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
  const [showConfirm, setShowConfirm] = useState(false);

  const refreshTournament = async () => {
    if (!tournament.pk) return;
    const rawData = await fetchTournament(tournament.pk);
    tournament = hydrateTournament(
      rawData as TournamentType & { _users?: Record<number, unknown> },
    ) as TournamentType;
    setTournament(tournament);
  };

  const deleteTeams = async (): Promise<boolean> => {
    const existing = (tournament.teams ?? []).filter(
      (team): team is TeamType & { pk: number } => !!team.pk,
    );
    const result = await deleteTeamsInOrder(existing, {
      checkUsage: fetchTeamUsage,
      remove: deleteTeam,
    });
    if (result.ok) return true;
    log.error('Team regeneration stopped before creating teams', result);
    toast.error(deleteTeamsMessage(result));
    await refreshTournament();
    return false;
  };

  const handleSubmit = async () => {
    if (!(await deleteTeams())) return;
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
          success: (data) =>
            data
              ? `${submitTeam.name} has been updated`
              : `${submitTeam.name} had no members left and was deleted`,
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
    await refreshTournament();
    setDialogOpen(false);
  };

  if (!isStaff()) return <AdminOnlyButton />;

  return (
    <>
      <SubmitButton
        data-testid="submitTeamsBtn"
        aria-label="Submit and create teams"
        onClick={() => setShowConfirm(true)}
      >
        Submit this
      </SubmitButton>
      <ConfirmDialog
        open={showConfirm}
        onOpenChange={setShowConfirm}
        title="Regenerate Teams? Are You Sure?"
        description="This action cannot be undone. This will permanently delete the previous teams and regenerate the new ones"
        confirmLabel="Continue"
        variant="destructive"
        onConfirm={handleSubmit}
        confirmTestId="confirmTeamsCreationBtn"
        cancelTestId="cancelTeamsCreationBtn"
      />
    </>
  );
};
