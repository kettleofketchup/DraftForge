import { memo } from 'react';
import type { UserType } from '~/index';
import { PositionEnum } from '~/index';
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
  if (!user.positions?.[PositionEnum.Carry]) return null;
  return (
    <Badge className="badge-primary bg-red-900 text-white">
      <CarrySVG />
      Carry
    </Badge>
  );
});

export const MidBadge: React.FC<{ user: UserType }> = ({ user }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.[PositionEnum.Mid]) return null;
  return (
    <Badge className="badge-primary bg-cyan-900 text-white">
      <MidSVG />
      Mid
    </Badge>
  );
};

export const OfflaneBadge: React.FC<{ user: UserType }> = ({ user }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;

  if (!user.positions?.[PositionEnum.Offlane]) return null;
  return (
    <Badge className="badge-primary badge-primary bg-green-900 text-white">
      <OfflaneSVG />
      Offlane
    </Badge>
  );
};

export const SoftSupportBadge: React.FC<{ user: UserType }> = ({ user }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.[PositionEnum.SoftSupport]) return null;
  return (
    <Badge className="badge-primary bg-purple-900 text-white">
      <SoftSupportSVG />
      SoftSupport
    </Badge>
  );
};

export const HardSupportBadge: React.FC<{ user: UserType }> = ({ user }) => {
  const shouldShowBadge = useBadgeGuard(user);
  if (!shouldShowBadge) return null;
  if (!user.positions?.[PositionEnum.HardSupport]) return null;
  return (
    <Badge className="badge-primary bg-blue-900 text-white">
      <HardSupportSVG />
      HardSupport
    </Badge>
  );
};
export const RolePositions: React.FC<{ user: UserType }> = ({ user }) => {
  if (!user.positions) return null;
  return (
    <div className="flex gap-1 flex-wrap">
      <CarryBadge user={user} />
      <MidBadge user={user} />
      <OfflaneBadge user={user} />
      <SoftSupportBadge user={user} />
      <HardSupportBadge user={user} />
    </div>
  );
};
