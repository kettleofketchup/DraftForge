import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/components/user/types';

type PopoverType = 'player' | 'team' | null;

interface SharedPopoverState {
  type: PopoverType;
  player: UserType | null;
  team: TeamType | null;
  anchorEl: HTMLElement | null;
  isOpen: boolean;
}

export interface PlayerModalContext {
  leagueId?: number;
  organizationId?: number;
}

/** Stable callbacks. The value is constructed once and never changes. */
interface SharedPopoverActionsValue {
  showPlayerPopover: (player: UserType, anchorEl: HTMLElement) => void;
  showTeamPopover: (team: TeamType, anchorEl: HTMLElement) => void;
  hidePopover: () => void;
  openPlayerModal: (player: UserType, context?: PlayerModalContext) => void;
  openTeamModal: (team: TeamType) => void;
  setPlayerModalOpen: (open: boolean) => void;
  setTeamModalOpen: (open: boolean) => void;
}

/** Mutable state. The value changes whenever the popover/modal opens or closes. */
interface SharedPopoverStateValue {
  state: SharedPopoverState;
  playerModalState: { player: UserType | null; open: boolean; context?: PlayerModalContext };
  teamModalState: { team: TeamType | null; open: boolean };
}

interface SharedPopoverContextValue
  extends SharedPopoverActionsValue,
    SharedPopoverStateValue {}

const SharedPopoverContext = createContext<SharedPopoverContextValue | null>(null);
// Split context: action consumers (UserCard, PopoverTriggers) subscribe to a
// value that is constructed once and never changes, so popover/modal state
// transitions don't cascade re-renders down to every grid card on screen.
// State consumers (PlayerModal, popover renderer) keep using the legacy
// combined hook.
const SharedPopoverActionsContext = createContext<SharedPopoverActionsValue | null>(null);

export const useSharedPopover = () => {
  const context = useContext(SharedPopoverContext);
  if (!context) {
    throw new Error('useSharedPopover must be used within SharedPopoverProvider');
  }
  return context;
};

/**
 * Subscribe to ONLY the popover/modal action callbacks. The returned object
 * reference is stable across renders — components that use this hook do NOT
 * re-render when the popover/modal opens, closes, or changes target.
 *
 * Use this for any component that just *triggers* a popover/modal but doesn't
 * need to know whether one is currently open (e.g. cards, list rows, hover
 * triggers). The full `useSharedPopover()` is for renderers that read state.
 */
export const useSharedPopoverActions = () => {
  const context = useContext(SharedPopoverActionsContext);
  if (!context) {
    throw new Error(
      'useSharedPopoverActions must be used within SharedPopoverProvider',
    );
  }
  return context;
};

interface SharedPopoverProviderProps {
  children: React.ReactNode;
}

export const SharedPopoverProvider: React.FC<SharedPopoverProviderProps> = ({
  children,
}) => {
  const [state, setState] = useState<SharedPopoverState>({
    type: null,
    player: null,
    team: null,
    anchorEl: null,
    isOpen: false,
  });

  const [playerModalState, setPlayerModalState] = useState<{
    player: UserType | null;
    open: boolean;
    context?: PlayerModalContext;
  }>({ player: null, open: false });

  const [teamModalState, setTeamModalState] = useState<{
    team: TeamType | null;
    open: boolean;
  }>({ team: null, open: false });

  const hoverIntentRef = useRef<NodeJS.Timeout | null>(null);
  const isHoveringRef = useRef(false);

  const showPlayerPopover = useCallback((player: UserType, anchorEl: HTMLElement) => {
    isHoveringRef.current = true;
    if (hoverIntentRef.current) {
      clearTimeout(hoverIntentRef.current);
    }
    hoverIntentRef.current = setTimeout(() => {
      if (isHoveringRef.current) {
        setState({
          type: 'player',
          player,
          team: null,
          anchorEl,
          isOpen: true,
        });
      }
    }, 50);
  }, []);

  const showTeamPopover = useCallback((team: TeamType, anchorEl: HTMLElement) => {
    isHoveringRef.current = true;
    if (hoverIntentRef.current) {
      clearTimeout(hoverIntentRef.current);
    }
    hoverIntentRef.current = setTimeout(() => {
      if (isHoveringRef.current) {
        setState({
          type: 'team',
          player: null,
          team,
          anchorEl,
          isOpen: true,
        });
      }
    }, 50);
  }, []);

  const hidePopover = useCallback(() => {
    isHoveringRef.current = false;
    if (hoverIntentRef.current) {
      clearTimeout(hoverIntentRef.current);
    }
    setState((prev) => ({ ...prev, isOpen: false }));
  }, []);

  const openPlayerModal = useCallback((player: UserType, context?: PlayerModalContext) => {
    hidePopover();
    setPlayerModalState({ player, open: true, context });
  }, [hidePopover]);

  const openTeamModal = useCallback((team: TeamType) => {
    hidePopover();
    setTeamModalState({ team, open: true });
  }, [hidePopover]);

  const setPlayerModalOpen = useCallback((open: boolean) => {
    setPlayerModalState((prev) => ({ ...prev, open }));
  }, []);

  const setTeamModalOpen = useCallback((open: boolean) => {
    setTeamModalState((prev) => ({ ...prev, open }));
  }, []);

  // Actions value: constructed once. All callbacks above are useCallback with
  // empty (or [hidePopover]) deps, so this object reference NEVER changes
  // across renders. Action-only consumers via useSharedPopoverActions()
  // therefore don't re-render when popover/modal state changes.
  const actionsValue = useMemo<SharedPopoverActionsValue>(
    () => ({
      showPlayerPopover,
      showTeamPopover,
      hidePopover,
      openPlayerModal,
      openTeamModal,
      setPlayerModalOpen,
      setTeamModalOpen,
    }),
    [
      showPlayerPopover,
      showTeamPopover,
      hidePopover,
      openPlayerModal,
      openTeamModal,
      setPlayerModalOpen,
      setTeamModalOpen,
    ],
  );

  // Combined value: kept for state-reading consumers (PlayerModal, popover
  // renderer). Changes whenever any of the state slices change.
  const contextValue = useMemo<SharedPopoverContextValue>(
    () => ({ ...actionsValue, state, playerModalState, teamModalState }),
    [actionsValue, state, playerModalState, teamModalState],
  );

  return (
    <SharedPopoverActionsContext.Provider value={actionsValue}>
      <SharedPopoverContext.Provider value={contextValue}>
        {children}
      </SharedPopoverContext.Provider>
    </SharedPopoverActionsContext.Provider>
  );
};
