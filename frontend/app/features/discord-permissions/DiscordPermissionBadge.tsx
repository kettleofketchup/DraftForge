import { Check, CircleHelp, Clock, TriangleAlert, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { badgeVariants } from '~/components/ui/badge';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { cn } from '~/lib/utils';
import { VERIFICATION_LIMITATION } from './copy';
import { PermissionDetails } from './PermissionDetails';
import type { PermissionQuery } from './queries';
import { isExpired, type PermissionCheckResult } from './schemas';

type BadgeView = {
  tone: 'success' | 'warning' | 'error' | 'neutral';
  label: string;
  icon: 'check' | 'alert' | 'x' | 'help' | 'clock';
};

export function badgeView(
  result: PermissionCheckResult | undefined,
  state: PermissionQuery['state'],
  now: Date,
  disabled = false,
): BadgeView {
  if (state === 'checking')
    return { tone: 'neutral', label: 'Checking…', icon: 'clock' };
  if (state === 'error')
    return { tone: 'neutral', label: 'Unable to verify', icon: 'help' };
  if (!result) return { tone: 'neutral', label: 'Not checked', icon: 'help' };
  if (isExpired(result, now))
    return { tone: 'neutral', label: 'Check expired', icon: 'clock' };
  let view: BadgeView;
  switch (result.status) {
    case 'verified':
      view = { tone: 'success', label: 'Permissions verified', icon: 'check' };
      break;
    case 'missing_permissions':
      view = { tone: 'error', label: 'Missing permissions', icon: 'x' };
      break;
    case 'unknown':
      view = { tone: 'neutral', label: 'Unable to verify', icon: 'help' };
      break;
    case 'unconfigured':
      view = {
        tone: 'neutral',
        label:
          result.reason === 'no_channel_configured'
            ? 'No channel'
            : result.reason === 'no_server_configured'
              ? 'No server configured'
              : result.reason === 'pending_signup_post'
                ? 'Pending signup post'
                : 'Not configured',
        icon: 'help',
      };
      break;
    case 'unsupported':
      view = {
        tone: 'warning',
        label:
          result.action === 'mark_interested'
            ? 'Unsupported operation'
            : 'Cannot verify operation',
        icon: 'alert',
      };
      break;
    case 'not_applicable':
      view = { tone: 'neutral', label: 'Recipient dependent', icon: 'help' };
      break;
  }
  return disabled ? { ...view, tone: 'neutral', icon: 'help' } : view;
}

const tones = {
  success: 'bg-success/20 text-success border-success/30',
  warning: 'bg-warning/20 text-warning',
  error: 'bg-destructive/20 text-error',
  neutral: 'bg-muted text-muted-foreground',
};
const icons = {
  check: Check,
  alert: TriangleAlert,
  x: X,
  help: CircleHelp,
  clock: Clock,
};

export function DiscordPermissionBadge({
  operationLabel,
  result,
  state,
  disabled = false,
  'data-testid': testId,
}: {
  operationLabel: string;
  result: PermissionCheckResult | undefined;
  state: PermissionQuery['state'];
  disabled?: boolean;
  'data-testid'?: string;
}) {
  const [open, setOpen] = useState(false);
  const intent = useRef({
    pinned: false,
    hovered: false,
    focused: false,
    dismissed: false,
  });
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  useEffect(
    () => () => {
      if (closeTimer.current !== null) clearTimeout(closeTimer.current);
    },
    [],
  );
  const cancelClose = () => {
    if (closeTimer.current !== null) clearTimeout(closeTimer.current);
  };
  const closeAfterLeave = () => {
    cancelClose();
    closeTimer.current = setTimeout(() => {
      if (
        !intent.current.pinned &&
        !intent.current.hovered &&
        !intent.current.focused
      )
        setOpen(false);
    }, 180);
  };
  const hoverEnter = (pointerType: string) => {
    if (pointerType === 'touch') return;
    intent.current.hovered = true;
    cancelClose();
    if (!intent.current.dismissed) setOpen(true);
  };
  const hoverLeave = (pointerType: string) => {
    if (pointerType === 'touch') return;
    intent.current.hovered = false;
    intent.current.dismissed = false;
    closeAfterLeave();
  };
  const now = new Date();
  const view = badgeView(result, state, now, disabled);
  const Icon = icons[view.icon];
  const visibleResult =
    state === 'ready' || state === 'idle' ? result : undefined;
  const destination = visibleResult?.destination;
  const accessibleName = `${operationLabel}: ${view.label}${destination?.name ? ` in #${destination.name}` : destination?.channel_id ? ` in channel ${destination.channel_id}` : ''}`;
  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        cancelClose();
        if (!next) {
          intent.current.pinned = false;
          intent.current.dismissed = true;
        }
        setOpen(next);
      }}
    >
      <PopoverTrigger
        type="button"
        className={cn(
          badgeVariants({ variant: 'outline' }),
          'cursor-pointer',
          tones[view.tone],
        )}
        aria-label={accessibleName}
        data-testid={
          testId ?? `discord-permission-badge-${result?.key ?? 'unchecked'}`
        }
        onPointerEnter={(event) => hoverEnter(event.pointerType)}
        onPointerLeave={(event) => hoverLeave(event.pointerType)}
        onFocus={() => {
          intent.current.focused = true;
          cancelClose();
          if (!intent.current.dismissed) setOpen(true);
        }}
        onBlur={(event) => {
          if (panel.current?.contains(event.relatedTarget)) return;
          intent.current.focused = false;
          intent.current.dismissed = false;
          closeAfterLeave();
        }}
        onClick={(event) => {
          event.preventDefault();
          cancelClose();
          const pinned = !intent.current.pinned;
          intent.current.pinned = pinned;
          intent.current.dismissed = !pinned;
          setOpen(pinned);
          if (pinned) panel.current?.focus();
        }}
      >
        <Icon aria-hidden="true" />
        {view.label}
      </PopoverTrigger>
      <PopoverContent
        ref={panel}
        className="max-h-96 w-80 max-w-[calc(100vw-2rem)] overflow-y-auto"
        aria-label={`${operationLabel} permission details`}
        onOpenAutoFocus={(event) => {
          if (!intent.current.pinned) event.preventDefault();
        }}
        onCloseAutoFocus={(event) => {
          if (!intent.current.focused) event.preventDefault();
        }}
        onPointerEnter={(event) => hoverEnter(event.pointerType)}
        onPointerLeave={(event) => hoverLeave(event.pointerType)}
        onFocusCapture={() => {
          intent.current.focused = true;
          cancelClose();
        }}
        onBlurCapture={(event) => {
          if (event.currentTarget.contains(event.relatedTarget)) return;
          intent.current.focused = false;
          closeAfterLeave();
        }}
      >
        {disabled && (
          <p className="mb-3 text-sm text-muted-foreground">
            This option is disabled. The check is diagnostic only.
          </p>
        )}
        {visibleResult ? (
          <PermissionDetails
            result={visibleResult}
            operationLabel={operationLabel}
            historical={isExpired(visibleResult, now)}
          />
        ) : (
          <div className="flex flex-col gap-2 text-sm">
            <p>{view.label}</p>
            <p>{VERIFICATION_LIMITATION}</p>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
