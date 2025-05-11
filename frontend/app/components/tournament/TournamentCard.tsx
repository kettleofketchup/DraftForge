import React, { use, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { TournamentType, GameType, TeamType } from '~/components/tournament/types';
import { STATE_CHOICES } from '~/components/tournament/tournament';
import axios from "../api/axios"
import { useNavigate } from "react-router";
import { useUserStore } from '~/store/userStore';

interface Props {
  tournament: TournamentType;
  edit?: boolean;
  saveFunc?: string;
}

export const TournamentCard: React.FC<Props> = ({ tournament, edit, saveFunc }) => {

  const [editMode, setEditMode] = useState(edit || false);
  const [form, setForm] = useState<TournamentType>(tournament ?? {} as TournamentType);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<Partial<Record<keyof TournamentType, string>>>({});
  const getUsers = useUserStore((state) => state.getUsers);

  const TOURNAMENT_TYPE_CHOICES = [
    { value: "single_elimination", label: "Single Elimination" },
    { value: "double_elimination", label: "Double Elimination" },
    { value: "swiss", label: "Swiss Bracket" },
  ];

  const handleChange = (field: keyof TournamentType, value: any) => {
    setForm((prev: any) => ({ ...prev, [field]: value }));
  };

  const handleSave = async (e: FormEvent) => {
    e.stopPropagation()
    setErrorMessage({}); // clear old errors

    if (saveFunc === "create") {
      setIsSaving(true);
      try {
        await axios.post(`/tournament`, form);
        setError(false);
        setForm({} as TournamentType);
        const modalCheckbox = document.getElementById("create_tournament_modal") as HTMLInputElement;
        if (modalCheckbox) modalCheckbox.checked = false;

      } catch (err: any) {
        console.error("Failed to create tournament", err);
        setErrorMessage(err.response.data);
        setError(true);

      } finally {
        setIsSaving(false);

      }

    }
    else if (saveFunc === "save") {
      if (!form.pk) return;
      setIsSaving(true);
      try {
        await axios.patch(`/users/${tournament.pk}/`, form);
        setEditMode(false);
        setError(false);
        getUsers(); // Triggers fetch and repopulates store

      } catch (err: any) {
        setError(true);
        setErrorMessage(err.response.data);

        console.error("Failed to update tournament", err);

      } finally {
        setIsSaving(false);
      }
    }
  };

  const [saveCallback, setSaveCallBack] = useState(saveFunc || "save");

  useEffect(() => {

  }, [tournament, isSaving]);

  useEffect(() => {
    console.log("reset form", tournament)
    setForm(tournament);
  }, [tournament]);

  const TournamentHeader = () => {
    return (
      <>
        {!editMode && (
          <div className="flex-1">

            <h2 className="card-title text-lg">{tournament.date_played}</h2>

            <div className="flex gap-2 mt-1">
              {tournament.state === STATE_CHOICES.in_progress && <span className="badge badge-warning">In Progress</span>}
              {tournament.state === STATE_CHOICES.future && <span className="badge badge-error">Admin</span>}
              {tournament.state === STATE_CHOICES.past && <span className="badge badge-success">Past</span>}
            </div>
          </div>
        )}
      </>
    )
  }

  const editModeView = () => {
    return (
      <>
        <div>
          <label className="font-semibold">Name:</label>
          <input
            type="text"
            value={form.name ?? ''}
            onChange={(e) => handleChange("name", e.target.value)}
            className={`input input-bordered w-full mt-1 ${errorMessage.name ? 'input-error' : ''}`}
          />
          {errorMessage.name && (
            <p className="text-error text-sm mt-1">{errorMessage.name}</p>
          )}
        </div>
        <div>
          <label className="font-semibold" htmlFor="state-select">State:</label>
          <select
            id="state-select"
            value={form.state ?? ''}
            onChange={(e) => handleChange("state", e.target.value)}
            className={`select select-bordered w-full mt-1 ${errorMessage.state ? 'select-error' : ''}`}
          >
            <option disabled value="">Select State</option>
            {Object.entries(STATE_CHOICES).map(([key, value]) => (
              <option key={key} value={key}>{value}</option>
            ))}
          </select>
          {errorMessage.state && (
            <p className="text-error text-sm mt-1">{errorMessage.state}</p>
          )}
        </div>
        <div>
          <label className="font-semibold" htmlFor="tournament-type-select">Tournament Type:</label>
          <select
            id="tournament-type-select"
            value={form.tournament_type ?? ''}
            onChange={(e) => handleChange("tournament_type", e.target.value)}
            className={`select select-bordered w-full mt-1 ${errorMessage.tournament_type ? 'select-error' : ''}`}
          >
            <option disabled value="">Select Tournament Type</option>
            {TOURNAMENT_TYPE_CHOICES.map((type) => (
              <option key={type.value} value={type.value}>{type.label}</option>
            ))}
          </select>
          {errorMessage.tournament_type && (
            <p className="text-error text-sm mt-1">{errorMessage.tournament_type}</p>
          )}
        </div>

        <button
          onClick={handleSave}
          className="btn btn-primary btn-sm mt-3"
          disabled={isSaving}
        >
          {saveCallback === "create" && (isSaving ? "Saving..." : "Create User")}
          {saveCallback === "save" && (isSaving ? "Saving..." : "Save Changes")}
        </button>
      </>
    );
  };

  const viewMode = () => {
    return (<>
      {tournament.date_played !== undefined && (
        <div>
          <span className="font-semibold">Played:</span> {tournament.date_played}
        </div>
      )}
      {tournament.name && (
        <div>
          <span className="font-semibold">Name:</span> {tournament.name}
        </div>
      )}
      {tournament.tournament_type && (
        <div>
          <span className="font-semibold">Style:</span> {tournament.tournament_type}
        </div>
      )}
      {tournament.users && tournament.users.length > 0 && (
        <div className="collapse collapse-arrow border border-base-300 bg-base-200 rounded-box">
          <input type="checkbox" />
          <div className="collapse-title text-md font-medium">
            Players ({tournament.users.length})
          </div>
          <div className="collapse-content">
            <ul className="list-disc list-inside ml-4">
              {tournament.users.map((user) => (
                <li key={user.pk || user.username}>{user.nickname || user.username}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>)
  }

  const getKeyName = () => {
    let result = ""
    if (tournament.pk) {
      result += tournament.pk.toString();
    }
    if (tournament.date_played) {
      result += tournament.date_played.toString();
    }
    if (tournament.name) {
      result += tournament.name;
    }
    return result
  }
  return (

    <div key={`usercard:${getKeyName()} base`} className='px-6 py-4 gap-6 content-center'>
      <div className=" p-2 h-full card bg-base-200 shadow-md w-full
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
              {editMode ? "Cancel" : "Edit"}
            </button>
          )}
        </div>

        <div className="mt-4 space-y-2 text-sm">
          {editMode ? editModeView() : viewMode()}

        </div>
      </div>
    </div>
  );
};
