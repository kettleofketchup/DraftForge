import { useEffect } from 'react';
import { useNavigate } from 'react-router';
import { Spinner } from '~/components/ui/spinner';
import { useUserStore } from '~/store/userStore';

export function meta() {
  return [
    { title: 'Edit Profile' },
    { name: 'description', content: 'Edit your profile' },
  ];
}

// Redirect /edit-profile to /user/{currentUserId}?edit=true
function EditProfileRedirect() {
  const navigate = useNavigate();
  const currentUser = useUserStore((state) => state.currentUser);
  const hasHydrated = useUserStore((state) => state.hasHydrated);

  useEffect(() => {
    if (hasHydrated) {
      if (currentUser?.pk) {
        navigate(`/user/${currentUser.pk}?edit=true`, { replace: true });
      } else {
        // Not logged in - redirect to home
        navigate('/', { replace: true });
      }
    }
  }, [currentUser, hasHydrated, navigate]);

  return (
    <div className="flex justify-center items-center h-screen">
      <Spinner className="size-8" />
    </div>
  );
}

export default EditProfileRedirect;
