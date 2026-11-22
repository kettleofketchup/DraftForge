import { Award, CalendarCheck, Crown, type LucideIcon } from 'lucide-react';
import type { ComponentType } from 'react';
import { ConductDetail } from '~/features/conduct/ConductPanels';
import { ConductRateExplainer } from '~/features/conduct/ConductRateExplainer';
import {
  ContributionsAdmin,
  ContributionsDetail,
} from '~/features/contributions/ContributionsPanels';
import {
  LeadershipBanner,
  LeadershipDetail,
} from '~/features/leadership/LeadershipPanels';
import type { OrgFeatureAccess } from '~/features/org-features';
import type { TrackKey } from './schemas';

export interface TrackDetailProps {
  orgId: number;
  orgUserPk: number;
  own: boolean;
  period: string;
  timeZone: string | undefined;
  access: OrgFeatureAccess;
  onClose: () => void;
}

/** Props for the track-level slots (Admin, Banner) that sit beside the leaderboard. */
export interface TrackSlotProps {
  orgId: number;
  timeZone: string | undefined;
  access: OrgFeatureAccess;
}

export interface TrackPanelSet {
  tabValue: string;
  icon: LucideIcon;
  sampleLabel: (metricKey: string) => string | null;
  totalUnit: string | null;
  emptyLabel: (periodic: boolean) => string;
  canOpen: (ctx: {
    own: boolean;
    rowsVisible: boolean;
    access: OrgFeatureAccess;
  }) => boolean;
  openOwnByDefault: boolean;
  Detail: ComponentType<TrackDetailProps>;
  Admin?: ComponentType<TrackSlotProps>;
  Banner?: ComponentType<TrackSlotProps>;
  HeaderExtra?: ComponentType;
}

export const TRACK_PANELS: Partial<Record<TrackKey, TrackPanelSet>> = {
  contribution: {
    tabValue: 'contributions',
    icon: Award,
    sampleLabel: (metricKey) => (metricKey === 'entries' ? null : 'Entries'),
    totalUnit: 'points',
    emptyLabel: () => 'No contributions in this period',
    canOpen: ({ own, rowsVisible }) => rowsVisible || own,
    openOwnByDefault: false,
    Detail: ContributionsDetail,
    Admin: ContributionsAdmin,
  },
  conduct: {
    tabValue: 'conduct',
    icon: CalendarCheck,
    sampleLabel: () => 'Events',
    totalUnit: null,
    emptyLabel: () => 'No ranked members yet',
    canOpen: ({ own, access }) => own || access.canViewConductDetails,
    openOwnByDefault: true,
    Detail: ConductDetail,
    HeaderExtra: ConductRateExplainer,
  },
  leadership: {
    tabValue: 'leadership',
    icon: Crown,
    sampleLabel: (metricKey) =>
      metricKey === 'points' ? 'Entries' : 'Reviews',
    totalUnit: 'points',
    emptyLabel: (periodic) =>
      periodic
        ? 'No leadership points in this period'
        : 'No ranked captains yet',
    canOpen: ({ own, rowsVisible }) => own || rowsVisible,
    openOwnByDefault: true,
    Detail: LeadershipDetail,
    Banner: LeadershipBanner,
  },
};

export function panelFor(key: TrackKey): TrackPanelSet | undefined {
  return TRACK_PANELS[key];
}
