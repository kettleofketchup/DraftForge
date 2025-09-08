import { getLogger } from '~/lib/logger';

import type { FormEvent, JSX } from 'react';
import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Tournament } from '~/components/tournament/tournament';
import { DialogClose } from '~/components/ui/dialog';
import { Label } from '~/components/ui/label';
import { useUserStore } from '~/store/userStore';
import { TOURNAMENT_TYPE } from '../constants';
import type { TournamentClassType, TournamentType } from '../types';

const log = getLogger('editForm');

import type { UserType } from '~/components/user/types';

import { createTournament, updateTournament } from '~/components/api/api';
import { SCROLLAREA_CSS } from '~/components/reusable/modal';
import { ScrollArea } from '~/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { Input } from '~/components/ui/input';
interface Props {
  tourn: TournamentClassType; // Accepts both UserClassType and TournamentType
  form: TournamentClassType;
  setForm: React.Dispatch<React.SetStateAction<TournamentClassType>>;
}

export const TournamentEditForm: React.FC<Props> = ({
  tourn,
  form,
  setForm,
}) => {
  const currentUser: UserType = useUserStore((state) => state.currentUser); // Zustand setter
  const [errorMessage, setErrorMessage] = useState<
    Partial<Record<keyof TournamentType, string>>
  >({});

  const [isSaving, setIsSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>('null');
  const addTournament = useUserStore((state) => state.addTournament); // Zustand setter
  const delTournament = useUserStore((state) => state.delTournament); // Zustand setter
  const setTournamentStore = useUserStore((state) => state.setTournament); // Zustand setter
  const getTournaments = useUserStore((state) => state.getTournaments); // Zustand setter

  const handleChange = (field: keyof TournamentClassType, value: any) => {
    setForm((prev) => ({ ...prev, [field]: value }) as TournamentClassType);
  };

  if (!currentUser.is_staff && !currentUser.is_superuser) {
    return (
      <div className="text-error">
        You do not have permission to edit tournaments.
      </div>
    );
  }

  const createErrorMessage = (
    val: Partial<Record<keyof TournamentType, string>>,
  ): JSX.Element => {
    const headerText = () => <h5>Error creating Tournament:</h5>;
    if (!val || Object.keys(val).length === 0) return headerText();

    return (
      <div className="text-error">
        {headerText()}
        <ul>
          {Object.entries(val).map(([field, message]) => (
            <li key={field}>{message}</li>
          ))}
        </ul>
      </div>
    );
  };

  const handleSave = async (e: FormEvent) => {
    setErrorMessage({}); // Clear old errors

    tourn = new Tournament(form as TournamentType); // Create a new instance of Tournament with the form data
    log.debug(tourn);

    if (!tourn.pk) {
      let updateData = {
        ...form,
      } as Partial<TournamentType>;
      toast.promise(createTournament(updateData), {
        loading: `Creating tournament .`,
        success: () => {
          setIsSaving(true);
          setStatusMsg('tourn created successfully!');
          getTournaments(); // Refresh the tournaments list
          return `${tourn?.name} has been Created`;
        },
        error: (err) => {
          let val = err.response.data;
          log.error(`Failed to update tourn ${tourn.pk}`, err);
          setErrorMessage(val);
          return <>{createErrorMessage(val)}</>;
        },
      });
      setIsSaving(false);
    } else {
      let updateData = {
        pk: tourn.pk,
        ...form,
      } as Partial<TournamentType>;

      log.debug('Saving tournament with payload:', updateData);
      toast.promise(updateTournament(tourn.pk, updateData), {
        loading: `Updating tourn ${tourn.pk}.`,
        success: (data: TournamentType) => {
          setIsSaving(true);
          setStatusMsg('tourn updated successfully!');

          setTournamentStore(data); // Update Zustand store with the current instance
          return `${tourn.pk} has been updated`;
        },
        error: (err) => {
          let val = err.response.data;
          log.error(`Failed to update tourn ${tourn.pk}`, err);
          setErrorMessage(err);
          return <>{createErrorMessage(val)}</>;
        },
      });
      setIsSaving(false);
    }
  };

  useEffect(() => {}, [tourn, form, setForm]);

  const tournamentTypeInput = () => {
    return (
      <div className="w-full flex flex-col items-start">
        <Label htmlFor="tournament_type">Tournament Type</Label>
        <Select
          value={form.tournament_type || ''}
          onValueChange={(value) => handleChange('tournament_type', value)}
          style={{ width: '90%' }}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Select a tournament type" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectLabel>Tournament Type</SelectLabel>
              {/* Replace these with your actual TOURNAMENT_TYPE enum values */}
              {/* For example, if TOURNAMENT_TYPE.SINGLE_ELIMINATION is "Single Elimination" */}
              <SelectItem value={TOURNAMENT_TYPE.single_elimination}>
                Single Elimination
              </SelectItem>
              <SelectItem value={TOURNAMENT_TYPE.double_elimination}>
                Double Elimination
              </SelectItem>

              <SelectItem value={TOURNAMENT_TYPE.swiss}>
                Swiss System
              </SelectItem>
              {/* Add other tournament types from your enum here */}
            </SelectGroup>
          </SelectContent>
        </Select>
      </div>
    );
  };
  const inputView = (key: string, label: string, type: string = 'text') => {
    return (
      <div className="w-full">
        <Label className="font-semibold">{label}</Label>
        <Input
          type={type}
          placeholder={tourn[key] ?? ''}
          value={form[key] ?? ''}
          onFocus={() => handleChange(key as keyof TournamentType, tourn[key])}
          onChange={(e) =>
            handleChange(key as keyof TournamentType, e.target.value)
          }
          className={`input input-bordered w-full mt-1 ${errorMessage[key] ? 'input-error' : ''}`}
        />
        {errorMessage[key] && (
          <p className="text-error text-sm mt-1">{errorMessage[key]}</p>
        )}
      </div>
    );
  };

  return (
    <ScrollArea className={`${SCROLLAREA_CSS}`}>
      <div className="flex flex-col justify-center align-center items-center w-full gap-4 ">
        {inputView('name', 'Name: ')}
        {tournamentTypeInput()}
        {inputView('date_played', 'Date Played')}
        <div className="flex flex-row items-start gap-4">
          <DialogClose asChild>
            <button
              onClick={handleSave}
              className="btn btn-primary btn-sm mt-3"
              disabled={isSaving}
            >
              {tourn && tourn.pk && (isSaving ? 'Saving...' : 'Save Changes')}
              {tourn && !tourn.pk && (isSaving ? 'Saving...' : 'Create tourn')}
            </button>
          </DialogClose>
        </div>
      </div>
    </ScrollArea>
  );
};
