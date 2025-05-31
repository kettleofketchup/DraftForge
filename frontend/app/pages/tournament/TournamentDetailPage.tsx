import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from '~/components/api/axios'; // Assuming axios is configured for your API
import type { TournamentType } from '~/components/tournament/types';
import { TournamentCard } from '~/components/tournament/TournamentCard'; // Re-using TournamentCard for display

export const TournamentDetailPage: React.FC = () => {
  const { pk } = useParams<{ pk: string }>();
  const [tournament, setTournament] = useState<TournamentType | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (pk) {
      const fetchTournament = async () => {
        setLoading(true);
        setError(null);
        try {
          const response = await axios.get(`/tournaments/${pk}/`);
          setTournament(response.data);
        } catch (err) {
          console.error('Failed to fetch tournament:', err);
          setError(
            'Failed to load tournament details. Please try again later.',
          );
        } finally {
          setLoading(false);
        }
      };
      fetchTournament();
    }
  }, [pk]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div role="alert" className="alert alert-error">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="stroke-current shrink-0 h-6 w-6"
            fill="none"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (!tournament) {
    return (
      <div className="flex justify-center items-center h-screen">
        Tournament not found.
      </div>
    );
  }

  const tabContent1 = () => {
    return (
      <>
        <div className="tab-content bg-base-100 border-base-300 p-6">
          Tab content 1
        </div>
      </>
    );
  };

  const tabContent2 = () => {
    return (
      <>
        <div className="tab-content bg-base-100 border-base-300 p-6">
          Tab content 2
        </div>
      </>
    );
  };
  const tabContent3 = () => {
    return (
      <>
        <div className="tab-content bg-base-100 border-base-300 p-6">
          Tab content 3
        </div>
      </>
    );
  };

  const getDate = () => {
    let date = tournament.date_played
      ? (() => {
          const [year, month, day] = tournament.date_played.split('-');
          return `${month}-${day}`;
        })()
      : '';
    return ` - ${date || ''}`;
  };

  const title = () => {
    return (
      <>
        {tournament.name && (
          <h1 className="text-3xl font-bold mb-4">
            {tournament.name}
            <span className="ml-4 text-base text-base-content/50 font-normal">
              {getDate()}
            </span>
          </h1>
        )}
      </>
    );
  };
  return (
    <div className="container mx-auto p-4">
      {title()}
      <div className="tabs tabs-">
        <input
          type="radio"
          name="my_tabs_6"
          className="tab"
          aria-label="Tab 1"
        />
        {tabContent1()}

        <input
          type="radio"
          name="my_tabs_6"
          className="tab"
          aria-label="Tab 2"
          defaultChecked
        />
        {tabContent2()}

        <input
          type="radio"
          name="my_tabs_6"
          className="tab"
          aria-label="Tab 3"
        />
        {tabContent3()}
      </div>
    </div>
  );
};

export default TournamentDetailPage;
