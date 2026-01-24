import type { FormEvent } from 'react';
import React, { useEffect, useState } from 'react';
import type { GameType } from '~/index';
import { getLogger } from '~/lib/logger';
const log = getLogger('GameCard');

import { motion } from 'framer-motion';
import { Edit, BarChart3 } from 'lucide-react';
import { useNavigate } from 'react-router';
import { refreshTournamentHook } from '~/components/draft/hooks/refreshTournamentHook';
import { useUserStore } from '~/store/userStore';
import { Button } from '../../ui/button';
import { updateGameHook } from '../hooks/updateGameHook';
import { GameRemoveButton } from './deleteButton';
import { DotaMatchStatsModal } from '~/components/bracket/modals';
interface Props {
  game: GameType;
  edit?: boolean;
  saveFunc?: string;
  onEditModeChange?: (isEditing: boolean) => void; // Added new prop
}

export const GameCard: React.FC<Props> = ({
  game,
  edit,
  saveFunc,
  onEditModeChange,
}) => {
  let navigate = useNavigate();
  const [editMode, setEditMode] = useState(edit || false);
  const [form, setForm] = useState<GameType>(game ?? ({} as GameType));
  const [isSaving, setIsSaving] = useState(false);
  const setTournament = useUserStore((state) => state.setTournament);
  const [error, setError] = useState(false);
  const [showStatsModal, setShowStatsModal] = useState(false);
  const [errorMessage, setErrorMessage] = useState<
    Partial<Record<keyof GameType, string>>
  >({});
  const tournament = useUserStore((state) => state.tournament);

  const allUsersFromStore = useUserStore((state) => state.users); // Assuming 'users' holds all users
  const fetchAllUsers = useUserStore((state) => state.getUsers); // Assuming 'getUsers' fetches all users

  const currentUser = useUserStore((state) => state.currentUser);
  const [saveCallback, setSaveCallBack] = useState(saveFunc || 'save');

  const handleChange = (field: keyof GameType, value: any) => {
    setForm((prev: any) => ({ ...prev, [field]: value }));
  };

  const handleSave = async (e: FormEvent) => {
    e.stopPropagation();
    setErrorMessage({}); // clear old errors
    const payload: Partial<GameType> = {
      pk: game.pk,
      ...form,
    };
    setIsSaving(true);
    await updateGameHook({ game });
    await refreshTournamentHook({ tournament, setTournament });
    setIsSaving(false);
  };

  useEffect(() => {}, [game, isSaving]);
  useEffect(() => {}, [tournament]);

  useEffect(() => {
    log.debug('reset form', game);
    setForm(game);
  }, [game]);

  useEffect(() => {
    // Added useEffect to call onEditModeChange
    if (onEditModeChange) {
      onEditModeChange(editMode);
    }
  }, [editMode, onEditModeChange]);
  log.debug('Gamecard after use effects');
  const GameHeader = () => {
    if (editMode) return null;
    return (
      <div className="flex flex-col w-40em items-top ">
        <h2 className="w-full card-title text-lg">Game</h2>
      </div>
    );
  };
  const editModeView = () => {
    return (
      <>
        <div>
          <label className="font-semibold">Round:</label>
          <input
            type="text"
            value={form.round ?? ''}
            onChange={(e) => handleChange('round', e.target.value)}
            className={`input input-bordered w-full mt-1 ${errorMessage.name ? 'input-error' : ''}`}
          />
          {errorMessage.name && (
            <p className="text-error text-sm mt-1">{errorMessage.round}</p>
          )}
        </div>
        <div>
          <label className="font-semibold" htmlFor="state-select">
            gameid:
          </label>
        </div>

        <Button
          onClick={handleSave}
          type="submit"
          className="btn btn-primary btn-sm mt-3"
          disabled={isSaving}
        >
          {saveCallback === 'create' &&
            (isSaving ? 'Saving...' : 'Create Tournament')}
          {saveCallback === 'save' && (isSaving ? 'Saving...' : 'Save Changes')}
        </Button>
      </>
    );
  };
  const viewMode = () => {
    return (
      <>
        {game.round !== undefined && (
          <div>
            <span className="font-semibold">Played:</span> {game.round}
          </div>
        )}
        {game.gameid && (
          <div>
            <span className="font-semibold">gameid: </span>
            {game.gameid}
          </div>
        )}
        {game.radiant_team && (
          <div>
            <span className="font-semibold">Radiant:</span>{' '}
            {game.radiant_team?.captain?.username}'s Team
          </div>
        )}
        {game.dire_team && (
          <div>
            <span className="font-semibold">Dire:</span>{' '}
            {game.dire_team?.captain?.username}'s Team
          </div>
        )}
      </>
    );
  };

  const editBtn = () => {
    if (!currentUser || !currentUser.is_staff) return null;
    if (saveCallback === 'create') {
      return null;
    }

    return (
      <Button
        className="w-20 ml-0 bg-purple-900 text-white"
        onClick={() => setEditMode(!editMode)}
      >
        {!editMode && <Edit />}
        {editMode ? 'Cancel' : 'Edit'}
      </Button>
    );
  };

  const headerButtons = () => {
    return (
      <div className="flex self-start flex flex-col w-full align-top  items-end justify-end gap-2 lg:flex-row lg:justify-end lg:items-top ">
        {editBtn()}
        {game.gameid && (
          <Button
            variant={'secondary'}
            className="w-24 outline-green-500"
            onClick={() => setShowStatsModal(true)}
            data-testid="view-stats-btn"
          >
            <BarChart3 className="w-4 h-4 mr-1" />
            Stats
          </Button>
        )}
      </div>
    );
  };
  log.debug('game Card');
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className={
        'flex items-center justify-center p-4 gap-6 content-center w-full h-full'
      }
      whileHover={{ scale: 1.02 }}
    >
      <div
        className="w-full h-full card bg-base-300 shadow-elevated w-full
            max-w-sm hover:bg-base-200 shadow-hover focus:outline-2
            focus:outline-offset-2 focus:outline-primary
            focus:outline-offset-2 active:bg-base-200
            transition-all duration-300 ease-in-out"
      >
        <div className="flex flex-row items-center align-start gap-2">
          {GameHeader()}
          {headerButtons()}
        </div>

        <div className="mt-4 space-y-2 text-sm">
          {editMode ? editModeView() : viewMode()}
        </div>
        <div className="flex flex-row mt-5 justify-end h-full items-end">
          <GameRemoveButton game={game} />
        </div>
      </div>

      {/* Match Stats Modal */}
      <DotaMatchStatsModal
        open={showStatsModal}
        onClose={() => setShowStatsModal(false)}
        matchId={game.gameid}
      />
    </motion.div>
  );
};
