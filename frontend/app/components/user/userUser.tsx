import { useState, useCallback } from 'react';
import { fetchCurrentUser, fetchUsers } from '../api/api';
import type { User, Users } from './types';
import { useUserStore } from '../../store/useUserStore';

export function useUser() {
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);
  const setUser = useUserStore((state) => state.setUser); // Zustand setter
  const user = useUserStore((state) => state.user); // Zustand setter

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

export function useUsers() {
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);
  const setUsers = useUserStore((state) => state.setUsers); // Zustand setter
  const users = useUserStore((state) => state.users); // Zustand setter

  const getUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      console.log("User fetching");

        fetchUsers().then( (response) => {
          setUsers(response)
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
  return { users, loading, error, getUsers };
}
