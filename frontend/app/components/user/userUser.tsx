import { useState, useCallback } from 'react';
import { fetchCurrentUser } from '../api/api';
import type { User } from './types';

export function useUser() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);

  const getUser = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      console.log("User fetching");

       fetchCurrentUser().then( (response) => {
          setUser(response)
          console.log('User fetched successfully:', response);     })
        .catch((error) => {
          console.error('Error fetching user:', error);
          setError(error);
      });
    }
    catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  return { user, loading, error, getUser };
}
