import { History } from 'lucide-react';

import type {
  EventSignupType,
  HistorySubject,
} from '~/components/events/schemas';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '~/components/ui/sheet';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { DisplayName } from '~/components/user/avatar';
import type { UserType } from '~/components/user/types';

import { SignupHistorySection } from './SignupHistorySection';

/** The history subject for a signup row, preferring the cached user over the signup payload. */
export function historySubjectFor(
  signup: EventSignupType,
  user?: UserType,
): HistorySubject {
  const data = signup.user_data;
  return {
    user_id: signup.user,
    username: user?.username ?? data?.username ?? signup.username ?? null,
    nickname: user?.nickname ?? data?.nickname ?? null,
    discordNickname: user?.discordNickname ?? data?.discordNickname ?? null,
    guildNickname: user?.guildNickname ?? null,
    avatarUrl: user?.avatarUrl ?? data?.avatarUrl ?? null,
    discord_id: user?.discordId ?? data?.discordId ?? null,
  };
}

export function SignupHistoryButton({
  user,
  onClick,
}: {
  user: HistorySubject;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <SecondaryButton
          size="sm"
          className="min-h-11 sm:min-h-8"
          aria-label={`View history for ${DisplayName(user)}`}
          data-testid={`signup-history-btn-user-${user.user_id}`}
          onClick={onClick}
        >
          <History className="size-4" aria-hidden />
        </SecondaryButton>
      </TooltipTrigger>
      <TooltipContent>View history</TooltipContent>
    </Tooltip>
  );
}

export function SignupHistorySheet({
  eventId,
  eventTimezone,
  isAdmin,
  user,
  onOpenChange,
}: {
  eventId: number;
  eventTimezone?: string;
  isAdmin: boolean;
  user: HistorySubject | null;
  onOpenChange: (open: boolean) => void;
}) {
  if (!isAdmin) return null;
  return (
    <Sheet open={!!user} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col sm:max-w-lg"
        data-testid="signup-history-sheet"
      >
        <SheetHeader>
          <SheetTitle>Sign-up history</SheetTitle>
          <SheetDescription className="wrap-anywhere">
            {user ? DisplayName(user) : null}
          </SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {user && (
            <SignupHistorySection
              eventId={eventId}
              isAdmin={isAdmin}
              eventTimezone={eventTimezone}
              compact
              fixedUser={user}
            />
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
