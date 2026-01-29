import { memo } from 'react';
import type { UserType } from '~/index';
import { cn } from '~/lib/utils';
import { Badge } from '../../ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '../../ui/tooltip';
import {
  CarrySVG,
  HardSupportSVG,
  MidSVG,
  OfflaneSVG,
  SoftSupportSVG,
} from './icons';

interface BadgeProps {
  user: UserType;
  /**
   * Compact mode: icon + rank only, no text label.
   * - `true`: Always compact
   * - `false`: Always full (with text)
   * - `undefined`: Responsive - compact on mobile (<sm), full on larger screens
   */
  compact?: boolean;
  /**
   * Disable tooltips for performance in list views with many items.
   * Uses native title attribute instead.
   */
  disableTooltips?: boolean;
}

import { getLogger } from '~/lib/logger';

const numberClasses =
  'absolute -top-1 -left-1 h-4 w-4 rounded-full p-0 border-white border-1 text-white';

const compactNumberClasses =
  'absolute -top-1 -left-1 h-3.5 w-3.5 text-[10px] rounded-full p-0 border-white border-1 text-white flex items-center justify-center';

const getRankLabel = (rank: number): string => {
  switch (rank) {
    case 1:
      return '1st choice';
    case 2:
      return '2nd choice';
    case 3:
      return '3rd choice';
    case 4:
      return '4th choice';
    case 5:
      return '5th choice';
    default:
      return `${rank}th choice`;
  }
};

const log = getLogger('userPositionsBadge');
export const useBadgeGuard = (user: UserType): boolean => {
  if (!user) {
    log.debug('No user provided to badge component');
    return false;
  }
  if (!user.positions) {
    log.debug('User has no positions defined');
    return false;
  }
  if (Object.keys(user.positions).length === 0) {
    log.debug('User positions object is empty');
    return false;
  }
  return true;
};

export const CarryBadge: React.FC<BadgeProps> = memo(({ user, compact, disableTooltips }) => {
  const shouldShowBadge = useBadgeGuard(user);

  if (!shouldShowBadge) return null;
  if (!user.positions?.carry) return null;

  // Responsive: compact on mobile, full on sm+ (unless explicitly set)
  const isResponsive = compact === undefined;
  const forceCompact = compact === true;

  const badgeContent = (
    <div
      className="relative inline-block cursor-help"
      title={disableTooltips ? `Position 1: Carry - ${getRankLabel(user.positions.carry)}` : undefined}
    >
      <Badge className={cn(
        "badge-primary !bg-rose-900 !text-white hover:!bg-rose-800 transition-colors",
        forceCompact && "!px-1 !py-0.5",
        isResponsive && "!px-1 !py-0.5 sm:!px-2.5 sm:!py-0.5"
      )}>
        <Badge className={cn(
          "!bg-rose-800",
          forceCompact ? compactNumberClasses : isResponsive ? cn(compactNumberClasses, "sm:h-4 sm:w-4 sm:text-xs") : numberClasses
        )}>
          {user.positions.carry}
        </Badge>
        <CarrySVG className={cn(
          forceCompact && "w-4 h-4",
          isResponsive && "w-4 h-4 sm:w-5 sm:h-5"
        )} />
        {!forceCompact && (
          <span className={isResponsive ? "hidden sm:inline" : undefined}>Carry</span>
        )}
      </Badge>
    </div>
  );

  if (disableTooltips) return badgeContent;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {badgeContent}
      </TooltipTrigger>
      <TooltipContent className="bg-rose-900 text-white">
        <p className="font-semibold">Position 1: Carry</p>
        <p className="text-rose-200">{getRankLabel(user.positions.carry)}</p>
      </TooltipContent>
    </Tooltip>
  );
});

