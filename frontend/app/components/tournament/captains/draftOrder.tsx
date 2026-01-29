import { useCallback, useMemo } from 'react';
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
import { useTournamentDataStore } from '~/store/tournamentDataStore';
const log = getLogger('DraftOrderButton');

export const DraftOrderButton: React.FC<{
  user: UserType;
  draft_order: string;
  id: string;
  setDraftOrder: React.Dispatch<React.SetStateAction<string>>;
}> = ({ user, draft_order, id, setDraftOrder }) => {
  const teams = useTournamentDataStore((state) => state.teams);
  const users = useTournamentDataStore((state) => state.users);
  const metadata = useTournamentDataStore((state) => state.metadata);
  const loadTeams = useTournamentDataStore((state) => state.loadTeams);

  const team = useMemo(() => {
    return teams.find((t) => t.captain?.pk === user.pk);
  }, [teams, user.pk]);

  const updateDraftOrder = useCallback(async (newOrder: string) => {
    log.debug('updateDraftOrder', { newOrder, team });
    if (!team) return;

    const newTeam = {
      draft_order: parseInt(newOrder),
    };
    log.debug('updateDraftOrder', {
      user: user.username,
      draft_order: newOrder,
      team: team.name,
    });
    toast.promise(updateTeam(team.pk!, newTeam), {
      loading: `Updating Draft order for ${user.username}`,

      success: (data) => {
        loadTeams();
        if (data.draft_order !== undefined) {
          log.debug('draft_order state updated', data.draft_order);
          setDraftOrder(String(data.draft_order));
        }
        log.debug(data);
        return `${metadata?.name} has updated the draft_order to ${data.draft_order}`;
      },
      error: (err) => {
        const val = err.response.data;
        log.error('Failed to update captains tournament', err);
        return `Failed to update captains: ${val}`;
      },
    });
  }, [team, user.username, loadTeams, metadata?.name, setDraftOrder]);

  const handleChange = useCallback(async (value: string) => {
    log.debug('handleChange', { value });
    setDraftOrder(value);
    await updateDraftOrder(value);
  }, [setDraftOrder, updateDraftOrder]);
  const range = useMemo(() => {
    return Math.ceil(users.length / 5);
  }, [users.length]);
  return (
    <div className="flex flex-col items-center gap-2 md:flex-row">
      <Label htmlFor={id}>Draft Order</Label>

      <Select onValueChange={handleChange} value={draft_order}>
        <SelectTrigger className="w-[80px]">
          <SelectValue placeholder={draft_order} />
        </SelectTrigger>

        <SelectContent>
          {Array.from({ length: range }, (_, i) => (
            <SelectItem key={i + 1} value={String(i + 1)}>
              {i + 1}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
};
