import { Settings } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { TEAMS_BUTTONS_WIDTH } from '~/components/constants';
import { DIALOG_CSS } from '~/components/reusable/modal';
import { Button } from '~/components/ui/button';
import { CancelButton, PrimaryButton } from '~/components/ui/buttons';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '~/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';

import { AdminOnlyButton } from '~/components/reusable/adminButton';
import { Label } from '~/components/ui/label';
import { getLogger } from '~/lib/logger';
import { updateDraftStyleHook } from '../hooks/updateDraftStyleHook';
import type { DraftType } from '../types';
const log = getLogger('DraftStyleModal');

interface DraftStyleModalProps {
  /** External open state control (optional) */
  externalOpen?: boolean;
  /** External open state change handler (optional) */
  onExternalOpenChange?: (open: boolean) => void;
  /** Whether to show the trigger button (default: true) */
  showTrigger?: boolean;
}

export const DraftStyleModal: React.FC<DraftStyleModalProps> = ({
  externalOpen,
  onExternalOpenChange,
  showTrigger = true,
}) => {
  const isStaff = useUserStore((state) => state.isStaff);
  const draft = useUserStore((state) => state.draft);

  const setDraft = useUserStore((state) => state.setDraft);
  const [internalOpen, setInternalOpen] = useState(false);

  // Use external open state if provided, otherwise use internal state
  const open = externalOpen !== undefined ? externalOpen : internalOpen;
  const setOpen = onExternalOpenChange || setInternalOpen;
  const [selectedStyle, setSelectedStyle] = useState<'snake' | 'normal' | 'shuffle'>(
    draft?.draft_style || 'snake',
  );

  const draftPredictedMMRs = useTournamentStore(
    (state) => state.draftPredictedMMRs,
  );
  const updateDraftPredictedMMRs = useTournamentStore(
    (state) => state.updateDraftPredictedMMRs,
  );

  useEffect(() => {
    if (open && draft && draft.pk !== null) {
      updateDraftPredictedMMRs(draft.pk);
    }
  }, [open, draft]);

  useEffect(() => {}, [draftPredictedMMRs]);

  const handleStyleChange = async (newStyle: 'snake' | 'normal' | 'shuffle') => {
    if (!draft) return;

    try {
      // TODO: Add API call to update draft style
      // const updatedDraft = await updateDraftStyle(draft.pk, newStyle);

      // For now, update locally
      log.debug('Handling style change', { draft, newStyle });
      const updatedDraft: DraftType = {
        ...draft,
        pk: draft.pk,
        draft_style: newStyle as 'snake' | 'normal' | 'shuffle',
      };

      await updateDraftStyleHook({
        draftStyle: newStyle,
        draft: draft,
        setDraft: setDraft,
      });
      setDraft(updatedDraft);
      setSelectedStyle(newStyle);
      setOpen(false);
    } catch (error) {
      console.error('Failed to update draft style:', error);
    }
  };

  const formatMMR = (mmr: number) => {
    return mmr.toLocaleString();
  };

  const calculateBalance = (firstPick: number, lastPick: number) => {
    const diff = Math.abs(firstPick - lastPick);
    const avg = (firstPick + lastPick) / 2;
    const balancePercentage = avg > 0 ? (diff / avg) * 100 : 0;
    return balancePercentage.toFixed(1);
  };

  const dialogButton = () => {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <DialogTrigger asChild>
              <PrimaryButton
                color="blue"
                className={`w-[${TEAMS_BUTTONS_WIDTH}]`}
              >
                <Settings className="mr-2 h-4 w-4" />
                Draft Style
              </PrimaryButton>
            </DialogTrigger>
          </TooltipTrigger>
          <TooltipContent>
            <p>Configure draft style and view MMR balance</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };

  if (!draft) {
    return null;
  }

  const snakeBalance = () =>
    calculateBalance(
      draftPredictedMMRs.snake_first_pick_mmr || 0,
      draftPredictedMMRs.snake_last_pick_mmr || 0,
    );

  const normalBalance = () =>
    calculateBalance(
      draftPredictedMMRs.normal_first_pick_mmr || 0,
      draftPredictedMMRs.normal_last_pick_mmr || 0,
    );
  const getButtons = () => {
    if (!isStaff()) return <AdminOnlyButton />;

    return (
      <Button
        onClick={() => handleStyleChange(selectedStyle)}
        disabled={selectedStyle === draft.draft_style}
      >
        Apply {selectedStyle === 'snake' ? 'Snake' : selectedStyle === 'normal' ? 'Normal' : 'Shuffle'} Draft
      </Button>
    );
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {showTrigger && dialogButton()}
      <DialogContent className={`${DIALOG_CSS} max-w-2xl`}>
        <DialogHeader>
          <DialogTitle>Draft Style Configuration</DialogTitle>
          <DialogDescription>
            Choose draft style and compare team balance using MMR projections
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Draft Style Selection */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">Draft Style</Label>
            <Select value={selectedStyle} onValueChange={(value) => setSelectedStyle(value as 'snake' | 'normal' | 'shuffle')}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select draft style" />
              </SelectTrigger>
              <SelectContent className="">
                <SelectItem value="snake">
                  <div className="flex flex-col sm:flex-row sm:justify-between gap-2 w-full align-center items-center justify-center">
                    <span className="font-medium">Snake Draft</span>
                    <span className="text-xs text-muted-foreground">
                      1st, 2nd, 3rd, 4th, 4th, 3rd, 2nd, 1st...
                    </span>
                  </div>
                </SelectItem>
                <SelectItem value="normal">
                  <div className="flex flex-col">
                    <span className="font-medium">Normal Draft</span>
                    <span className="text-xs text-muted-foreground">
                      1st, 2nd, 3rd, 4th, 1st, 2nd, 3rd, 4th...
                    </span>
                  </div>
                </SelectItem>
                <SelectItem value="shuffle">
                  <div className="flex flex-col">
                    <span className="font-medium">Shuffle Draft</span>
                    <span className="text-xs text-muted-foreground">
                      Lowest MMR team picks first, recalculated each round
                    </span>
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* MMR Comparison */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold">Team Balance Comparison</h3>

            {/* Snake Draft Stats */}
            <div className="rounded-lg border p-4 space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="font-medium text-green-600">Snake Draft</h4>
                <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">
                  {snakeBalance()}% imbalance
                </span>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">
                    First Pick Team:{' '}
                  </span>
                  <span className="font-medium">
                    {formatMMR(draftPredictedMMRs.snake_first_pick_mmr || 0)}{' '}
                    MMR
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">
                    Last Pick Team:{' '}
                  </span>
                  <span className="font-medium">
                    {formatMMR(draftPredictedMMRs.snake_last_pick_mmr || 0)} MMR
                  </span>
                </div>
              </div>
              <div className="text-xs text-muted-foreground">
                Difference:{' '}
                {formatMMR(
                  Math.abs(
                    (draftPredictedMMRs.snake_first_pick_mmr || 0) -
                      (draftPredictedMMRs.snake_last_pick_mmr || 0),
                  ),
                )}{' '}
                MMR
              </div>
            </div>

            {/* Normal Draft Stats */}
            <div className="rounded-lg border p-4 space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="font-medium text-orange-600">Normal Draft</h4>
                <span className="text-xs bg-orange-100 text-orange-800 px-2 py-1 rounded">
                  {normalBalance()}% imbalance
                </span>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">
                    First Pick Team:{' '}
                  </span>
                  <span className="font-medium">
                    {formatMMR(draftPredictedMMRs.normal_first_pick_mmr || 0)}{' '}
                    MMR
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">
                    Last Pick Team:{' '}
                  </span>
                  <span className="font-medium">
                    {formatMMR(draftPredictedMMRs.normal_last_pick_mmr || 0)}{' '}
                    MMR
                  </span>
                </div>
              </div>
              <div className="text-xs text-muted-foreground">
                Difference:{' '}
                {formatMMR(
                  Math.abs(
                    (draftPredictedMMRs.normal_first_pick_mmr || 0) -
                      (draftPredictedMMRs.normal_last_pick_mmr || 0),
                  ),
                )}{' '}
                MMR
              </div>
            </div>

            {/* Shuffle Draft Stats */}
            <div className="rounded-lg border p-4 space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="font-medium text-purple-600">Shuffle Draft</h4>
                <span className="text-xs bg-purple-100 text-purple-800 px-2 py-1 rounded">
                  Dynamic balance
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                Pick order adjusts after each selection to favor the lowest MMR team.
                Cannot predict final balance - depends on captain choices.
              </p>
            </div>

            {/* Recommendation */}
            <div className="bg-blue-50 dark:bg-blue-950/20 rounded-lg p-3">
              <p className="text-sm text-blue-800 dark:text-blue-200">
                <strong>Recommendation:</strong>{' '}
                {snakeBalance() < normalBalance() ? (
                  <>
                    Snake draft provides better balance ({snakeBalance()}% vs{' '}
                    {normalBalance()} % imbalance)
                  </>
                ) : (
                  <>
                    Normal draft provides better balance ({normalBalance()}% vs{' '}
                    {snakeBalance()}% imbalance)
                  </>
                )}
              </p>
            </div>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <DialogClose asChild>
            <CancelButton />
          </DialogClose>
          {getButtons()}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
