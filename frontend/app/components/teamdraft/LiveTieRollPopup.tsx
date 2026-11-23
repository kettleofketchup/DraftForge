import { useCallback } from 'react';
import { serverNow } from '~/lib/draftClock/clock';
import {
  draftWsSelectors,
  useDraftWebSocketStore,
} from '~/store/draftWebSocketStore';
import { TieRollPopup, liveTieHold, type TieRollTeam } from './TieRollPopup';
import type { TieResolution } from './types';

interface LiveTieRollPopupProps {
  tie: TieResolution;
  teams: TieRollTeam[];
  clockHeld: boolean;
  onDone: () => void;
}

/** TieRollPopup fed the live draft clock, so a pause or resume during the hold moves its countdown. */
export function LiveTieRollPopup(props: LiveTieRollPopupProps) {
  const tick = useDraftWebSocketStore((s) => s.tick);
  const draftState = useDraftWebSocketStore((s) => s.draftState);
  const tickIsNewer = useDraftWebSocketStore(
    draftWsSelectors.tickIsNewerThanDraftState,
  );
  const tieServerNow = useCallback(
    () => serverNow(useDraftWebSocketStore.getState().serverClockOffsetMs),
    [],
  );
  return (
    <TieRollPopup
      {...props}
      serverNow={tieServerNow}
      liveHold={liveTieHold(
        tick,
        draftState,
        tickIsNewer,
        props.tie.pick_number,
      )}
    />
  );
}
