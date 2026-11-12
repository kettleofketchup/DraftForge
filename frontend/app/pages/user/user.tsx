import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from '~/components/api/axios';
import type { UserClassType, UserType } from '~/components/user/types';
import { UserCard } from '~/components/user/userCard';
import { getLogger } from '~/lib/logger';
import { Spinner } from '~/components/ui/spinner';
import { Alert, AlertDescription } from '~/components/ui/alert';
import { CircleX } from 'lucide-react';

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
        <Spinner className="size-8" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center h-screen">
        <Alert variant="destructive" className="w-auto">
          <CircleX />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
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
      <UserCard user={user as UserClassType} />
    </div>
  );
};

export default UserDetailPage;
