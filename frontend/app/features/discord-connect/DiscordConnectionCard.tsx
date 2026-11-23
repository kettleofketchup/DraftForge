import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Loader2,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { toast } from 'sonner';
import { PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import { DiscordIcon } from '~/components/ui/icons';
import { extractApiError } from '~/lib/apiError';
import { useDiscordBotStatus, useStartDiscordConnect } from './queries';

export interface DiscordConnectionCardProps {
  orgId: number;
  serverId: string | null | undefined;
  /** Unsaved settings would be lost by leaving for Discord. */
  hasUnsavedChanges: boolean;
}

export function DiscordConnectionCard({
  orgId,
  serverId,
  hasUnsavedChanges,
}: DiscordConnectionCardProps) {
  const status = useDiscordBotStatus(orgId, true);
  const connect = useStartDiscordConnect(orgId);

  const start = () =>
    connect.mutate(undefined, {
      onError: (err) =>
        toast.error(extractApiError(err) ?? 'Could not reach Discord'),
    });

  const hasBot = status.data?.has_bot === true;
  const busy = connect.isPending || connect.isSuccess;
  const buttonIcon = busy ? (
    <Loader2 className="h-4 w-4 animate-spin" />
  ) : (
    <ExternalLink className="h-4 w-4" />
  );
  const buttonProps = {
    type: 'button' as const,
    onClick: start,
    disabled: busy || hasUnsavedChanges,
    'data-testid': 'org-discord-connect-button',
  };

  let summary: ReactNode;
  if (status.isPending && serverId) {
    summary = <span className="text-muted-foreground">Checking…</span>;
  } else if (hasBot) {
    summary = (
      <span
        className="flex items-center gap-2"
        data-testid="org-discord-connected"
      >
        <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
        <span className="min-w-0 truncate">
          Connected to <strong>{status.data?.guild_name ?? serverId}</strong>
        </span>
      </span>
    );
  } else if (serverId) {
    summary = (
      <span
        className="flex items-center gap-2"
        data-testid="org-discord-bot-missing"
      >
        <AlertTriangle className="h-4 w-4 shrink-0 text-warning" />
        The DraftForge bot isn't in this server
      </span>
    );
  } else {
    summary = (
      <span
        className="text-muted-foreground"
        data-testid="org-discord-not-connected"
      >
        Not connected
      </span>
    );
  }

  return (
    <div
      className="flex flex-col gap-3 rounded-md border border-border p-4"
      data-testid="org-discord-connection"
    >
      <div className="flex items-center gap-2 font-medium">
        <DiscordIcon className="h-5 w-5 text-discord" />
        Discord server
      </div>
      <div className="text-sm">{summary}</div>
      <p className="text-sm text-muted-foreground">
        {hasBot
          ? 'Member search, event posts and signups use this server. Switch to add the bot to a different one.'
          : 'Adds the DraftForge bot to your server and links it here, which turns on member search, event posts and signups.'}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        {hasBot ? (
          <SecondaryButton {...buttonProps}>
            {buttonIcon}
            Switch server
          </SecondaryButton>
        ) : (
          <PrimaryButton {...buttonProps}>
            {buttonIcon}
            {serverId ? 'Add bot to server' : 'Connect Discord server'}
          </PrimaryButton>
        )}
        {hasUnsavedChanges && (
          <span className="text-xs text-muted-foreground">
            Save or discard your changes first.
          </span>
        )}
      </div>
    </div>
  );
}
