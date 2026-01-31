import { useEffect } from 'react';
import { useNavigate } from 'react-router';
import { useUserStore } from '~/store/userStore';
import type { Route } from './+types/home';

export function meta({}: Route.MetaArgs) {
  return [
    { title: 'Profile' },
    { name: 'description', content: 'Your profile' },
  ];
}

// Redirect /profile to /user/{currentUserId}
function ProfileRedirect() {
  const navigate = useNavigate();
  const currentUser = useUserStore((state) => state.currentUser);
  const hasHydrated = useUserStore((state) => state.hasHydrated);

  useEffect(() => {
    if (hasHydrated) {
      if (currentUser?.pk) {
        navigate(`/user/${currentUser.pk}`, { replace: true });
      } else {
        // Not logged in - redirect to home
        navigate('/', { replace: true });
      }
    }
  }, [currentUser, hasHydrated, navigate]);

  return (
    <div className="flex justify-center items-center h-screen">
      <span className="loading loading-spinner loading-lg"></span>
    </div>
  );
}

export default ProfileRedirect;
