import type { FormEvent } from 'react';
import React, { useEffect, useState } from 'react';
import type { TournamentType } from '~/components/tournament/types';
import { getLogger } from '~/lib/logger';
import { STATE_CHOICES } from '../constants';

const log = getLogger('TournamentCard');

import { motion } from 'framer-motion';
import { Edit } from 'lucide-react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { useUserStore } from '~/store/userStore';
import { updateTournament } from '../../api/api';
import { Button } from '../../ui/button';
import { UsersDropdown } from './UsersDropdown';
import { TournamentRemoveButton } from './deleteButton';
interface Props {
  tournament: TournamentType;
  edit?: boolean;
  saveFunc?: string;
  onEditModeChange?: (isEditing: boolean) => void;
  /** Animation delay index for staggered loading */
  animationIndex?: number;
}

export const TournamentCard: React.FC<Props> = React.memo(({
  tournament,
  edit,
  saveFunc,
  onEditModeChange,
  animationIndex = 0,
}) => {
  let navigate = useNavigate();
  const [editMode, setEditMode] = useState(edit || false);
  const [form, setForm] = useState<TournamentType>(
    tournament ?? ({} as TournamentType),
  );
  const [isSaving, setIsSaving] = useState(false);
  const setTournament = useUserStore((state) => state.setTournament);
  const [error, setError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<
    Partial<Record<keyof TournamentType, string>>
  >({});
  const allUsersFromStore = useUserStore((state) => state.users); // Assuming 'users' holds all users
  const fetchAllUsers = useUserStore((state) => state.getUsers); // Assuming 'getUsers' fetches all users

  const currentUser = useUserStore((state) => state.currentUser);

  const TOURNAMENT_TYPE_CHOICES = [
    { value: 'single_elimination', label: 'Single Elimination' },
    { value: 'double_elimination', label: 'Double Elimination' },
    { value: 'swiss', label: 'Swiss Bracket' },
  ];

  const handleChange = (field: keyof TournamentType, value: any) => {
    setForm((prev: any) => ({ ...prev, [field]: value }));
  };

  const handleSave = async (e: FormEvent) => {
    e.stopPropagation();
    setErrorMessage({}); // clear old errors

    const { pk: _pk, ...formWithoutPk } = form;
    const payload: Partial<TournamentType> = {
      pk: tournament.pk,
      ...formWithoutPk,
    };
    log.debug('Saving tournament with payload:', payload);
    log.debug('Save function:', saveFunc);

    if (!tournament.pk) return;

    toast.promise(updateTournament(tournament.pk, payload), {
      loading: `Updating Tournament for  ${tournament.pk}`,
      success: (data: TournamentType) => {
        log.debug('Tournament updated successfully:', data);
        setTournament(data);

        return `${tournament.pk} has been updated successfully!`;
      },
      error: (err) => {
        const val = err.response.data;
        log.error('Failed to update tournament', err);
        return `Failed to update tournament: ${val}`;
      },
    });

    setIsSaving(true);
  };

  const [saveCallback, setSaveCallBack] = useState(saveFunc || 'save');

  useEffect(() => {
    log.debug('reset form', tournament.pk);
    setForm(tournament);
    // Only reset form when tournament pk changes, not on every object reference change
  }, [tournament.pk]);

  useEffect(() => {
    // Added useEffect to call onEditModeChange
    if (onEditModeChange) {
      onEditModeChange(editMode);
    }
  }, [editMode, onEditModeChange]);

  const getHeaderName = () => {
    let date = tournament.date_played
      ? (() => {
          const [year, month, day] = tournament.date_played.split('-');
          return `${month}-${day}`;
        })()
      : '';
    return `${tournament.name || ''}`;
  };

  const TournamentHeader = () => {
    if (editMode) return null;
    if (!tournament || !tournament.name) return null;
    return (
      <div className="flex flex-col w-40em items-top ">
        <h2 className="w-full card-title text-lg">Tournament</h2>
        <h2 className="w-full card-subtitle text-lg text-center ">
          {getHeaderName()}
        </h2>
      </div>
    );
  };
  const editModeView = () => {
    return (
      <>
        <div>
          <label className="font-semibold">Name:</label>
          <input
            type="text"
            value={form.name ?? ''}
            onChange={(e) => handleChange('name', e.target.value)}
            className={`input input-bordered w-full mt-1 ${errorMessage.name ? 'input-error' : ''}`}
          />
          {errorMessage.name && (
            <p className="text-error text-sm mt-1">{errorMessage.name}</p>
          )}
        </div>
        <div>
          <label className="font-semibold" htmlFor="state-select">
            State:
          </label>
          <select
            id="state-select"
            value={form.state ?? ''}
            onChange={(e) => handleChange('state', e.target.value)}
            className={`select select-bordered w-full mt-1 ${errorMessage.state ? 'select-error' : ''}`}
          >
            <option disabled value="">
              Select State
            </option>
            {Object.entries(STATE_CHOICES).map(([key, value]) => (
              <option key={key} value={key}>
                {value}
              </option>
            ))}
          </select>
          {errorMessage.state && (
            <p className="text-error text-sm mt-1">{errorMessage.state}</p>
          )}
        </div>
        <div>
          <label className="font-semibold" htmlFor="tournament-type-select">
            Tournament Type:
          </label>
          <select
            id="tournament-type-select"
            value={form.tournament_type ?? ''}
            onChange={(e) => handleChange('tournament_type', e.target.value)}
            className={`select select-bordered w-full mt-1 ${errorMessage.tournament_type ? 'select-error' : ''}`}
          >
            <option disabled value="">
              Select Tournament Type
            </option>
            {TOURNAMENT_TYPE_CHOICES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
          {errorMessage.tournament_type && (
            <p className="text-error text-sm mt-1">
              {errorMessage.tournament_type}
            </p>
          )}
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
        {tournament.date_played !== undefined && (
          <div>
            <span className="font-semibold">Played:</span>{' '}
            {tournament.date_played}
          </div>
        )}
        {tournament.name && (
          <div>
            <span className="font-semibold">Name:</span> {tournament.name}
          </div>
        )}
        {tournament.tournament_type && (
          <div>
            <span className="font-semibold">Style:</span>{' '}
            {tournament.tournament_type}
          </div>
        )}

        <UsersDropdown users={tournament.captains || []} />
      </>
    );
  };

  const getKeyName = () => {
    let result = '';
    if (tournament.pk) {
      result += tournament.pk.toString();
    }
    if (tournament.date_played) {
      result += tournament.date_played.toString();
    }
    if (tournament.name) {
      result += tournament.name;
    }
    return result;
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
        <Button
          variant={'secondary'}
          className="w-20 outline-green-500"
          onClick={() => navigate(`/tournament/${tournament.pk}`)}
        >
          View
        </Button>
      </div>
    );
  };
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, delay: Math.min(animationIndex * 0.02, 0.2) }}
      key={`Tournamentcard:${getKeyName()} base`}
      className={
        'flex items-center justify-center p-4 gap-6 content-center w-full h-full'
      }
      whileHover={{ scale: 1.02 }}
    >
      <div
        className="w-full h-full card bg-base-300 shadow-elevated w-full
            max-w-sm hover:bg-base-200 focus:outline-2
            shadow-hover
            focus:outline-offset-2 focus:outline-primary
            focus:outline-offset-2 active:bg-base-200
            transition-all duration-300 ease-in-out"
      >
        <div className="flex flex-row items-center align-start gap-2">
          {TournamentHeader()}
          {headerButtons()}
        </div>

        <div className="mt-4 space-y-2 text-sm">
          {editMode ? editModeView() : viewMode()}
        </div>
        <div className="flex flex-row mt-5 justify-end h-full items-end">
          <TournamentRemoveButton tournament={tournament} />
        </div>
      </div>
    </motion.div>
  );
}, (prevProps, nextProps) => {
  // Custom comparison - only re-render if these values actually change
  return (
    prevProps.tournament.pk === nextProps.tournament.pk &&
    prevProps.tournament.name === nextProps.tournament.name &&
    prevProps.tournament.state === nextProps.tournament.state &&
    prevProps.tournament.date_played === nextProps.tournament.date_played &&
    prevProps.animationIndex === nextProps.animationIndex &&
    prevProps.edit === nextProps.edit &&
    prevProps.saveFunc === nextProps.saveFunc
  );
});
