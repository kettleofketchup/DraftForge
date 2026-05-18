import { useClickAway } from '@uidotdev/usehooks';
import { LogOutIcon, UserPenIcon } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { DraftNotificationBadge } from '~/components/teamdraft/DraftNotificationBadge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import { UserAvatar } from '~/components/user/UserAvatar';
import { useUserStore } from '../../store/userStore';
import type { UserType } from '../user/types';

import { Button } from '~/components/ui/button';
import { DestructiveButton, PrimaryButton } from '~/components/ui/buttons';
import { getLogger } from '~/lib/logger';
const log = getLogger('login');

const DiscordIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    className={className}
    aria-hidden="true"
  >
    <path d="M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z" />
  </svg>
);

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
              <UserAvatar user={currentUser} size="xl" className="w-full h-full" data-testid="user-avatar" />
            </AvatarContainer>
            <DraftNotificationBadge />
          </div>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuLabel>
            <Link to="/profile">
              <Button>
                <UserPenIcon />
                Profile
              </Button>
            </Link>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem>
            <DestructiveButton onClick={logoutClick}>
              <LogOutIcon />
              Logout
            </DestructiveButton>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );
};

// Build a Discord OAuth login URL that returns the user to `returnTo`
// after auth completes. Passed through python-social-auth's `?next=` param,
// which is honored by the social_django pipeline and falls back to
// LOGIN_REDIRECT_URL when absent or unsafe.
export const buildDiscordLoginUrl = (returnTo?: string | null): string => {
  const base = '/login/discord/';
  if (!returnTo || returnTo === '/' || returnTo === '/done') return base;
  return `${base}?next=${encodeURIComponent(returnTo)}`;
};

export const LoginButton: React.FC = () => {
  const location = useLocation();
  const loginUrl = buildDiscordLoginUrl(`${location.pathname}${location.search}`);
  return (
    <PrimaryButton asChild data-testid="navbarLoginButton">
      <a href={loginUrl}>
        <DiscordIcon className="h-5 w-5" />
        <span>Login with Discord</span>
      </a>
    </PrimaryButton>
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
