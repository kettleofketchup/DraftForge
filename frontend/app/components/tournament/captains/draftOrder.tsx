import { Fragment, useState } from 'react';
import { toast } from 'sonner';
import { updateTeam } from '~/components/api/api';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectSeparator,
  SelectValue,
} from '~/components/ui/brand-select';
import { Label } from '~/components/ui/label';
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
        {/* shadcn <Label htmlFor> wires up screen-reader association +
            click-to-focus on the select trigger. Micro-styling overrides
            keep the 9px uppercase visual treatment that matches the
            captain action column's Pick/Remove subtitle. */}
        <Label
          htmlFor={id}
          className="text-[9px] uppercase tracking-wider text-muted-foreground leading-none justify-center font-normal"
        >
          Order
        </Label>
        <BrandSelect onValueChange={handleChange} value={draft_order}>
          <BrandSelectTrigger
            id={id}
            size="sm"
            className="w-9 px-1 py-0 text-xs justify-center [&>svg]:size-3"
            aria-label={`Draft order for ${user.username ?? ''}`.trim()}
            data-testid={`draft-order-trigger-${user.pk}`}
          >
            <SelectValue placeholder={draft_order} />
          </BrandSelectTrigger>
          <BrandSelectContent>
            {Array.from({ length: getRange() }, (_, i) => (
              <Fragment key={i + 1}>
                {i > 0 && <SelectSeparator className="!my-0 bg-violet-400/30" />}
                <BrandSelectItem value={String(i + 1)}>{i + 1}</BrandSelectItem>
              </Fragment>
            ))}
          </BrandSelectContent>
        </BrandSelect>
      </div>
    );
  }

  return (
    // Total stack height ≈ label (10) + gap (2) + sm trigger (24) = 36px,
    // so the label + select column matches the sibling Remove Captain
    // pill's `h-9` (36px) so both cells sit on the same baseline in the
    // captain Table row.
    <div className="inline-flex flex-col items-start gap-0.5">
      <Label
        htmlFor={id}
        className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground leading-none"
      >
        Draft Order
      </Label>

      <div className="flex items-center gap-2">
        <BrandSelect onValueChange={handleChange} value={draft_order}>
          <BrandSelectTrigger
            size="sm"
            className="w-[80px] h-6 py-0 text-xs"
            id={id}
          >
            <SelectValue placeholder={draft_order} />
          </BrandSelectTrigger>

          <BrandSelectContent>
            {Array.from({ length: getRange() }, (_, i) => (
              <Fragment key={i + 1}>
                {i > 0 && <SelectSeparator className="!my-0 bg-violet-400/30" />}
                <BrandSelectItem value={String(i + 1)}>{i + 1}</BrandSelectItem>
              </Fragment>
            ))}
          </BrandSelectContent>
        </BrandSelect>
        {isLoading && <span className="loading loading-spinner loading-xs" />}
      </div>
    </div>
  );
};
