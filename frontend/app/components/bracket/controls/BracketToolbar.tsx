import { ChevronDown } from 'lucide-react';
import { useState } from 'react';
import {
  CancelButton,
  ConfirmButton,
  DestructiveButton,
  SecondaryButton,
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
import { useBracketStore } from '~/store/bracketStore';
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
  const { generateBracket, reseedBracket, saveBracket, resetBracket, isLoading, isDirty, isVirtual } =
    useBracketStore();

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

  const handleSave = () => {
    saveBracket(tournamentId);
  };

  const handleReset = () => {
    resetBracket();
    setShowResetConfirm(false);
  };

  const minTeamsForBracket = 2;
  const canGenerate = teams.length >= minTeamsForBracket;

  return (
    <div className="flex items-center gap-2 mb-4 p-2 bg-muted/50 rounded-lg relative z-10">
      {/* Generate / Reseed dropdown */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <SecondaryButton disabled={!canGenerate} color="cyan">
            {hasMatches ? 'Reseed Bracket' : 'Generate Bracket'}
            <ChevronDown className="h-4 w-4 ml-1" />
          </SecondaryButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onClick={() => handleGenerate('mmr_total')}>
            Seed by Team MMR (Recommended)
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => handleGenerate('captain_mmr')}>
            Seed by Captain MMR
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => handleGenerate('random')}>
            Random Seeding
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Save button */}
      {hasMatches && (
        <SubmitButton
          onClick={handleSave}
          disabled={!isDirty}
          loading={isLoading}
          loadingText="Saving..."
        >
          {isVirtual ? 'Save Bracket' : 'Save Changes'}
        </SubmitButton>
      )}

      {/* Reset button */}
      {hasMatches && (
        <DestructiveButton onClick={() => setShowResetConfirm(true)}>
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
            <ConfirmButton variant="warning" onClick={confirmGenerate}>
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
