import { memo } from 'react';
import type { UserType } from '~/index';
import { Badge } from '../../ui/badge';
import {
  CarrySVG,
  HardSupportSVG,
  MidSVG,
  OfflaneSVG,
  SoftSupportSVG,
} from './icons';
interface BadgeProps {
  user: UserType;
}

import { getLogger } from '~/lib/logger';

const numberClasses =
  'absolute -top-1 -left-1 h-4 w-4 rounded-full p-0 border-white border-1 text-white';

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

export const CarryBadge: React.FC<BadgeProps> = memo(({ user }) => {
  const shouldShowBadge = useBadgeGuard(user);

  if (!shouldShowBadge) return null;
  if (!user.positions?.carry) return null;
  return (
    <div className="relative inline-block">
      <div className="flex flex-row">
        <Badge className="badge-primary bg-red-900 text-white">
          <Badge className={`${numberClasses} bg-red-900/80`}>
            {user.positions.carry}
          </Badge>
          <CarrySVG />
          Carry
        </Badge>
      </div>
    </div>
  );
});

export const MidBadge: React.FC<{ user: UserType }> = ({ user }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.mid) return null;
  return (
    <div className="relative inline-block">
      <div className="flex flex-row">
        <Badge className="badge-primary bg-cyan-900 text-white">
          <Badge className={`${numberClasses} bg-cyan-900/80`}>
            {user.positions.mid}
          </Badge>
          <MidSVG />
          Mid
        </Badge>
      </div>
    </div>
  );
};

export const OfflaneBadge: React.FC<{ user: UserType }> = ({ user }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;

  if (!user.positions?.offlane) return null;
  return (
    <div className="relative inline-block">
      <div className="flex flex-row">
        <Badge className="badge-primary badge-primary bg-green-900 text-white">
          <Badge className={`${numberClasses} bg-green-900/80`}>
            {user.positions.offlane}
          </Badge>
          <OfflaneSVG />
          Offlane
        </Badge>
      </div>
    </div>
  );
};

export const SoftSupportBadge: React.FC<{ user: UserType }> = ({ user }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.soft_support) return null;
  return (
    <div className="relative inline-block">
      <div className="flex flex-row">
        <Badge className="badge-primary bg-purple-900 text-white">
          <Badge className={`${numberClasses} bg-purple-900/80`}>
            {user.positions.soft_support}
          </Badge>
          <SoftSupportSVG />
          <span className="hidden 2xl:inline">SoftSupport</span>
          <span className="inline 2xl:hidden">SoftSup</span>
        </Badge>
      </div>
    </div>
  );
};

export const HardSupportBadge: React.FC<{ user: UserType }> = ({ user }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.hard_support) return null;
  return (
    <div className="relative inline-block">
      <div className="flex flex-row">
        <Badge className="badge-primary bg-blue-900 text-white">
          <Badge className={`${numberClasses} bg-blue-900/80`}>
            {user.positions.hard_support}
          </Badge>
          <HardSupportSVG />
          <span className="hidden 2xl:inline">HardSupport</span>
          <span className="inline 2xl:hidden">HardSup</span>
        </Badge>
      </div>
    </div>
  );
};
export const RolePositions: React.FC<{ user: UserType }> = ({ user }) => {
  if (!user.positions) return null;

  return (
    <div className="flex flex-col md:flex-row gap-1 flex-wrap">
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
          <Component key={index} user={user} />
        ))}
    </div>
  );
};
