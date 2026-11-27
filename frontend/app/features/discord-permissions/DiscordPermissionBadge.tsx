import * as PopoverPrimitive from '@radix-ui/react-popover';
import { Check, CircleHelp, Clock, Info, TriangleAlert, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { badgeVariants } from '~/components/ui/badge';
import { DiscordIcon } from '~/components/ui/icons';
import { Popover, PopoverTrigger } from '~/components/ui/popover';
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
  checks,
  state,
  disabled = false,
  'data-testid': testId,
}: {
  operationLabel: string;
  result: PermissionCheckResult | undefined;
  checks?: readonly {
    operationLabel: string;
    result: PermissionCheckResult | undefined;
  }[];
  state: PermissionQuery['state'];
  disabled?: boolean;
  'data-testid'?: string;
}) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const restoreTrigger = useRef(false);
  const [portalContainer, setPortalContainer] = useState<HTMLElement | null>(
    null,
  );
  const attachTrigger = useCallback((node: HTMLButtonElement | null) => {
    trigger.current = node;
    // Keep pointer scrolling inside the enclosing dialog's scroll lock.
    setPortalContainer(node?.closest<HTMLElement>('[role="dialog"]') ?? null);
  }, []);
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
    if (!intent.current.dismissed) {
      if (!open) restoreTrigger.current = false;
      setOpen(true);
    }
  };
  const hoverLeave = (pointerType: string) => {
    if (pointerType === 'touch') return;
    intent.current.hovered = false;
    intent.current.dismissed = false;
    closeAfterLeave();
  };
  const now = new Date();
  const entries = checks ?? [{ operationLabel, result }];
  const views = entries.map((entry) => badgeView(entry.result, state, now));
  const aggregate =
    views.find((item) => item.tone === 'error') ??
    views.find((item) => item.tone !== 'success') ??
    views[0] ??
    badgeView(undefined, state, now);
  const view: BadgeView = disabled
    ? { ...aggregate, tone: 'neutral', icon: 'help' }
    : aggregate;
  const Icon = icons[view.icon];
  const visibleResult =
    state === 'ready' || state === 'idle' ? result : undefined;
  const destination = checks ? undefined : visibleResult?.destination;
  const accessibleName = `Discord ${operationLabel}: ${view.label}${destination?.name ? ` in #${destination.name}` : destination?.channel_id ? ` in channel ${destination.channel_id}` : ''}`;
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
        ref={attachTrigger}
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
          if (!intent.current.dismissed) {
            if (!open) restoreTrigger.current = false;
            setOpen(true);
          }
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
          restoreTrigger.current = !pinned;
          intent.current.pinned = pinned;
          intent.current.dismissed = !pinned;
          setOpen(pinned);
          if (pinned) panel.current?.focus();
        }}
      >
        <DiscordIcon
          aria-hidden="true"
          data-testid="discord-permission-discord-icon"
        />
        {view.tone !== 'success' && <Icon aria-hidden="true" />}
        {view.label}
        <Info
          aria-hidden="true"
          data-testid="discord-permission-info-icon"
          className="opacity-70"
        />
      </PopoverTrigger>
      <PopoverPrimitive.Portal container={portalContainer}>
        <PopoverPrimitive.Content
          ref={panel}
          className="bg-popover text-popover-foreground z-50 rounded-md border p-4 shadow-md outline-hidden w-80 max-w-[calc(100vw-2rem)] max-h-[min(24rem,var(--radix-popover-content-available-height))] overflow-y-auto overscroll-contain touch-pan-y"
          collisionPadding={16}
          collisionBoundary={portalContainer ?? undefined}
          tabIndex={0}
          aria-label={`${operationLabel} permission details`}
          onOpenAutoFocus={(event) => {
            if (!intent.current.pinned) event.preventDefault();
          }}
          onEscapeKeyDown={() => {
            restoreTrigger.current = true;
          }}
          onPointerDownOutside={() => {
            restoreTrigger.current = false;
          }}
          onCloseAutoFocus={(event) => {
            if (restoreTrigger.current) {
              event.preventDefault();
              trigger.current?.focus({ preventScroll: true });
            } else if (!intent.current.focused) event.preventDefault();
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
          <div className="space-y-4">
            {entries.map((entry, index) => {
              const visible =
                state === 'ready' || state === 'idle'
                  ? entry.result
                  : undefined;
              const status = badgeView(
                entry.result,
                state,
                now,
                disabled,
              ).label;
              return visible ? (
                <PermissionDetails
                  key={entry.operationLabel}
                  result={visible}
                  operationLabel={entry.operationLabel}
                  statusLabel={status}
                  historical={isExpired(visible, now)}
                />
              ) : (
                <section
                  key={entry.operationLabel}
                  className="flex flex-col gap-2 text-sm"
                >
                  <h3 className="font-semibold">
                    {entry.operationLabel} permissions
                  </h3>
                  <p>{views[index]?.label ?? view.label}</p>
                  <p>{VERIFICATION_LIMITATION}</p>
                </section>
              );
            })}
          </div>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </Popover>
  );
}
