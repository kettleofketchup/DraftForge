import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from '~/components/api/axios'; // Assuming axios is configured for your API
import type { UserClassType, UserType } from '~/components/user/types';
import { UserCard } from '~/components/user/userCard';
import { getLogger } from '~/lib/logger';

const log = getLogger('userDetailPage');

export const UserDetailPage: React.FC = () => {
  const { pk } = useParams<{ pk: string }>();
  const [user, setUser] = useState<UserType | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (pk) {
      const getUser = async () => {
        setLoading(true);
        setError(null);
        try {
          const response = await axios.get(`/users/${pk}/`);
          setUser(response.data);
        } catch (err) {
          log.error('Failed to fetch tournament:', err);
          setError(
            'Failed to load tournament details. Please try again later.',
          );
        } finally {
          setLoading(false);
        }
      };
      getUser();
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

  if (!user) {
    return (
      <div className="flex justify-center items-center h-screen">
        Tournament not found.
      </div>
    );
  }

  return (
    <div className="container mx-auto p-4">
      {/* You can use TournamentCard or a custom layout */}

      <UserCard user={user as UserClassType} />
      {/* Additional details or components can be added here */}
    </div>
  );
};

export default UserDetailPage;
