import { RotateCcw, Save, Wand2 } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';
import { AutoAssignModal } from '~/components/bracket/modals';
import {
  DestructiveButton,
  SecondaryButton,
  SubmitButton,
} from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs';
import {
  BrandDropdownMenu,
  type BrandDropdownAction,
} from '~/components/ui/brand-dropdown-menu';
import { useBracketStore } from '~/store/bracketStore';
import { useSaveBracket } from '~/hooks/useBracket';
import { useQueryClient } from '@tanstack/react-query';
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
  const queryClient = useQueryClient();

  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [showGenerateConfirm, setShowGenerateConfirm] = useState(false);
  const [showAutoAssign, setShowAutoAssign] = useState(false);
  const [pendingSeedMethod, setPendingSeedMethod] = useState<SeedingMethod | null>(
    null
  );

  const handleAutoAssignComplete = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
  }, [queryClient, tournamentId]);

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

  const mobileActions = useMemo<BrandDropdownAction[]>(() => {
    if (!hasMatches) return [];
    return [
      {
        key: 'save',
        icon: <Save className="h-4 w-4" />,
        label: 'Save',
        onClick: handleSave,
        variant: 'primary',
        disabled: !isDirty || saveMutation.isPending,
        'data-testid': 'saveBracketButton-mobile',
      },
      {
        key: 'auto-assign',
        icon: <Wand2 className="h-4 w-4" />,
        label: 'Auto-Assign Matches',
        onClick: () => setShowAutoAssign(true),
        variant: 'edit',
        'data-testid': 'auto-assign-btn-mobile',
      },
      {
        key: 'reset',
        icon: <RotateCcw className="h-4 w-4" />,
        label: 'Reset',
        onClick: () => setShowResetConfirm(true),
        variant: 'destructive',
        'data-testid': 'resetBracketButton-mobile',
      },
    ];
  }, [hasMatches, isDirty, saveMutation.isPending, handleSave]);

  return (
    <div className="flex flex-wrap items-center gap-2 mb-4 p-2 bg-muted/50 rounded-lg relative z-10">
      {/* Generate / Reseed branded dropdown — hidden when <2 teams */}
      {canGenerate && (
        <BrandDropdownMenu
          label={hasMatches ? 'Reseed Bracket' : 'Generate Bracket'}
          variant="primary"
          data-testid={hasMatches ? 'reseedBracketButton' : 'generateBracketButton'}
          actions={[
            {
              key: 'seed-mmr-total',
              icon: <Wand2 className="h-4 w-4" />,
              label: 'Seed by Team MMR (Recommended)',
              onClick: () => handleGenerate('mmr_total'),
              variant: 'primary',
              'data-testid': 'seedByTeamMmrOption',
            },
            {
              key: 'seed-captain-mmr',
              icon: <Wand2 className="h-4 w-4" />,
              label: 'Seed by Captain MMR',
              onClick: () => handleGenerate('captain_mmr'),
              variant: 'default',
              'data-testid': 'seedByCaptainMmrOption',
            },
            {
              key: 'seed-random',
              icon: <Wand2 className="h-4 w-4" />,
              label: 'Random Seeding',
              onClick: () => handleGenerate('random'),
              variant: 'default',
              'data-testid': 'randomSeedingOption',
            },
          ]}
        />
      )}

      {/* Mobile: branded actions dropdown — Save, Auto-Assign, Reset */}
      {hasMatches && (
        <BrandDropdownMenu
          label="Bracket Actions"
          actions={mobileActions}
          variant="admin"
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

      {/* Desktop: Auto-Assign Matches */}
      {hasMatches && (
        <SecondaryButton
          onClick={() => setShowAutoAssign(true)}
          className="hidden sm:inline-flex"
          data-testid="auto-assign-btn"
        >
          <Wand2 className="h-4 w-4 mr-1" />
          Auto-Assign Matches
        </SecondaryButton>
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

      {/* Auto-Assign modal — shared by mobile dropdown + desktop button */}
      <AutoAssignModal
        isOpen={showAutoAssign}
        onClose={() => setShowAutoAssign(false)}
        tournamentId={tournamentId}
        onAssignComplete={handleAutoAssignComplete}
      />

      {/* Team count indicator */}
      <span className="ml-auto text-sm text-muted-foreground">
        {teams.length} teams
      </span>

      {/* Generate confirmation dialog */}
      <ConfirmDialog
        open={showGenerateConfirm}
        onOpenChange={setShowGenerateConfirm}
        title="Regenerate Bracket?"
        description="This will replace the current bracket structure. Any unsaved changes will be lost."
        confirmLabel="Regenerate"
        variant="warning"
        onConfirm={confirmGenerate}
        confirmTestId="regenerateBracketConfirmButton"
      />

      {/* Reset confirmation dialog */}
      <ConfirmDialog
        open={showResetConfirm}
        onOpenChange={setShowResetConfirm}
        title="Reset Bracket?"
        description="This will clear all matches. This cannot be undone."
        confirmLabel="Reset"
        variant="destructive"
        onConfirm={handleReset}
      />
    </div>
  );
}
