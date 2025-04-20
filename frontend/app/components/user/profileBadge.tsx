import React, { useState } from 'react';
import { useUser } from './useUser.tsx';

export const UserProfileBadge: React.FC = () => {
  const [inputId, setInputId] = useState<string>('');
  const { user, loading, error, getUser } = useUser();


  return (
    <>
        <div className="avatar flex ">
            <div className="ring-primary ring-offset-base-100  rounded-full ring ring-offset-2 w-100 shadow-xl hover:shadow-indigo-500/50
                            ]motion-safe:md:hover:animate-pulse motion-safe:md:hover:animate-spin motion-safe:transition delay-150 duration-300 easin-in-out">
                <img src={user.avatarUrl} alt="Vite logo animate-spin w-36" />
            </div>
    </div>
    </>
  );
};

export default UserProfileBadge;
