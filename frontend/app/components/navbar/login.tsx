import { useQueryClient } from '@tanstack/react-query';
import { useClickAway } from '@uidotdev/usehooks';
import { LogOutIcon, UserPenIcon } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Link,
  useLocation,
  useNavigate,
  useRouteLoaderData,
} from 'react-router';
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

import { logout } from '~/components/api/api';
import { Button } from '~/components/ui/button';
import { DestructiveButton, PrimaryButton } from '~/components/ui/buttons';
import { DiscordIcon } from '~/components/ui/icons';
import { Skeleton } from '~/components/ui/skeleton';
import { invalidatePermissionChecks } from '~/features/discord-permissions/lifecycle';
import { getLogger } from '~/lib/logger';
import type { SessionHint } from '~/lib/sessionHint';
const log = getLogger('login');

type AvatarProps = {
  children: React.ReactNode;
};
const AvatarContainer: React.FC<AvatarProps> = (props) => {
  return (
    <div
      className="relative w-12 h-12 flex-shrink-0 ring-primary ring-offset-base-100 rounded-full
                     ring ring-offset-0 shadow-xl hover:shadow-primary/5
                       delay-150 duration-300 ease-in-out hover:bg-glow-sky"
    >
      {props.children}
    </div>
  );
};

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
  const queryClient = useQueryClient();
  const { t } = useTranslation('navbar');
  const currentUser = useUserStore((state) => state.currentUser);
  const navigate = useNavigate();
  const [showPopover, setShowPopover] = useState(false);
  const clearUser = useUserStore((state) => state.clearUser);
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
    // Clear after the server drops the session: clearing first refetches
    // per-viewer payloads that still carry the old session.
    try {
      await logout();
    } catch (err) {
      log.warn('logout_failed', { err });
    } finally {
      await invalidatePermissionChecks(queryClient, {}, 'remove');
      clearUser();
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger>
          <div
            className="m-0 p-0 rounded-full inline-flex relative"
            popoverTarget="popover-3"
            style={{ anchorName: '--anchor-3' } as React.CSSProperties}
            onClick={handleClick}
            onFocusCapture={handleClick}
          >
            <AvatarContainer>
              <UserAvatar
                user={currentUser}
                size="xl"
                className="w-full h-full"
                data-testid="user-avatar"
              />
            </AvatarContainer>
            <DraftNotificationBadge />
          </div>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuLabel>
            <Link to="/profile">
              <Button className="min-h-11" data-testid="navbarProfileButton">
                <UserPenIcon />
                {t('profile')}
              </Button>
            </Link>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem>
            <DestructiveButton
              data-testid="navbarLogoutButton"
              onClick={logoutClick}
            >
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
  const loginUrl = buildDiscordLoginUrl(
    `${location.pathname}${location.search}`,
  );
  return (
    <PrimaryButton
      asChild
      data-testid="navbarLoginButton"
      aria-label={t('login')}
      className="h-11 flex-col gap-0.5 px-2 has-[>svg]:px-2 sm:h-9 sm:flex-row sm:gap-2 sm:has-[>svg]:px-3"
    >
      <a href={loginUrl}>
        <DiscordIcon className="h-5 w-5" />
        {/* Below sm the label stacks under the icon so the button keeps the
            icon's width next to the centered PageNav dropdown. */}
        <span className="text-[10px] leading-none sm:hidden">
          {t('login_short')}
        </span>
        <span className="hidden sm:inline">{t('login')}</span>
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
  const rootData = useRouteLoaderData<{ sessionHint?: SessionHint }>('root');
  const knownAnonymous = rootData?.sessionHint === 'anonymous';

  // Read cached user after mount to avoid hydration mismatch
  useEffect(() => {
    setMounted(true);
    setCachedUser(getCachedUser());
  }, []);

  const user = hasHydrated
    ? currentUser
    : mounted && cachedUser
      ? cachedUser
      : currentUser;

  useEffect(() => {
    if (hasHydrated) {
      if (user?.username) {
        setIsCheckingAuth(false);
        getCurrentUser();
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

  // The server saw no session cookie, so the login button is what both the
  // server and the first client render can agree on.
  if (!mounted && knownAnonymous) return <LoginButton />;

  // Before mount: static placeholder to avoid Radix hydration mismatch
  if (!mounted) {
    return (
      <button type="button" className="bg-transparent border-0 p-0">
        <div className="m-0 p-0 rounded-full inline-flex relative">
          <AvatarContainer>
            <Skeleton className="size-full rounded-full bg-base-300" />
          </AvatarContainer>
          <DraftNotificationBadge />
        </div>
      </button>
    );
  }

  const hasUser = user?.username !== undefined && user?.username !== null;

  if (hasUser) {
    return <ProfileButton />;
  }

  // No user yet - skeleton while checking auth (skipped when known anonymous), then login button
  if (!knownAnonymous && (!hasHydrated || isCheckingAuth)) {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger>
          <div
            className="m-0 p-0 rounded-full inline-flex relative"
            style={{ anchorName: '--anchor-3' } as React.CSSProperties}
          >
            <AvatarContainer>
              <Skeleton className="size-full rounded-full bg-base-300" />
            </AvatarContainer>
            <DraftNotificationBadge />
          </div>
        </DropdownMenuTrigger>
      </DropdownMenu>
    );
  }

  return <LoginButton />;
};
