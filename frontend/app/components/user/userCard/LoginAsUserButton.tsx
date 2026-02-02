/**
 * Login As User Button
 *
 * DEV ONLY: Small red icon button that allows logging in as a specific user.
 * Only visible when:
 * 1. import.meta.env.DEV (development mode, tree-shaken from production)
 * 2. NOT running under Playwright (hidden during demos/recordings)
 * 3. User has a Discord ID (required for login)
 *
 * Uses same pattern as react-scan in root.tsx.
 * Reference: docs/testing/auth/fixtures.md
 */
import { LogIn } from 'lucide-react';
import { useState } from 'react';
import { Button } from '~/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import type { UserClassType } from '~/components/user/types';
import { loginAsDiscordId, shouldShowTestFeatures } from '~/lib/test-utils';

interface Props {
  user: UserClassType;
}

export function LoginAsUserButton({ user }: Props) {
  const [isLoading, setIsLoading] = useState(false);

  // Don't render if not in test mode or if Playwright is running
  if (!shouldShowTestFeatures()) {
    return null;
  }

  // Need Discord ID to login
  if (!user.discordId) {
    return null;
  }

  const handleLogin = async () => {
    setIsLoading(true);
    try {
      await loginAsDiscordId(user.discordId!);
      // Page will reload after successful login
    } catch (error) {
      console.error('Failed to login as user:', error);
      setIsLoading(false);
    }
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-red-500 hover:text-red-400 hover:bg-red-500/10"
          onClick={handleLogin}
          disabled={isLoading}
          data-testid={`login-as-user-btn-${user.pk}`}
        >
          <LogIn className="h-3.5 w-3.5" />
          <span className="sr-only">Login as {user.username || user.nickname}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent side="top" className="bg-red-900 text-white border-red-800">
        <p className="text-xs">Login as {user.username || user.nickname}</p>
        <p className="text-xs text-red-300">(Test Only)</p>
      </TooltipContent>
    </Tooltip>
  );
}
