import { ExternalLink, MoreHorizontal } from 'lucide-react';
import { ROSTER_BADGE_SIZE } from '~/components/team/manage/RosterStatusBadge';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { DotabuffButton, SecondaryButton } from '~/components/ui/buttons';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import { useSetSteamVerification } from '~/features/steam-verification';
import { cn } from '~/lib/utils';

const STEAM_ID_64_BASE = BigInt('76561197960265728');

const UNVERIFIED_TONE = 'bg-warning/20 text-warning border-warning/30';
const VERIFIED_TONE = 'text-success border-success/30';

export function steamProfileUrl(steamAccountId: number): string {
  const id64 = BigInt(steamAccountId) + STEAM_ID_64_BASE;
  return `https://steamcommunity.com/profiles/${id64.toString()}`;
}

function formatVerifiedDate(verifiedAt: string | null | undefined): string {
  if (!verifiedAt) return 'an unknown date';
  const date = new Date(verifiedAt);
  if (Number.isNaN(date.getTime())) return 'an unknown date';
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function steamVerificationTitle(
  verified: boolean,
  existsChecked: boolean,
  verifiedOrgName: string | null | undefined,
  verifiedAt: string | null | undefined,
): string {
  if (verified) {
    return `Verified by ${verifiedOrgName ?? 'site staff'} on ${formatVerifiedDate(verifiedAt)}`;
  }
  return existsChecked
    ? 'Self-reported. Found on Steam.'
    : 'Self-reported. Not checked against Steam.';
}

export interface SteamVerificationBadgeProps {
  userPk: number;
  steamAccountId: number | null | undefined;
  verified: boolean;
  verifiedOrgName?: string | null;
  verifiedAt?: string | null;
  existsChecked: boolean;
  canVerify: boolean;
  /** Admin placement: show the Verified state even without verify rights. */
  staffView?: boolean;
  /** Turns the badge into a button (list placement opens the player modal). */
  onClick?: () => void;
  /** Off where the host already renders its own Dotabuff link. */
  showDotabuff?: boolean;
}

interface ActionsProps {
  userPk: number;
  steamAccountId: number;
  verified: boolean;
  showDotabuff: boolean;
}

function SteamVerificationActions({
  userPk,
  steamAccountId,
  verified,
  showDotabuff,
}: ActionsProps) {
  const mutation = useSetSteamVerification(userPk);

  if (verified) {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="size-6"
            aria-label="Friend ID verification actions"
            data-testid="steam-verification-menu"
          >
            <MoreHorizontal />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            className="text-warning focus:bg-warning/20"
            disabled={mutation.isPending}
            onSelect={() =>
              mutation.mutate({ verified: false, steamAccountId })
            }
            data-testid="steam-unverify-item"
          >
            Mark unverified
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  return (
    <>
      <SecondaryButton
        asChild
        size="sm"
        className="h-6 px-2 text-xs"
        data-testid="steam-profile-link"
      >
        <a
          href={steamProfileUrl(steamAccountId)}
          target="_blank"
          rel="noopener noreferrer"
          title="View Steam profile"
        >
          <ExternalLink className="size-3" />
          <span>Steam</span>
        </a>
      </SecondaryButton>
      {showDotabuff && (
        <DotabuffButton
          steamAccountId={steamAccountId}
          responsive={false}
          size="sm"
          className="h-6 px-2 text-xs"
        />
      )}
      <SecondaryButton
        size="sm"
        className="h-6 px-2 text-xs"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate({ verified: true, steamAccountId })}
        data-testid="steam-verify-button"
      >
        Verify
      </SecondaryButton>
    </>
  );
}

export function SteamVerificationBadge({
  userPk,
  steamAccountId,
  verified,
  verifiedOrgName,
  verifiedAt,
  existsChecked,
  canVerify,
  staffView = false,
  onClick,
  showDotabuff = true,
}: SteamVerificationBadgeProps) {
  if (!steamAccountId) return null;
  if (verified && !canVerify && !staffView) return null;

  const title = steamVerificationTitle(
    verified,
    existsChecked,
    verifiedOrgName,
    verifiedAt,
  );
  const testId = verified
    ? 'steam-verification-verified'
    : 'steam-verification-unverified';
  const className = cn(
    ROSTER_BADGE_SIZE,
    verified ? VERIFIED_TONE : UNVERIFIED_TONE,
    onClick && 'cursor-pointer hover:opacity-80',
  );
  const label = verified ? 'Verified' : 'Unverified';

  const badge = onClick ? (
    <Badge variant="outline" className={className} asChild>
      <button
        type="button"
        title={title}
        aria-label={`Friend ID ${label.toLowerCase()}: ${title}`}
        onClick={(e) => {
          e.stopPropagation();
          onClick();
        }}
        data-testid={testId}
      >
        {label}
      </button>
    </Badge>
  ) : (
    <Badge
      variant="outline"
      className={className}
      title={title}
      data-testid={testId}
    >
      {label}
    </Badge>
  );

  if (!canVerify) return badge;

  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {badge}
      <SteamVerificationActions
        userPk={userPk}
        steamAccountId={steamAccountId}
        verified={verified}
        showDotabuff={showDotabuff}
      />
    </span>
  );
}
