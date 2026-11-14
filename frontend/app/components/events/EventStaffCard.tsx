import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { Crown, UserPlus, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { toast } from 'sonner';

import type {
  AddMemberPayload,
  DiscordSearchResult,
  SearchUserResult,
} from '~/components/api/api';
import type { EventStaffUser, EventType } from '~/components/events/schemas';
import { Card, CardContent, CardHeader } from '~/components/ui/card';
import { PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import { AddUserModal } from '~/components/user/AddUserModal';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { UserType } from '~/components/user/types';
import { usePointValues } from '~/features/contributions';
import type { OrgFeatureAccess } from '~/features/org-features';
import { useEventActionMutation } from '~/hooks/useEvent';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';

const log = getLogger('EventStaffCard');

export interface StaffPointValues {
  event_host: number;
  event_helper: number;
}

export interface EventStaffCardProps {
  event: EventType;
  canEdit: boolean;
  showPoints: boolean;
  pointValues?: StaffPointValues;
  hasDiscordServer?: boolean;
}

interface StaffState {
  host: EventStaffUser | null;
  helpers: EventStaffUser[];
}

type PickerMode = 'host' | 'helper';

function staffKey(state: StaffState): string {
  return JSON.stringify([
    state.host?.pk ?? null,
    state.helpers.map((h) => h.pk).sort((a, b) => a - b),
  ]);
}

function displayName(user: EventStaffUser): string {
  return user.nickname || user.username;
}

function findSearchedUser(queryClient: QueryClient, pk: number): EventStaffUser | null {
  for (const [, results] of queryClient.getQueriesData<SearchUserResult[]>({
    queryKey: ['userSearch'],
  })) {
    const match = results?.find((u) => u.pk === pk);
    if (match) {
      return {
        pk,
        username: match.username ?? `User #${pk}`,
        nickname: match.nickname ?? null,
        avatarUrl: match.avatarUrl ?? null,
      };
    }
  }
  for (const [, results] of queryClient.getQueriesData<DiscordSearchResult[]>({
    queryKey: ['discordSearch'],
  })) {
    const member = results?.find((m) => m.site_user_pk === pk);
    if (member) {
      return {
        pk,
        username: member.user.username,
        nickname: member.nick || member.user.global_name || null,
        avatarUrl: member.user.avatar
          ? `https://cdn.discordapp.com/avatars/${member.user.id}/${member.user.avatar}`
          : null,
      };
    }
  }
  return null;
}

function logSaveFailure(eventId: number, err: unknown): void {
  const status = (err as { response?: { status?: number } })?.response?.status;
  const context = { eventId, status, error: extractApiError(err) };
  if (status != null && status >= 400 && status < 500) {
    log.warn('event_staff_save_failed', context);
  } else {
    log.error('event_staff_save_failed', context);
  }
}

function StaffRow({
  user,
  role,
  points,
  onRemove,
  removeTestId,
}: {
  user: EventStaffUser;
  role: string;
  points: number | null;
  onRemove?: () => void;
  removeTestId?: string;
}) {
  return (
    <div className="flex items-center gap-2 py-1.5">
      <UserAvatar user={user} size="sm" />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-sm font-semibold text-foreground">{displayName(user)}</span>
        <span className="text-xs text-muted-foreground">{role}</span>
      </div>
      {points !== null && (
        <span className="text-xs font-medium text-primary">+{points} pts</span>
      )}
      {onRemove && (
        <SecondaryButton
          type="button"
          size="sm"
          color="red"
          onClick={onRemove}
          aria-label={`Remove ${displayName(user)}`}
          data-testid={removeTestId}
        >
          <X className="h-4 w-4" />
        </SecondaryButton>
      )}
    </div>
  );
}

export function EventStaffCard({
  event,
  canEdit,
  showPoints,
  pointValues,
  hasDiscordServer = false,
}: EventStaffCardProps) {
  const queryClient = useQueryClient();
  const { setEventStaff } = useEventActionMutation(event.id);
  const server = useMemo<StaffState>(
    () => ({ host: event.host, helpers: event.helpers }),
    [event.host, event.helpers],
  );
  const serverKey = staffKey(server);
  const [pending, setPending] = useState<StaffState>(server);
  const [baseKey, setBaseKey] = useState(serverKey);
  const [picker, setPicker] = useState<PickerMode | null>(null);
  const [pickerSession, setPickerSession] = useState(0);
  const [draftConflict, setDraftConflict] = useState(false);

  if (baseKey !== serverKey) {
    const pendingKey = staffKey(pending);
    setBaseKey(serverKey);
    if (pendingKey === baseKey || pendingKey === serverKey) {
      setPending(server);
      setDraftConflict(false);
    } else {
      setDraftConflict(true);
    }
  }

  const openPicker = (mode: PickerMode): void => {
    setPickerSession((n) => n + 1);
    setPicker(mode);
  };

  const dirty = staffKey(pending) !== serverKey;
  const hostPoints = showPoints && pointValues ? pointValues.event_host : null;
  const helperPoints = showPoints && pointValues ? pointValues.event_helper : null;

  const resolveUser = (pk: number): EventStaffUser => {
    const known = [pending.host, ...pending.helpers, server.host, ...server.helpers].find(
      (u) => u?.pk === pk,
    );
    return (
      known ??
      findSearchedUser(queryClient, pk) ?? {
        pk,
        username: `User #${pk}`,
        nickname: null,
        avatarUrl: null,
      }
    );
  };

  const handlePick = async (payload: AddMemberPayload): Promise<UserType> => {
    if (payload.user_id == null) {
      throw new Error('Select a site user; Discord members without an account cannot be assigned.');
    }
    const user = resolveUser(payload.user_id);
    if (picker === 'host') {
      setPending((s) => ({ host: user, helpers: s.helpers.filter((h) => h.pk !== user.pk) }));
      setPicker(null);
    } else {
      setPending((s) => ({
        host: s.host?.pk === user.pk ? null : s.host,
        helpers: s.helpers.some((h) => h.pk === user.pk) ? s.helpers : [...s.helpers, user],
      }));
    }
    return { pk: user.pk, username: user.username, nickname: user.nickname } as UserType;
  };

  const isPicked = (user: UserType): boolean => {
    if (user.pk == null) return false;
    if (picker === 'host') return pending.host?.pk === user.pk;
    return pending.helpers.some((h) => h.pk === user.pk);
  };

  const discard = (): void => {
    setPending(server);
    setDraftConflict(false);
  };

  const save = async (): Promise<void> => {
    const payload = {
      host_id: pending.host?.pk ?? null,
      helper_ids: pending.helpers.map((h) => h.pk),
    };
    try {
      await setEventStaff.mutateAsync(payload);
      setDraftConflict(false);
      toast.success('Event staff saved');
    } catch (err: unknown) {
      logSaveFailure(event.id, err);
      toast.error(extractApiError(err) || 'Failed to save event staff');
    }
  };

  const empty = !pending.host && pending.helpers.length === 0;

  return (
    <Card data-testid="event-staff-card">
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <h3 className="font-semibold">Host &amp; Helpers</h3>
        {canEdit && (
          <div className="flex flex-wrap items-center gap-2">
            <SecondaryButton
              type="button"
              size="sm"
              onClick={() => openPicker('host')}
              data-testid="event-host-edit-btn"
            >
              <Crown className="h-4 w-4 mr-1.5" />
              {pending.host ? 'Change host' : 'Set host'}
            </SecondaryButton>
            <SecondaryButton
              type="button"
              size="sm"
              onClick={() => openPicker('helper')}
              data-testid="event-helper-add-btn"
            >
              <UserPlus className="h-4 w-4 mr-1.5" />
              Add helper
            </SecondaryButton>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-1">
        {empty && <p className="text-sm text-muted-foreground">No host or helpers assigned.</p>}
        {pending.host && (
          <StaffRow
            user={pending.host}
            role="Host"
            points={hostPoints}
            onRemove={canEdit ? () => setPending((s) => ({ ...s, host: null })) : undefined}
            removeTestId="event-host-remove-btn"
          />
        )}
        {pending.helpers.map((helper) => (
          <StaffRow
            key={helper.pk}
            user={helper}
            role="Helper"
            points={helperPoints}
            onRemove={
              canEdit
                ? () =>
                    setPending((s) => ({
                      ...s,
                      helpers: s.helpers.filter((h) => h.pk !== helper.pk),
                    }))
                : undefined
            }
            removeTestId={`event-helper-remove-${helper.pk}`}
          />
        ))}
        {canEdit && dirty && draftConflict && (
          <p className="text-xs text-muted-foreground" data-testid="event-staff-conflict-note">
            Host or helpers were changed elsewhere. Saving replaces those changes; Discard loads them.
          </p>
        )}
        {canEdit && dirty && (
          <div className="flex justify-end gap-2 pt-2">
            <SecondaryButton
              type="button"
              size="sm"
              onClick={discard}
              disabled={setEventStaff.isPending}
              data-testid="event-staff-reset-btn"
            >
              Discard
            </SecondaryButton>
            <PrimaryButton
              type="button"
              size="sm"
              onClick={() => void save()}
              disabled={setEventStaff.isPending}
              data-testid="event-staff-save-btn"
            >
              Save
            </PrimaryButton>
          </div>
        )}
      </CardContent>
      {canEdit && (
        <AddUserModal
          key={pickerSession}
          open={picker !== null}
          onOpenChange={(open) => {
            if (!open) setPicker(null);
          }}
          title={picker === 'host' ? 'Choose Event Host' : 'Add Event Helper'}
          entityContext={{ orgId: event.organization }}
          onAdd={handlePick}
          isAdded={isPicked}
          hasDiscordServer={hasDiscordServer}
        />
      )}
    </Card>
  );
}

export interface EventStaffSectionProps {
  event: EventType;
  access: OrgFeatureAccess;
  hasDiscordServer: boolean;
}

export function EventStaffSection({ event, access, hasDiscordServer }: EventStaffSectionProps) {
  const canEdit = event.user_can_manage_event_staff && access.settled;
  const showPoints = access.settled && access.canManageContributions;
  const { data: rows } = usePointValues(event.organization, access);
  const pointValues = useMemo<StaffPointValues | undefined>(() => {
    if (!rows) return undefined;
    const byKind = new Map(rows.map((r) => [r.kind, r.points]));
    const host = byKind.get('event_host');
    const helper = byKind.get('event_helper');
    return host !== undefined && helper !== undefined
      ? { event_host: host, event_helper: helper }
      : undefined;
  }, [rows]);

  if (!canEdit && !event.host && event.helpers.length === 0) return null;

  return (
    <EventStaffCard
      event={event}
      canEdit={canEdit}
      showPoints={showPoints}
      pointValues={pointValues}
      hasDiscordServer={hasDiscordServer}
    />
  );
}
