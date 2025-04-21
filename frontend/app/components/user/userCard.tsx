import React from 'react';
import type { User } from '../types';

interface Props {
  user: User;
}

export const UserCard: React.FC<Props> = ({ user }) => {
  return (
    <div className="card bg-base-200 shadow-md p-4 w-full max-w-sm">
      <div className="flex items-center gap-4">
        {user.avatar && (
                    <img
                    src={user.avatarUrl}
                    alt={`${user.username}'s avatar`}
                    className="w-16 h-16 rounded-full border border-primary"
                    />
                     )}

        <div>
          <h2 className="card-title text-lg">{user.username}</h2>
          <div className="flex gap-2 mt-1">
            {user.is_staff && (
              <span className="badge badge-warning">Staff</span>
            )}
            {user.is_superuser && (
              <span className="badge badge-error">Admin</span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 space-y-1 text-sm">
        {user.mmr && (
          <div>
            <span className="font-semibold">MMR:</span> {user.mmr}
          </div>
        )}
        {user.position && (
          <div>
            <span className="font-semibold">Position:</span> {user.position}
          </div>
        )}
        {user.steamid && (
          <div>
            <span className="font-semibold">Steam ID:</span> {user.steamid}
          </div>
        )}
      </div>
    </div>
  );
};
