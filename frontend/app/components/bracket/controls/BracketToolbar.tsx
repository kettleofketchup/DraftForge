import { useState } from 'react';
import { Button } from '~/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
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
  isDirty: boolean;
  isVirtual: boolean;
}

export function BracketToolbar({
  tournamentId,
  teams,
  hasMatches,
  isDirty,
  isVirtual,
}: BracketToolbarProps) {
  const { generateBracket, reseedBracket, saveBracket, resetBracket, isLoading } =
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
    <div className="flex items-center gap-2 mb-4 p-2 bg-muted/50 rounded-lg">
      {/* Generate / Reseed dropdown */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" disabled={!canGenerate}>
            {hasMatches ? 'Reseed Bracket' : 'Generate Bracket'}
          </Button>
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
        <Button
          onClick={handleSave}
          disabled={!isDirty || isLoading}
          variant={isDirty ? 'default' : 'outline'}
        >
          {isLoading ? 'Saving...' : isVirtual ? 'Save Bracket' : 'Save Changes'}
        </Button>
      )}

      {/* Reset button */}
      {hasMatches && (
        <Button variant="destructive" onClick={() => setShowResetConfirm(true)}>
          Reset
        </Button>
      )}

      {/* Team count indicator */}
      <span className="ml-auto text-sm text-muted-foreground">
        {teams.length} teams
      </span>

      {/* Generate confirmation dialog */}
      <AlertDialog open={showGenerateConfirm} onOpenChange={setShowGenerateConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Regenerate Bracket?</AlertDialogTitle>
            <AlertDialogDescription>
              This will replace the current bracket structure. Any unsaved changes
              will be lost.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmGenerate}>
              Regenerate
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Reset confirmation dialog */}
      <AlertDialog open={showResetConfirm} onOpenChange={setShowResetConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reset Bracket?</AlertDialogTitle>
            <AlertDialogDescription>
              This will clear all matches. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleReset} className="bg-destructive">
              Reset
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
