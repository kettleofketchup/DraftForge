import { useState } from 'react';
import { toast } from 'sonner';
import { updateTeam } from '~/components/api/api';
import { Label } from '~/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import type { UserType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
const log = getLogger('updateCaptainButton');

export const DraftOrderButton: React.FC<{
  user: UserType;
  draft_order: string;
  id: string;
  setDraftOrder: React.Dispatch<React.SetStateAction<string>>;
}> = ({ user, draft_order, id, setDraftOrder }) => {
  const tournament = useUserStore((state) => state.tournament);
  const getCurrentTournament = useUserStore(
    (state) => state.getCurrentTournament,
  );
  const [isLoading, setIsLoading] = useState(false);
  const getTeam = () => {
    return tournament?.teams?.find((t) => t.captain?.pk === user.pk);
  };
  const handleChange = async (value: string) => {
    log.debug('handleChange', { value });
    setDraftOrder(value);
    draft_order = value;
    await updateDraftOrder();
  };
  const updateDraftOrder = async () => {
    log.debug('updateDraftOrder', {
      draft_order,
    });

    const team = getTeam();
    log.debug('updateDraftOrder', {
      team,
    });
    if (!team) return;
    const newTeam = {
      draft_order: parseInt(draft_order),
    };
    log.debug('updateDraftOrder', {
      user: user.username,
      draft_order,
      team: team.name,
    });
    toast.promise(updateTeam(team.pk!, newTeam), {
      loading: ` Updating Draft order for ${user.username}`,

      success: (data) => {
        getCurrentTournament();
        if (data.draft_order !== undefined) {
          log.debug('draft_order state updated', data.draft_order);
          setDraftOrder(String(data.draft_order));
        }
        log.debug(data);
        return `${tournament?.name} has updated the draft_order to ${data.draft_order}`;
      },
      error: (err) => {
        const val = err.response.data;
        log.error('Failed to update captains tournament', err);
        return `Failed to update captains: ${val}`;
      },
    });
  };
  const getRange = () => {
    if (!tournament?.users) return 0;
    return Math.ceil(tournament.users.length / 5);
  };
  return (
    <div className="flex flex-col items-center gap-2 md:flex-row">
      <Label htmlFor={id}>Draft Order</Label>

      <Select onValueChange={handleChange} value={draft_order}>
        <SelectTrigger className="w-[80px]">
          <SelectValue placeholder={draft_order} />
        </SelectTrigger>

        <SelectContent>
          {Array.from({ length: getRange() }, (_, i) => (
            <SelectItem key={i + 1} value={String(i + 1)}>
              {i + 1}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {isLoading && <span className="loading loading-spinner loading-xs" />}
    </div>
  );
};
