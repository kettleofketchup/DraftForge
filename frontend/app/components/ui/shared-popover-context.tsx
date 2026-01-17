import React, {
  createContext,
  useCallback,
  useContext,
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

interface SharedPopoverContextValue {
  state: SharedPopoverState;
  showPlayerPopover: (player: UserType, anchorEl: HTMLElement) => void;
  showTeamPopover: (team: TeamType, anchorEl: HTMLElement) => void;
  hidePopover: () => void;
  openPlayerModal: (player: UserType) => void;
  openTeamModal: (team: TeamType) => void;
  playerModalState: { player: UserType | null; open: boolean };
  teamModalState: { team: TeamType | null; open: boolean };
  setPlayerModalOpen: (open: boolean) => void;
  setTeamModalOpen: (open: boolean) => void;
}

const SharedPopoverContext = createContext<SharedPopoverContextValue | null>(null);

export const useSharedPopover = () => {
  const context = useContext(SharedPopoverContext);
  if (!context) {
    throw new Error('useSharedPopover must be used within SharedPopoverProvider');
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

  const openPlayerModal = useCallback((player: UserType) => {
    hidePopover();
    setPlayerModalState({ player, open: true });
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

  return (
    <SharedPopoverContext.Provider
      value={{
        state,
        showPlayerPopover,
        showTeamPopover,
        hidePopover,
        openPlayerModal,
        openTeamModal,
        playerModalState,
        teamModalState,
        setPlayerModalOpen,
        setTeamModalOpen,
      }}
    >
      {children}
    </SharedPopoverContext.Provider>
  );
};
