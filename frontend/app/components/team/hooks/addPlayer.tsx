import { toast } from 'sonner';
import { updateTeam } from '~/components/api/api';
import type { TeamType, UserType } from '~/index';
import { getLogger } from '~/lib/logger';
const log = getLogger('AddPlayerHook');

type hookParams = {
  team: TeamType;
  player: UserType;
};

export const addPlayerHook = async ({ team, player }: hookParams) => {
  if (!team || !team.pk) {
    log.error('No Team Found');
    return;
  }
  if (!player || !player.pk) {
    log.error('No player Found');
    return;
  }

  const getMembers = () => team.members?.map((user: UserType) => user.pk);

  if (getMembers()?.includes(player.pk)) {
    log.error('Player is already in the team');
    toast.error('Player is already in the team');
    return;
  }

  let payload: Partial<TeamType> = {
    members_ids: [...(team.members_ids || []), player.pk],
  };

  toast.promise(updateTeam(team.pk, payload), {
    loading: `Adding ${player.username} to ${team.name}`,
    success: (data) => {
      return `${team.name} has been updated successfully!`;
    },
    error: (err) => {
      const val = err.response.data;
      log.error('Failed to update team', err);
      return `Failed to update team: ${val}`;
    },
  });
};
