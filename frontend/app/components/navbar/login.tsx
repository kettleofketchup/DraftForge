import { useClickAway } from '@uidotdev/usehooks';
import { LogOutIcon, UserPenIcon } from 'lucide-react';
import React, { memo, useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { DraftNotificationBadge } from '~/components/draft/DraftNotificationBadge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import { useUserStore } from '../../store/userStore';
import type { UserType } from '../user/types';

import { Button } from '~/components/ui/button';
import { getLogger } from '~/lib/logger';
const log = getLogger('login');
type UserProps = {
  user: UserType;
};
type AvatarProps = {
  children: React.ReactNode;
};
const AvatarContainer: React.FC<AvatarProps> = (props) => {
  return (
    <div
      className="relative w-12 h-12 flex-shrink-0 ring-primary ring-offset-base-100 rounded-full
                     ring ring-offset-0 shadow-xl hover:shadow-indigo-500/5
                       delay-150 duration-300 ease-in-out hover:bg-sky-100"
    >
      {props.children}
    </div>
  );
};
export const UserAvatarImg: React.FC<UserProps> = memo(({ user }) => {
  const [isLoaded, setIsLoaded] = useState(false);
  const [hasError, setHasError] = useState(false);

  // Reset loading state when user changes
  React.useEffect(() => {
    setIsLoaded(false);
    setHasError(false);
  }, [user?.avatarUrl]);

  if (!user) {
    return <div className="w-full h-full skeleton rounded-full" />;
  }

  if (hasError) {
    return (
      <div className="w-full h-full bg-base-300 rounded-full flex items-center justify-center">
        <span className="text-xs text-base-content/50">
          {user.username?.charAt(0)?.toUpperCase() || '?'}
        </span>
      </div>
    );
  }

  return (
    <>
      {!isLoaded && <div className="absolute inset-0 skeleton rounded-full" />}
      <img
        src={user.avatarUrl}
        alt={user.username}
        className={`w-full h-full rounded-full ${isLoaded ? 'opacity-100' : 'opacity-0'}`}
        onLoad={() => setIsLoaded(true)}
        onError={() => setHasError(true)}
      />
    </>
  );
});

import { logout } from '~/components/api/api';

// Try to get cached user from sessionStorage (client-side only)
const getCachedUser = (): UserType | null => {
  try {
    const stored = sessionStorage.getItem('dtx-storage');
    if (stored) {
      const parsed = JSON.parse(stored);
      return parsed?.state?.currentUser || null;
    }
  } catch {
    // Ignore parse errors
  }
  return null;
};

export const ProfileButton: React.FC = () => {
  const currentUser = useUserStore((state) => state.currentUser); // Zustand user state
  const navigate = useNavigate();
  const [showPopover, setShowPopover] = useState(false);
  const clearUser = useUserStore((state) => state.clearUser); // Zustand setter
  useEffect(() => {}, [currentUser.username]);
  const handleClick = () => {
    setShowPopover((prev) => !prev);
    log.debug('Show popover');
  };
  const hidePopover = () => {
    setShowPopover(false);
  };

  const ref = useClickAway(() => {
    setShowPopover(false);
  });
  const logoutClick = async () => {
    log.debug('Logout clicked');
    clearUser();
    await logout();
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger>
          <div
            className="m-0 btn-circle avatar flex p-0 relative"
            popoverTarget="popover-3"
            style={{ anchorName: '--anchor-3' } as React.CSSProperties}
            onClick={handleClick}
            onFocusCapture={handleClick}
          >
            <AvatarContainer>
              <UserAvatarImg user={currentUser} />
            </AvatarContainer>
            <DraftNotificationBadge />
          </div>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuLabel>
            <a href="/profile">
              <Button>
                <UserPenIcon />
                Profile
              </Button>
            </a>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem>
            <Button className="" onClick={logoutClick} variant={'destructive'}>
              <LogOutIcon />
              Logout
            </Button>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );
};

export const LoginButton: React.FC = () => {
  const loginUrl = '/login/discord/';
  return (
    <a className="p-2" href={loginUrl}>
      <button className="bg-gray-950 flex items-center border border-gray-300 rounded-lg shadow-md px-6 py-2 text-sm font-medium text-gray-400 hover:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500">
        <svg
          className="h-6 w-6 mr-2"
          xmlns="http://www.w3.org/2000/svg"
          xmlnsXlink="http://www.w3.org/1999/xlink"
          width="800px"
          height="800px"
          viewBox="0 -28.5 256 256"
          version="1.1"
          preserveAspectRatio="xMidYMid"
        >
          <g>
            <path
              d="M216.856339,16.5966031 C200.285002,8.84328665 182.566144,3.2084988 164.041564,0 C161.766523,4.11318106 159.108624,9.64549908 157.276099,14.0464379 C137.583995,11.0849896 118.072967,11.0849896 98.7430163,14.0464379 C96.9108417,9.64549908 94.1925838,4.11318106 91.8971895,0 C73.3526068,3.2084988 55.6133949,8.86399117 39.0420583,16.6376612 C5.61752293,67.146514 -3.4433191,116.400813 1.08711069,164.955721 C23.2560196,181.510915 44.7403634,191.567697 65.8621325,198.148576 C71.0772151,190.971126 75.7283628,183.341335 79.7352139,175.300261 C72.104019,172.400575 64.7949724,168.822202 57.8887866,164.667963 C59.7209612,163.310589 61.5131304,161.891452 63.2445898,160.431257 C105.36741,180.133187 151.134928,180.133187 192.754523,160.431257 C194.506336,161.891452 196.298154,163.310589 198.110326,164.667963 C191.183787,168.842556 183.854737,172.420929 176.223542,175.320965 C180.230393,183.341335 184.861538,190.991831 190.096624,198.16893 C211.238746,191.588051 232.743023,181.531619 254.911949,164.955721 C260.227747,108.668201 245.831087,59.8662432 216.856339,16.5966031 Z M85.4738752,135.09489 C72.8290281,135.09489 62.4592217,123.290155 62.4592217,108.914901 C62.4592217,94.5396472 72.607595,82.7145587 85.4738752,82.7145587 C98.3405064,82.7145587 108.709962,94.5189427 108.488529,108.914901 C108.508531,123.290155 98.3405064,135.09489 85.4738752,135.09489 Z M170.525237,135.09489 C157.88039,135.09489 147.510584,123.290155 147.510584,108.914901 C147.510584,94.5396472 157.658606,82.7145587 170.525237,82.7145587 C183.391518,82.7145587 193.761324,94.5189427 193.539891,108.914901 C193.539891,123.290155 183.391518,135.09489 170.525237,135.09489 Z"
              fill="#5865F2"
              fillRule="nonzero"
            ></path>
          </g>
        </svg>

        <span>Login</span>
      </button>
    </a>
  );
};

type props = {};
export const LoginWithDiscordButton: React.FC<props> = () => {
  const currentUser = useUserStore((state) => state.currentUser);
  const hasHydrated = useUserStore((state) => state.hasHydrated);
  const getCurrentUser = useUserStore((state) => state.getCurrentUser);
  const [mounted, setMounted] = useState(false);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const [cachedUser, setCachedUser] = useState<UserType | null>(null);

  // Read cached user after mount to avoid hydration mismatch
  useEffect(() => {
    setMounted(true);
    setCachedUser(getCachedUser());
  }, []);

  // Use cached user after mount, then switch to store user after hydration
  const user = hasHydrated ? currentUser : (mounted && cachedUser ? cachedUser : currentUser);

  // Check auth after hydration - background refresh
  useEffect(() => {
    if (hasHydrated) {
      // If we already have a user (from cache or store), just refresh in background
      if (user?.username) {
        setIsCheckingAuth(false);
        getCurrentUser(); // Background refresh
      } else {
        // No cached user - must wait for API
        const checkAuth = async () => {
          await getCurrentUser();
          setIsCheckingAuth(false);
        };
        checkAuth();
      }
    }
  }, [hasHydrated]);

  // Before mount: static placeholder to avoid Radix hydration mismatch
  if (!mounted) {
    return (
      <button type="button" className="bg-transparent border-0 p-0">
        <div className="m-0 btn-circle avatar flex p-0 relative">
          <AvatarContainer>
            <div className="w-full h-full skeleton rounded-full" />
          </AvatarContainer>
          <DraftNotificationBadge />
        </div>
      </button>
    );
  }

  // If we have a user (cached or from store), show them immediately
  const hasUser = user?.username !== undefined && user?.username !== null;

  if (hasUser) {
    return <ProfileButton />;
  }

  // No user yet - show skeleton while checking auth, then login button
  if (!hasHydrated || isCheckingAuth) {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger>
          <div
            className="m-0 btn-circle avatar flex p-0 relative"
            style={{ anchorName: '--anchor-3' } as React.CSSProperties}
          >
            <AvatarContainer>
              <div className="w-full h-full skeleton rounded-full" />
            </AvatarContainer>
            <DraftNotificationBadge />
          </div>
        </DropdownMenuTrigger>
      </DropdownMenu>
    );
  }

  return <LoginButton />;
};
