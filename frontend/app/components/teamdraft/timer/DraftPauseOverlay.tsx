import { Play } from 'lucide-react';
import { useEffect, useState } from 'react';
import { PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import { DisplayName } from '~/components/user/avatar';
import type { UserType } from '~/index';
import type { TeamDraftState } from '../schemas';

export interface DraftPauseOverlayProps {
  draftStatus: TeamDraftState | null;
  isManualPause: boolean;
  resumingRemainingMs: number;
  activeCaptain: UserType | null;
  isActiveCaptainDisconnected: boolean;
  canResume: boolean;
  isStaff: boolean;
  onResume: () => Promise<unknown>;
  onPickForCaptain: () => void;
}

export function DraftPauseOverlay({
  draftStatus,
  isManualPause,
  resumingRemainingMs,
  activeCaptain,
  isActiveCaptainDisconnected,
  canResume,
  isStaff,
  onResume,
  onPickForCaptain,
}: DraftPauseOverlayProps) {
  const [minimized, setMinimized] = useState(false);

  useEffect(() => {
    if (draftStatus !== 'paused') setMinimized(false);
  }, [draftStatus]);

  if (draftStatus === 'resuming') {
    return (
      <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/70" data-testid="draft-paused-overlay">
        <h2 className="text-3xl font-bold text-green-400" data-testid="draft-resuming-countdown">
          Resuming in {Math.ceil(resumingRemainingMs / 1000)}…
        </h2>
      </div>
    );
  }
  if (draftStatus !== 'paused') return null;

  const captainName = activeCaptain ? DisplayName(activeCaptain) : 'captain';
  const message = isManualPause
    ? 'Paused by captain or staff'
    : isActiveCaptainDisconnected
      ? `${captainName} is disconnected — pick for them or wait`
      : 'Click Resume to continue';

  const resumeButton = canResume && (
    <PrimaryButton
      color="green"
      onClick={() => void onResume()}
      disabled={isActiveCaptainDisconnected}
      data-testid="draft-resume-button"
    >
      <Play className="h-4 w-4 mr-2" />
      Resume Draft
    </PrimaryButton>
  );

  if (minimized) {
    return (
      <div
        className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-yellow-500/20 px-4 py-2"
        data-testid="draft-paused-banner"
      >
        <span className="text-sm" data-testid="draft-paused-message">
          {message}
        </span>
        <div className="flex items-center gap-2">
          {resumeButton}
          <SecondaryButton data-testid="draft-paused-expand" onClick={() => setMinimized(false)}>
            Expand
          </SecondaryButton>
        </div>
      </div>
    );
  }

  return (
    <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/70" data-testid="draft-paused-overlay">
      <div className="space-y-4 text-center">
        <h2 className="text-3xl font-bold text-yellow-400" data-testid="draft-paused-title">
          Draft Paused
        </h2>
        <p className="text-muted-foreground" data-testid="draft-paused-message">
          {message}
        </p>
        <div className="flex flex-col items-center gap-2">
          {resumeButton}
          {isStaff && isActiveCaptainDisconnected && (
            <SecondaryButton
              data-testid="draft-pick-for-captain-button"
              onClick={() => {
                setMinimized(true);
                onPickForCaptain();
              }}
            >
              Pick for {captainName}
            </SecondaryButton>
          )}
        </div>
      </div>
    </div>
  );
}
