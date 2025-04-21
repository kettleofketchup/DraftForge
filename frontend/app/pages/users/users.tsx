import { useEffect, useState } from 'react'

import type { User } from '~/components/user/types';
import  { UserCard } from '~/components/user/userCard';
import { useUsers } from '~/components/user/userUser';

import { useUserStore } from '~/store/useUserStore';

export function UsersPage() {
  const user = useUserStore((state) => state.user); // Zustand setter
  const { users, loading, error, getUsers } = useUsers();

  const [count, setCount] = useState(0)
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);


  if (!user || !user.is_staff) return (

    <div className="flex justify-center h-full content-center mb-0 mt-0 overflow-hidden p-0">
      <div className='justify-self-center content-center align-middle'>
        <span> You are not authorized to view this page</span>
      </div>
    </div>
  )
  useEffect(() => {

    getUsers();
  }, [] );


  return (

    <div className="flex justify-center h-full content-center mb-0 mt-0 overflow-hidden p-0">
      <div className='justify-self-center content-center align-middle'>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 p-6 justify-center">
          {users?.map((u) => (
            <div key={u.username} className="flex justify-center">
              <UserCard user={u} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );

}