export const MidBadge: React.FC<BadgeProps> = memo(({ user, compact, disableTooltips }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.mid) return null;

  const isResponsive = compact === undefined;
  const forceCompact = compact === true;

  const badgeContent = (
    <div
      className="relative inline-block cursor-help"
      title={disableTooltips ? `Position 2: Mid - ${getRankLabel(user.positions.mid)}` : undefined}
    >
      <Badge className={cn(
        "badge-primary !bg-cyan-900 !text-white hover:!bg-cyan-800 transition-colors",
        forceCompact && "!px-1 !py-0.5",
        isResponsive && "!px-1 !py-0.5 sm:!px-2.5 sm:!py-0.5"
      )}>
        <Badge className={cn(
          "!bg-cyan-800",
          forceCompact ? compactNumberClasses : isResponsive ? cn(compactNumberClasses, "sm:h-4 sm:w-4 sm:text-xs") : numberClasses
        )}>
          {user.positions.mid}
        </Badge>
        <MidSVG className={cn(
          forceCompact && "w-4 h-4",
          isResponsive && "w-4 h-4 sm:w-5 sm:h-5"
        )} />
        {!forceCompact && (
          <span className={isResponsive ? "hidden sm:inline" : undefined}>Mid</span>
        )}
      </Badge>
    </div>
  );

  if (disableTooltips) return badgeContent;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {badgeContent}
      </TooltipTrigger>
      <TooltipContent className="bg-cyan-900 text-white">
        <p className="font-semibold">Position 2: Mid</p>
        <p className="text-cyan-200">{getRankLabel(user.positions.mid)}</p>
      </TooltipContent>
    </Tooltip>
  );
});

export const OfflaneBadge: React.FC<BadgeProps> = memo(({ user, compact, disableTooltips }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.offlane) return null;

  const isResponsive = compact === undefined;
  const forceCompact = compact === true;

  const badgeContent = (
    <div
      className="relative inline-block cursor-help"
      title={disableTooltips ? `Position 3: Offlane - ${getRankLabel(user.positions.offlane)}` : undefined}
    >
      <Badge className={cn(
        "badge-primary !bg-emerald-900 !text-white hover:!bg-emerald-800 transition-colors",
        forceCompact && "!px-1 !py-0.5",
        isResponsive && "!px-1 !py-0.5 sm:!px-2.5 sm:!py-0.5"
      )}>
        <Badge className={cn(
          "!bg-emerald-800",
          forceCompact ? compactNumberClasses : isResponsive ? cn(compactNumberClasses, "sm:h-4 sm:w-4 sm:text-xs") : numberClasses
        )}>
          {user.positions.offlane}
        </Badge>
        <OfflaneSVG className={cn(
          forceCompact && "w-4 h-4",
          isResponsive && "w-4 h-4 sm:w-5 sm:h-5"
        )} />
        {!forceCompact && (
          <span className={isResponsive ? "hidden sm:inline" : undefined}>Offlane</span>
        )}
      </Badge>
    </div>
  );

  if (disableTooltips) return badgeContent;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {badgeContent}
      </TooltipTrigger>
      <TooltipContent className="bg-emerald-900 text-white">
        <p className="font-semibold">Position 3: Offlane</p>
        <p className="text-emerald-200">{getRankLabel(user.positions.offlane)}</p>
      </TooltipContent>
    </Tooltip>
  );
});

export const SoftSupportBadge: React.FC<BadgeProps> = memo(({ user, compact, disableTooltips }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.soft_support) return null;

  const isResponsive = compact === undefined;
  const forceCompact = compact === true;

  const badgeContent = (
    <div
      className="relative inline-block cursor-help"
      title={disableTooltips ? `Position 4: Soft Support - ${getRankLabel(user.positions.soft_support)}` : undefined}
    >
      <Badge className={cn(
        "badge-primary !bg-violet-900 !text-white hover:!bg-violet-800 transition-colors",
        forceCompact && "!px-1 !py-0.5",
        isResponsive && "!px-1 !py-0.5 sm:!px-2.5 sm:!py-0.5"
      )}>
        <Badge className={cn(
          "!bg-violet-800",
          forceCompact ? compactNumberClasses : isResponsive ? cn(compactNumberClasses, "sm:h-4 sm:w-4 sm:text-xs") : numberClasses
        )}>
          {user.positions.soft_support}
        </Badge>
        <SoftSupportSVG className={cn(
          forceCompact && "w-4 h-4",
          isResponsive && "w-4 h-4 sm:w-5 sm:h-5"
        )} />
        {!forceCompact && (
          <span className={isResponsive ? "hidden sm:inline" : undefined}>
            <span className="hidden 2xl:inline">SoftSupport</span>
            <span className="inline 2xl:hidden">Pos4</span>
          </span>
        )}
      </Badge>
    </div>
  );

  if (disableTooltips) return badgeContent;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {badgeContent}
      </TooltipTrigger>
      <TooltipContent className="bg-violet-900 text-white">
        <p className="font-semibold">Position 4: Soft Support</p>
        <p className="text-violet-200">{getRankLabel(user.positions.soft_support)}</p>
      </TooltipContent>
    </Tooltip>
  );
});

