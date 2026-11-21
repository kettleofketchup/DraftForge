import type { LucideIcon } from 'lucide-react';
import { TRACK_PANELS, panelFor } from './panels';
import type { TrackInfo } from './schemas';

export interface StandingTabEntry {
  value: string;
  label: string;
  icon: LucideIcon;
  track: TrackInfo;
}

export function visibleStandingTabs(
  tracks: readonly TrackInfo[],
): StandingTabEntry[] {
  const tabs: StandingTabEntry[] = [];
  for (const track of tracks) {
    const panel = panelFor(track.key);
    if (!panel || (!track.board_open && !track.can_view_own)) continue;
    tabs.push({
      value: panel.tabValue,
      label: track.label,
      icon: panel.icon,
      track,
    });
  }
  return tabs;
}

export function isStandingTabValue(value: string): boolean {
  return Object.values(TRACK_PANELS).some((p) => p?.tabValue === value);
}
