import { useClickAway } from '@uidotdev/usehooks';
import { LogOutIcon, UserPenIcon } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
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
import { DiscordIcon } from '~/components/ui/icons';
import { getLogger } from '~/lib/logger';
const log = getLogger('login');

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
  const { t } = useTranslation('navbar');
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
              <Button data-testid="navbarProfileButton">
                <UserPenIcon />
                {t('profile')}
              </Button>
            </Link>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem>
            <DestructiveButton data-testid="navbarLogoutButton" onClick={logoutClick}>
              <LogOutIcon />
              {t('logout')}
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
  const { t } = useTranslation('navbar');
  const location = useLocation();
  const loginUrl = buildDiscordLoginUrl(`${location.pathname}${location.search}`);
  return (
    <PrimaryButton asChild data-testid="navbarLoginButton">
      <a href={loginUrl}>
        <DiscordIcon className="h-5 w-5" />
        <span>{t('login')}</span>
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
