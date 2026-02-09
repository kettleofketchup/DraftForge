import { ChevronDown, RotateCcw, Save } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';
import {
  CancelButton,
  ConfirmButton,
  DestructiveButton,
  PrimaryButton,
  SubmitButton,
} from '~/components/ui/buttons';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '~/components/ui/alert-dialog';
import {
  MobileActionsDropdown,
  type MobileAction,
} from '~/components/ui/mobile-actions-dropdown';
import { useBracketStore } from '~/store/bracketStore';
import { useSaveBracket } from '~/hooks/useBracket';
import type { TeamType } from '~/components/tournament/types';
import type { SeedingMethod } from '../types';

interface BracketToolbarProps {
  tournamentId: number;
  teams: TeamType[];
  hasMatches: boolean;
}

export function BracketToolbar({
  tournamentId,
  teams,
  hasMatches,
}: BracketToolbarProps) {
  const { generateBracket, reseedBracket, resetBracket, isDirty, isVirtual } =
    useBracketStore();
  const saveMutation = useSaveBracket(tournamentId);

  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [showGenerateConfirm, setShowGenerateConfirm] = useState(false);
  const [pendingSeedMethod, setPendingSeedMethod] = useState<SeedingMethod | null>(
    null
  );

  const handleGenerate = (method: SeedingMethod) => {
    if (hasMatches) {
      setPendingSeedMethod(method);
      setShowGenerateConfirm(true);
    } else {
      generateBracket(teams, method);
    }
  };

  const confirmGenerate = () => {
    if (pendingSeedMethod) {
      generateBracket(teams, pendingSeedMethod);
    }
    setShowGenerateConfirm(false);
    setPendingSeedMethod(null);
  };

  const handleSave = useCallback(() => {
    saveMutation.mutate(useBracketStore.getState().matches);
  }, [saveMutation]);

  const handleReset = () => {
    resetBracket();
    setShowResetConfirm(false);
  };

  const minTeamsForBracket = 2;
  const canGenerate = teams.length >= minTeamsForBracket;

  const mobileActions = useMemo<MobileAction[]>(() => {
    if (!hasMatches) return [];
    return [
      {
        key: 'save',
        icon: <Save className="h-4 w-4" />,
        label: 'Save',
        onClick: handleSave,
        variant: 'primary' as const,
        disabled: !isDirty || saveMutation.isPending,
        'data-testid': 'saveBracketButton-mobile',
      },
      {
        key: 'reset',
        icon: <RotateCcw className="h-4 w-4" />,
        label: 'Reset',
        onClick: () => setShowResetConfirm(true),
        variant: 'destructive' as const,
        'data-testid': 'resetBracketButton-mobile',
      },
    ];
  }, [hasMatches, isDirty, saveMutation.isPending, handleSave]);

  return (
    <div className="flex flex-wrap items-center gap-2 mb-4 p-2 bg-muted/50 rounded-lg relative z-10">
      {/* Generate / Reseed dropdown */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <PrimaryButton
            disabled={!canGenerate}
            data-testid={hasMatches ? 'reseedBracketButton' : 'generateBracketButton'}
          >
            {hasMatches ? (
              <>
                <span className="sm:hidden">Reseed</span>
                <span className="hidden sm:inline">Reseed Bracket</span>
              </>
            ) : (
              <>
                <span className="sm:hidden">Generate</span>
                <span className="hidden sm:inline">Generate Bracket</span>
              </>
            )}
            <ChevronDown className="h-4 w-4 ml-1" />
          </PrimaryButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem
            onClick={() => handleGenerate('mmr_total')}
            data-testid="seedByTeamMmrOption"
          >
            Seed by Team MMR (Recommended)
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => handleGenerate('captain_mmr')}
            data-testid="seedByCaptainMmrOption"
          >
            Seed by Captain MMR
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => handleGenerate('random')}
            data-testid="randomSeedingOption"
          >
            Random Seeding
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Mobile: actions dropdown for Save + Reset */}
      {hasMatches && (
        <MobileActionsDropdown
          actions={mobileActions}
          className="sm:hidden"
          data-testid="bracketActionsDropdown"
        />
      )}

      {/* Desktop: Save button */}
      {hasMatches && (
        <SubmitButton
          onClick={handleSave}
          disabled={!isDirty}
          loading={saveMutation.isPending}
          loadingText="Saving..."
          className="hidden sm:inline-flex"
          data-testid="saveBracketButton"
        >
          <Save className="h-4 w-4" />
          Save
        </SubmitButton>
      )}

      {/* Desktop: Reset button */}
      {hasMatches && (
        <DestructiveButton
          onClick={() => setShowResetConfirm(true)}
          className="hidden sm:inline-flex"
        >
          <RotateCcw className="h-4 w-4" />
          Reset
        </DestructiveButton>
      )}

      {/* Team count indicator */}
      <span className="ml-auto text-sm text-muted-foreground">
        {teams.length} teams
      </span>

      {/* Generate confirmation dialog */}
      <AlertDialog open={showGenerateConfirm} onOpenChange={setShowGenerateConfirm}>
        <AlertDialogContent className="bg-orange-950/95 border-orange-800">
          <AlertDialogHeader>
            <AlertDialogTitle>Regenerate Bracket?</AlertDialogTitle>
            <AlertDialogDescription className="text-orange-200">
              This will replace the current bracket structure. Any unsaved changes
              will be lost.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2">
            <CancelButton onClick={() => setShowGenerateConfirm(false)}>
              Cancel
            </CancelButton>
            <ConfirmButton
              variant="warning"
              onClick={confirmGenerate}
              data-testid="regenerateBracketConfirmButton"
            >
              Regenerate
            </ConfirmButton>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Reset confirmation dialog */}
      <AlertDialog open={showResetConfirm} onOpenChange={setShowResetConfirm}>
        <AlertDialogContent className="bg-red-950/95 border-red-800">
          <AlertDialogHeader>
            <AlertDialogTitle>Reset Bracket?</AlertDialogTitle>
            <AlertDialogDescription className="text-slate-300">
              This will clear all matches. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2">
            <CancelButton onClick={() => setShowResetConfirm(false)}>
              Cancel
            </CancelButton>
            <ConfirmButton variant="destructive" onClick={handleReset}>
              Reset
            </ConfirmButton>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
