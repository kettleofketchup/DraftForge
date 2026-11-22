import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { ChevronDown } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import type { AddMemberPayload } from '~/components/api/api';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import { SecondaryButton, SubmitButton } from '~/components/ui/buttons';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Textarea } from '~/components/ui/textarea';
import {
  AddUserModal,
  findSearchedUser,
  type SearchedUser,
} from '~/components/user/AddUserModal';
import { DisplayName } from '~/components/user/avatar';
import type { UserType } from '~/components/user/types';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { useOrgStore } from '~/store/orgStore';
import { useCreateManualAward, useUpdateManualAward } from '../queries';
import {
  MANUAL_MAX_POINTS,
  REASON_MAX_LENGTH,
  manualAwardSchema,
  type AdminEntry,
  type ManualAwardInput,
} from '../schemas';
import { dateInZone, formatOrgDate, todayInZone } from '../timezone';

const log = getLogger('ManualAwardForm');

const NO_EVENT = 'none';

export interface AwardEvent {
  id: number;
  name: string;
  scheduled_at?: string;
}

export interface ManualAwardFormProps {
  orgId: number;
  access: OrgFeatureAccess;
  timeZone: string | undefined;
  events: AwardEvent[];
  /** Edit this manual entry instead of creating a new award. */
  entry?: AdminEntry;
  onDone?: () => void;
}

function eventLabel(event: AwardEvent, timeZone: string | undefined): string {
  return event.scheduled_at
    ? `${event.name} · ${formatOrgDate(event.scheduled_at, timeZone)}`
    : event.name;
}

function numberOrNaN(value: string): number {
  return value === '' ? Number.NaN : Number(value);
}

