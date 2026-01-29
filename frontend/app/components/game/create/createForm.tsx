import { getLogger } from '~/lib/logger';

import type { FormEvent } from 'react';
import React, { useState } from 'react';
import { DialogClose } from '~/components/ui/dialog';
import { useUserStore } from '~/store/userStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';

const log = getLogger('GameCreateForm');

import { refreshTournamentHook } from '~/components/draft/hooks/refreshTournamentHook';
import { Label } from '~/components/ui/label';
import type { GameType, TeamType, UserType } from '~/index';
import { TeamComboBox } from '../helpers/teamCombobox';
import { createGameHook } from '../hooks/createGameHook';

export const GameCreateForm: React.FC = () => {
  const currentUser: UserType = useUserStore((state) => state.currentUser);
  const [errorMessage, setErrorMessage] = useState<
    Partial<Record<keyof GameType, string>>
  >({});

  const [isSaving, setIsSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>('null');
  const tournamentId = useTournamentDataStore((state) => state.metadata?.pk);
  const teams = useTournamentDataStore((state) => state.teams);
  const loadFull = useTournamentDataStore((state) => state.loadFull);
  const [radiantPK, setRadiantPK] = useState(0);
  const [direPK, setDirePK] = useState(0);

  const [form, setForm] = useState<GameType>({} as GameType);
  const handleChange = (field: keyof GameType, value: any) => {
    setForm((prev: GameType) => ({ ...prev, [field]: value }) as GameType);
  };

  if (!currentUser.is_staff && !currentUser.is_superuser) {
    return (
      <div className="text-error">
        You do not have permission to Create Games.
      </div>
    );
  }

  const handleSave = async (e: FormEvent) => {
    if (!tournamentId) {
      log.error('No tournament ID available');
      return;
    }
    form.tournament_id = tournamentId;

    setErrorMessage({}); // Clear old errors
    createGameHook({ game: form });
    refreshTournamentHook({ tournamentId, reloadTournament: loadFull });
  };

  const inputView = (key: string, label: string, type: string = 'text') => {
    return (
      <div>
        <label className="font-semibold">{label}</label>
        <input
          type={type}
          placeholder={form[key] ?? ''}
          value={form[key] ?? ''}
          onFocus={() => handleChange(key as keyof GameType, form[key])}
          onChange={(e) => handleChange(key as keyof GameType, e.target.value)}
          className={`input input-bordered w-full mt-1 ${errorMessage[key] ? 'input-error' : ''}`}
        />
        {errorMessage[key] && (
          <p className="text-error text-sm mt-1">{errorMessage[key]}</p>
        )}
      </div>
    );
  };
  const teamPicker = () => {
    return (
      <>
        <Label htmlFor="radiant">Radiant</Label>
        <div id={'radiant'}>
          <TeamComboBox
            teams={teams}
            selectedTeam={radiantPK}
            setSelectedTeam={setRadiantPK}
          />
        </div>
        <Label htmlFor="dire">Dire</Label>

        <div id={'dire'}>
          <TeamComboBox
            teams={teams}
            selectedTeam={direPK}
            setSelectedTeam={setDirePK}
          />
        </div>
      </>
    );
  };
  return (
    <>
      {inputView('name', 'Name: ')}

      {inputView('date_played', 'Date Played')}
      {teamPicker()}
      <div className="flex flex-row items-start gap-4">
        <DialogClose asChild>
          <button
            onClick={handleSave}
            className="btn btn-primary btn-sm mt-3"
            disabled={isSaving}
          >
            <div>Create Game</div>
          </button>
        </DialogClose>
      </div>
    </>
  );
};
