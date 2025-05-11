import React, { use, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type {  TournamentType,  GameType,  TeamType} from '~/components/tournament/types';
import { STATE_CHOICES } from '~/components/tournament/tournament';
import axios from "../api/axios"
import { useNavigate } from "react-router";
import { useUserStore } from '~/store/userStore';
interface Props {
  tournament: TournamentType;
}

export const TournamentModal: React.FC<Props> = ({tournament
}) => {

  const [form, setForm] = useState<TournamentType>( tournament ?? {} as TournamentType);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<Partial<Record<keyof TournamentType, string>>>({});
  const getUsers = useUserStore((state) => state.getUsers);

  const addUser = useUserStore((state) => state.addUser ); // Zustand setter


  const handleChange = (field: keyof TournamentType, value: any) => {
    setForm((prev: any) => ({ ...prev, [field]: value }));
  };

  const handleSave = async (e:FormEvent) => {
        e.stopPropagation()
      setErrorMessage({}); // clear old errors


  useEffect(() => {

  }, [tournament, isSaving]);

  useEffect(() => {
    console.log("reset form", tournament)
    setForm(tournament);
  }, [tournament]);



  return (

    <div key={`usercard:${getKeyName()} base`} className='px-6 py-4 gap-6 content-center'>
        <div className="p-2 h-full card bg-base-200 shadow-md w-full
            max-w-sm hover:bg-violet-900 . focus:outline-2
            hover:shadow-xl/30
            focus:outline-offset-2 focus:outline-violet-500
            focus:outline-offset-2 active:bg-violet-900
            delay-700 duration-900 ease-in-out">
        <div className="flex items-center gap-2">
            {TournamentHeader()}
            {saveCallback !== "create" && (

                <button
                className="btn btn-sm btn-outline ml-auto"
                onClick={() => setEditMode(!editMode)}
                >
                    {editMode ? "Cancel" : "Edit" }
                </button>
            )}
        </div>

        <div className="mt-4 space-y-2 text-sm">
             {editMode ? editModeView() :viewMode() }


            {editMode ? editModeView() :viewMode() }
        </div>
        </div>
    </div>
  );
};