export function ManualAwardForm({
  orgId,
  access,
  timeZone,
  events,
  entry,
  onDone,
}: ManualAwardFormProps) {
  const queryClient = useQueryClient();
  const hasDiscordServer = useOrgStore(
    (s) =>
      s.currentOrg?.pk === orgId && Boolean(s.currentOrg.discord_server_id),
  );
  const [member, setMember] = useState<SearchedUser | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerSession, setPickerSession] = useState(0);
  const create = useCreateManualAward(orgId, access);
  const update = useUpdateManualAward(orgId, access);
  const isEdit = entry != null;
  const prefix = isEdit ? `manual-award-edit` : 'manual-award';
  const pending = create.isPending || update.isPending;

  const defaults = (): ManualAwardInput =>
    entry
      ? {
          user_id: entry.member.user_pk,
          points: entry.points,
          reason: entry.reason,
          date: dateInZone(entry.occurred_at, timeZone),
          event_id: entry.event?.id ?? null,
        }
      : {
          user_id: 0,
          points: Number.NaN,
          reason: '',
          date: todayInZone(timeZone),
          event_id: null,
        };

  const form = useForm<ManualAwardInput>({
    resolver: zodResolver(manualAwardSchema),
    defaultValues: defaults(),
  });

  const onSubmit = async (values: ManualAwardInput): Promise<void> => {
    const payload: ManualAwardInput = {
      ...values,
      event_id: values.event_id ?? null,
    };
    try {
      if (entry) {
        const { user_id: _userId, ...changes } = payload;
        await update.mutateAsync({ entryPk: entry.pk, changes });
        toast.success('Award updated');
      } else {
        await create.mutateAsync(payload);
        toast.success('Points awarded');
        form.reset({ ...defaults(), date: values.date });
        setMember(null);
      }
      onDone?.();
    } catch (err) {
      log.warn('Failed to save manual award', {
        orgId,
        entryPk: entry?.pk,
        err,
      });
      toast.error(extractApiError(err) ?? 'Failed to save award');
    }
  };

  const pickMember = async (payload: AddMemberPayload): Promise<UserType> => {
    if (payload.user_id == null) {
      throw new Error(
        'This Discord member has no DraftForge account yet, so they cannot be awarded points.',
      );
    }
    const picked = findSearchedUser(queryClient, payload.user_id) ?? {
      pk: payload.user_id,
      username: `User #${payload.user_id}`,
      nickname: null,
      avatarUrl: null,
    };
    setMember(picked);
    form.setValue('user_id', picked.pk, {
      shouldDirty: true,
      shouldValidate: true,
    });
    setPickerOpen(false);
    return {
      pk: picked.pk,
      username: picked.username,
      nickname: picked.nickname,
    } as UserType;
  };

  const openPicker = (): void => {
    setPickerSession((n) => n + 1);
    setPickerOpen(true);
  };

  const linkedEventMissing =
    entry?.event != null && !events.some((e) => e.id === entry.event?.id);
  const eventOptions =
    linkedEventMissing && entry?.event ? [entry.event, ...events] : events;

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="flex flex-col gap-3"
        data-testid={`${prefix}-form`}
        noValidate
      >
        {isEdit ? (
          <p className="text-sm">
            Member:{' '}
            <span className="font-medium">{DisplayName(entry.member)}</span>
          </p>
        ) : (
          <FormField
            control={form.control}
            name="user_id"
            render={() => (
              <FormItem>
                <FormLabel>Member</FormLabel>
                <FormControl>
                  <SecondaryButton
                    type="button"
                    onClick={openPicker}
                    disabled={pending}
                    className="w-full justify-between sm:w-80"
                    data-testid="manual-award-member"
                    aria-label={
                      member
                        ? `Member: ${DisplayName(member)}`
                        : 'Choose a member'
                    }
                  >
                    {member ? (
                      <span className="flex min-w-0 items-center gap-2">
                        <UserAvatar user={member} size="xs" />
                        <span className="truncate">{DisplayName(member)}</span>
                      </span>
                    ) : (
                      <span className="text-muted-foreground">
                        Search for a member
                      </span>
                    )}
                    <ChevronDown className="size-4 opacity-60" aria-hidden />
                  </SecondaryButton>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="points"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Points</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={MANUAL_MAX_POINTS}
                    step={1}
                    name={field.name}
                    ref={field.ref}
                    onBlur={field.onBlur}
                    value={Number.isNaN(field.value) ? '' : field.value}
                    onChange={(e) =>
                      field.onChange(numberOrNaN(e.target.value))
                    }
                    disabled={pending}
                    data-testid={`${prefix}-points`}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="date"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Date (org timezone)</FormLabel>
                <FormControl>
                  <Input
                    type="date"
                    {...field}
                    disabled={pending}
                    data-testid={`${prefix}-date`}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="reason"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Reason</FormLabel>
              <FormControl>
                <Textarea
                  {...field}
                  rows={2}
                  maxLength={REASON_MAX_LENGTH}
                  disabled={pending}
                  data-testid={`${prefix}-reason`}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="event_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Event (optional)</FormLabel>
              <BrandSelect
                value={field.value ? String(field.value) : NO_EVENT}
                onValueChange={(v) =>
                  field.onChange(v === NO_EVENT ? null : Number(v))
                }
                disabled={pending}
              >
                <FormControl>
                  <BrandSelectTrigger
                    data-testid={`${prefix}-event`}
                    aria-label="Event"
                  >
                    <SelectValue />
                  </BrandSelectTrigger>
                </FormControl>
                <BrandSelectContent>
                  <BrandSelectItem value={NO_EVENT}>No event</BrandSelectItem>
                  {eventOptions.map((e) => (
                    <BrandSelectItem
                      key={e.id}
                      value={String(e.id)}
                      data-testid={`${prefix}-event-${e.id}`}
                    >
                      {eventLabel(e, timeZone)}
                    </BrandSelectItem>
                  ))}
                </BrandSelectContent>
              </BrandSelect>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex justify-end gap-2">
          {onDone && isEdit && (
            <SecondaryButton
              type="button"
              disabled={pending}
              onClick={onDone}
              data-testid={`${prefix}-cancel`}
            >
              Cancel
            </SecondaryButton>
          )}
          <SubmitButton loading={pending} data-testid={`${prefix}-submit`}>
            {isEdit ? 'Save award' : 'Award points'}
          </SubmitButton>
        </div>
      </form>
      {!isEdit && (
        <AddUserModal
          key={pickerSession}
          open={pickerOpen}
          onOpenChange={setPickerOpen}
          title="Choose member to award"
          entityContext={{ orgId }}
          onAdd={pickMember}
          isAdded={(user) => user.pk != null && user.pk === member?.pk}
          hasDiscordServer={hasDiscordServer}
        />
      )}
    </Form>
  );
}