export const HardSupportBadge: React.FC<BadgeProps> = memo(({ user, compact, disableTooltips }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.hard_support) return null;

  const isResponsive = compact === undefined;
  const forceCompact = compact === true;

  const badgeContent = (
    <div
      className="relative inline-block cursor-help"
      title={disableTooltips ? `Position 5: Hard Support - ${getRankLabel(user.positions.hard_support)}` : undefined}
    >
      <Badge className={cn(
        "badge-primary !bg-indigo-900 !text-white hover:!bg-indigo-800 transition-colors",
        forceCompact && "!px-1 !py-0.5",
        isResponsive && "!px-1 !py-0.5 sm:!px-2.5 sm:!py-0.5"
      )}>
        <Badge className={cn(
          "!bg-indigo-800",
          forceCompact ? compactNumberClasses : isResponsive ? cn(compactNumberClasses, "sm:h-4 sm:w-4 sm:text-xs") : numberClasses
        )}>
          {user.positions.hard_support}
        </Badge>
        <HardSupportSVG className={cn(
          forceCompact && "w-4 h-4",
          isResponsive && "w-4 h-4 sm:w-5 sm:h-5"
        )} />
        {!forceCompact && (
          <span className={isResponsive ? "hidden sm:inline" : undefined}>
            <span className="hidden 2xl:inline">HardSupport</span>
            <span className="inline 2xl:hidden">Pos5</span>
          </span>
        )}
      </Badge>
    </div>
  );

  if (disableTooltips) return badgeContent;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {badgeContent}
      </TooltipTrigger>
      <TooltipContent className="bg-indigo-900 text-white">
        <p className="font-semibold">Position 5: Hard Support</p>
        <p className="text-indigo-200">{getRankLabel(user.positions.hard_support)}</p>
      </TooltipContent>
    </Tooltip>
  );
});
interface RolePositionsProps {
  user: UserType;
  /**
   * Compact mode: icon + rank only, no text labels.
   * - `true`: Always compact
   * - `false`: Always full (with text)
   * - `undefined`: Responsive - compact on mobile (<sm), full on larger screens
   */
  compact?: boolean;
  /**
   * Disable tooltips for performance in list views with many items.
   * Uses native title attribute instead.
   */
  disableTooltips?: boolean;
}

export const RolePositions: React.FC<RolePositionsProps> = ({ user, compact, disableTooltips }) => {
  if (!user.positions) return null;

  const isResponsive = compact === undefined;
  const forceCompact = compact === true;

  return (
    <div className={cn(
      "flex flex-wrap justify-center",
      forceCompact ? "flex-row gap-2" : isResponsive ? "flex-row gap-1 sm:gap-1" : "flex-col md:flex-row gap-1"
    )}>
      {[
        { component: CarryBadge, value: user?.positions?.carry },
        { component: MidBadge, value: user?.positions?.mid },
        { component: OfflaneBadge, value: user?.positions?.offlane },
        { component: SoftSupportBadge, value: user?.positions?.soft_support },
        { component: HardSupportBadge, value: user?.positions?.hard_support },
      ]
        .filter(({ value }) => value != null)
        .sort((a, b) => a.value - b.value)
        .map(({ component: Component }, index) => (
          <Component key={index} user={user} compact={compact} disableTooltips={disableTooltips} />
        ))}
    </div>
  );
};
