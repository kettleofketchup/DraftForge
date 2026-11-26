import type { PermissionCheckResult } from './schemas';

export type ReasonCode = NonNullable<PermissionCheckResult['reason']>;

export const PERMISSION_LABELS: Record<string, string> = {
  VIEW_CHANNEL: 'View Channel',
  SEND_MESSAGES: 'Send Messages',
  SEND_MESSAGES_IN_THREADS: 'Send Messages in Threads',
  EMBED_LINKS: 'Embed Links',
  READ_MESSAGE_HISTORY: 'Read Message History',
  ADD_REACTIONS: 'Add Reactions',
  MENTION_EVERYONE: 'Mention Everyone',
  CREATE_EVENTS: 'Create Events',
  MANAGE_EVENTS: 'Manage Events',
  ATTACH_FILES: 'Attach Files',
  ADMINISTRATOR: 'Server-wide permission bypass',
};

export function permissionLabel(flag: string): string {
  return (
    PERMISSION_LABELS[flag] ??
    flag
      .toLowerCase()
      .replaceAll('_', ' ')
      .replace(/\b\w/g, (letter) => letter.toUpperCase())
  );
}

export function remedyFor(flag: string): string {
  return `Allow ${permissionLabel(flag)} on the bot's role and, for channel actions, check the destination's permission overrides.`;
}

export const REASON_TEXT: Record<ReasonCode, string> = {
  no_server_configured: 'Choose a Discord server to check this operation.',
  no_channel_configured:
    'Choose a destination channel to check this operation.',
  bot_unavailable: 'The bot or its server membership could not be found.',
  credential_unavailable:
    'Bot credentials are unavailable or invalid. Ask a site operator to check the connection.',
  forbidden_read:
    'Discord did not allow the bot to read the information needed for this check.',
  resource_unavailable:
    'The configured destination or saved resource is unavailable in this server.',
  rate_limited:
    'Discord is limiting permission checks. Try again after the indicated delay.',
  network_error:
    'Discord could not be reached. Recheck permissions when the connection recovers.',
  malformed_snapshot:
    'Discord returned incomplete or invalid information. Permissions could not be verified.',
  pending_signup_post:
    'The signup post must exist before its actual destination can be checked.',
  unsupported_channel_type:
    'This operation does not support the configured channel type.',
  unsupported_endpoint:
    'Discord does not provide a supported endpoint for this operation.',
  unsupported_signup_transport:
    'The current signup sender does not support text or announcement channel posts.',
};

export const BLOCKER_TEXT: Record<
  PermissionCheckResult['blockers'][number]['code'],
  string
> = {
  missing_reference:
    'A saved Discord resource is needed before this operation can be checked.',
  forum_requires_tag:
    'This forum requires a tag that the current sender does not supply.',
  communication_timeout:
    'The bot is timed out. Wait for the timeout to end, then recheck.',
  role_not_mentionable:
    'Make this role mentionable instead of granting broader mention permissions.',
  role_missing: 'A configured role no longer exists. Select an existing role.',
  thread_archived:
    'This thread is archived. Its current lifecycle does not permit verification.',
  thread_locked:
    'This thread is locked. Its current lifecycle does not permit verification.',
  private_thread_access:
    'The bot’s access to this private thread could not be confirmed.',
};

export const VERIFICATION_LIMITATION =
  'A verified check means the bot has the needed permissions now; it does not guarantee delivery.';
