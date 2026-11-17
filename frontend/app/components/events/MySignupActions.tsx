import { CheckCircle2, HelpCircle, XCircle } from 'lucide-react';
import {
  DestructiveButton,
  PrimaryButton,
  SecondaryButton,
} from '~/components/ui/buttons';
import { EventStateBadge } from './EventStateBadge';
import type { EventSignupType } from './schemas';
import { SignupStatus } from './schemas';

export type SignupIntent = 'rsvp' | 'tentative';

export interface MySignupActionsProps {
  mySignup: EventSignupType | undefined;
  signupsOpen: boolean;
  signupDisabled: boolean;
  cancelPending: boolean;
  onSignup: (intent: SignupIntent) => void;
  onCancel: () => void;
}

export function MySignupActions({
  mySignup,
  signupsOpen,
  signupDisabled,
  cancelPending,
  onSignup,
  onCancel,
}: MySignupActionsProps) {
  if (mySignup?.status === SignupStatus.DROPPED) {
    return (
      <div
        className="flex items-center gap-2 text-sm text-muted-foreground"
        data-testid="event-dropped-notice"
      >
        <EventStateBadge state={SignupStatus.DROPPED} />
        <span>You were dropped from this event</span>
      </div>
    );
  }

  if (!signupsOpen) return null;

  if (!mySignup) {
    return (
      <>
        <PrimaryButton
          size="sm"
          onClick={() => onSignup('rsvp')}
          disabled={signupDisabled}
          data-testid="event-signup-btn"
        >
          <CheckCircle2 className="h-4 w-4 mr-1.5" />
          Sign Up
        </PrimaryButton>
        <SecondaryButton
          size="sm"
          onClick={() => onSignup('tentative')}
          disabled={signupDisabled}
          data-testid="event-tentative-btn"
        >
          <HelpCircle className="h-4 w-4 mr-1.5" />
          <span className="hidden sm:inline">Tentative</span>
        </SecondaryButton>
      </>
    );
  }

  if (mySignup.status === SignupStatus.TENTATIVE) {
    return (
      <>
        <PrimaryButton
          size="sm"
          onClick={() => onSignup('rsvp')}
          disabled={signupDisabled}
          data-testid="event-upgrade-rsvp-btn"
        >
          <CheckCircle2 className="h-4 w-4 mr-1.5" />
          Sign Up
        </PrimaryButton>
        <DestructiveButton
          size="sm"
          onClick={onCancel}
          loading={cancelPending}
          depth={false}
          data-testid="event-cancel-tentative-btn"
        >
          <XCircle className="h-4 w-4 mr-1.5" />
          Cancel
        </DestructiveButton>
      </>
    );
  }

  return (
    <DestructiveButton
      size="sm"
      onClick={onCancel}
      loading={cancelPending}
      depth={false}
      data-testid="event-cancel-rsvp-btn"
    >
      <XCircle className="h-4 w-4 mr-1.5" />
      Cancel RSVP
    </DestructiveButton>
  );
}
