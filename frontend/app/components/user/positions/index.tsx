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
  /** Compact mode: icon + rank only, no text label */
  compact?: boolean;
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

export const CarryBadge: React.FC<BadgeProps> = memo(({ user, compact }) => {
  const shouldShowBadge = useBadgeGuard(user);

  if (!shouldShowBadge) return null;
  if (!user.positions?.carry) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="relative inline-block cursor-help">
          <Badge className={cn(
            "badge-primary !bg-rose-900 !text-white hover:!bg-rose-800 transition-colors",
            compact && "!px-1 !py-0.5"
          )}>
            <Badge className={cn(compact ? compactNumberClasses : numberClasses, "!bg-rose-800")}>
              {user.positions.carry}
            </Badge>
            <CarrySVG className={compact ? "w-4 h-4" : undefined} />
            {!compact && "Carry"}
          </Badge>
        </div>
      </TooltipTrigger>
      <TooltipContent className="bg-rose-900 text-white">
        <p className="font-semibold">Position 1: Carry</p>
        <p className="text-rose-200">{getRankLabel(user.positions.carry)}</p>
      </TooltipContent>
    </Tooltip>
  );
});

export const MidBadge: React.FC<BadgeProps> = memo(({ user, compact }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.mid) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="relative inline-block cursor-help">
          <Badge className={cn(
            "badge-primary !bg-cyan-900 !text-white hover:!bg-cyan-800 transition-colors",
            compact && "!px-1 !py-0.5"
          )}>
            <Badge className={cn(compact ? compactNumberClasses : numberClasses, "!bg-cyan-800")}>
              {user.positions.mid}
            </Badge>
            <MidSVG className={compact ? "w-4 h-4" : undefined} />
            {!compact && "Mid"}
          </Badge>
        </div>
      </TooltipTrigger>
      <TooltipContent className="bg-cyan-900 text-white">
        <p className="font-semibold">Position 2: Mid</p>
        <p className="text-cyan-200">{getRankLabel(user.positions.mid)}</p>
      </TooltipContent>
    </Tooltip>
  );
});

export const OfflaneBadge: React.FC<BadgeProps> = memo(({ user, compact }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.offlane) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="relative inline-block cursor-help">
          <Badge className={cn(
            "badge-primary !bg-emerald-900 !text-white hover:!bg-emerald-800 transition-colors",
            compact && "!px-1 !py-0.5"
          )}>
            <Badge className={cn(compact ? compactNumberClasses : numberClasses, "!bg-emerald-800")}>
              {user.positions.offlane}
            </Badge>
            <OfflaneSVG className={compact ? "w-4 h-4" : undefined} />
            {!compact && "Offlane"}
          </Badge>
        </div>
      </TooltipTrigger>
      <TooltipContent className="bg-emerald-900 text-white">
        <p className="font-semibold">Position 3: Offlane</p>
        <p className="text-emerald-200">{getRankLabel(user.positions.offlane)}</p>
      </TooltipContent>
    </Tooltip>
  );
});

export const SoftSupportBadge: React.FC<BadgeProps> = memo(({ user, compact }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.soft_support) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="relative inline-block cursor-help">
          <Badge className={cn(
            "badge-primary !bg-violet-900 !text-white hover:!bg-violet-800 transition-colors",
            compact && "!px-1 !py-0.5"
          )}>
            <Badge className={cn(compact ? compactNumberClasses : numberClasses, "!bg-violet-800")}>
              {user.positions.soft_support}
            </Badge>
            <SoftSupportSVG className={compact ? "w-4 h-4" : undefined} />
            {!compact && (
              <>
                <span className="hidden 2xl:inline">SoftSupport</span>
                <span className="inline 2xl:hidden">Pos4</span>
              </>
            )}
          </Badge>
        </div>
      </TooltipTrigger>
      <TooltipContent className="bg-violet-900 text-white">
        <p className="font-semibold">Position 4: Soft Support</p>
        <p className="text-violet-200">{getRankLabel(user.positions.soft_support)}</p>
      </TooltipContent>
    </Tooltip>
  );
});

export const HardSupportBadge: React.FC<BadgeProps> = memo(({ user, compact }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.hard_support) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="relative inline-block cursor-help">
          <Badge className={cn(
            "badge-primary !bg-indigo-900 !text-white hover:!bg-indigo-800 transition-colors",
            compact && "!px-1 !py-0.5"
          )}>
            <Badge className={cn(compact ? compactNumberClasses : numberClasses, "!bg-indigo-800")}>
              {user.positions.hard_support}
            </Badge>
            <HardSupportSVG className={compact ? "w-4 h-4" : undefined} />
            {!compact && (
              <>
                <span className="hidden 2xl:inline">HardSupport</span>
                <span className="inline 2xl:hidden">Pos5</span>
              </>
            )}
          </Badge>
        </div>
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
  /** Compact mode: icon + rank only, no text labels */
  compact?: boolean;
}

export const RolePositions: React.FC<RolePositionsProps> = ({ user, compact }) => {
  if (!user.positions) return null;

  return (
    <div className={cn(
      "flex flex-wrap justify-center",
      compact ? "flex-row gap-2" : "flex-col md:flex-row gap-1"
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
          <Component key={index} user={user} compact={compact} />
        ))}
    </div>
  );
};
