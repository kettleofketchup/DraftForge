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
  /** `compact` drops the "Draft Order" label and shrinks the select so the
   * control fits a UserStrip actionSlot column on mobile. */
  compact?: boolean;
}> = ({ user, draft_order, id, setDraftOrder, compact = false }) => {
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
  if (compact) {
    return (
      <div className="flex flex-col items-stretch gap-0.5 w-9" data-testid={`draft-order-${user.pk}`}>
        <span
          className="text-[9px] uppercase tracking-wider text-muted-foreground leading-none text-center"
          aria-hidden
        >
          Order
        </span>
        <Select onValueChange={handleChange} value={draft_order}>
          <SelectTrigger
            id={id}
            className="h-7 w-9 px-1 py-0 text-xs [&>svg]:size-3"
            aria-label={`Draft order for ${user.username ?? ''}`.trim()}
            data-testid={`draft-order-trigger-${user.pk}`}
          >
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
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-2 md:flex-row">
      <Label htmlFor={id}>Draft Order</Label>

      <Select onValueChange={handleChange} value={draft_order}>
        <SelectTrigger className="w-[80px]" id={id}>
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
