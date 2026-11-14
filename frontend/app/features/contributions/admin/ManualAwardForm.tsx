import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import { SecondaryButton, SubmitButton } from '~/components/ui/buttons';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Textarea } from '~/components/ui/textarea';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { useCreateManualAward, useUpdateManualAward } from '../queries';
import {
  MANUAL_MAX_POINTS,
  REASON_MAX_LENGTH,
  manualAwardSchema,
  type AdminEntry,
  type ManualAwardInput,
} from '../schemas';
import { dateInZone, todayInZone } from '../timezone';

const log = getLogger('ManualAwardForm');

const NO_EVENT = 'none';

export interface AwardMember {
  pk: number;
  username: string;
  nickname?: string | null;
}

export interface AwardEvent {
  id: number;
  name: string;
}

export interface ManualAwardFormProps {
  orgId: number;
  access: OrgFeatureAccess;
  timeZone: string | undefined;
  members: AwardMember[];
  events: AwardEvent[];
  /** Edit this manual entry instead of creating a new award. */
  entry?: AdminEntry;
  onDone?: () => void;
}

function memberName(member: AwardMember): string {
  return member.nickname || member.username;
}

function numberOrNaN(value: string): number {
  return value === '' ? Number.NaN : Number(value);
}

export function ManualAwardForm({
  orgId,
  access,
  timeZone,
  members,
  events,
  entry,
  onDone,
}: ManualAwardFormProps) {
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
    const payload: ManualAwardInput = { ...values, event_id: values.event_id ?? null };
    try {
      if (entry) {
        const { user_id: _userId, ...changes } = payload;
        await update.mutateAsync({ entryPk: entry.pk, changes });
        toast.success('Award updated');
      } else {
        await create.mutateAsync(payload);
        toast.success('Points awarded');
        form.reset({ ...defaults(), date: values.date });
      }
      onDone?.();
    } catch (err) {
      log.warn('Failed to save manual award', { orgId, entryPk: entry?.pk, err });
      toast.error(extractApiError(err) ?? 'Failed to save award');
    }
  };

  const linkedEventMissing =
    entry?.event != null && !events.some((e) => e.id === entry.event?.id);
  const eventOptions = linkedEventMissing && entry?.event ? [entry.event, ...events] : events;

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
            Member: <span className="font-medium">{entry.member.nickname || entry.member.username}</span>
          </p>
        ) : (
          <FormField
            control={form.control}
            name="user_id"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Member</FormLabel>
                <BrandSelect
                  value={field.value ? String(field.value) : ''}
                  onValueChange={(v) => field.onChange(Number(v))}
                  disabled={pending}
                >
                  <FormControl>
                    <BrandSelectTrigger data-testid="manual-award-member" aria-label="Member">
                      <SelectValue placeholder="Choose a member" />
                    </BrandSelectTrigger>
                  </FormControl>
                  <BrandSelectContent>
                    {members.map((m) => (
                      <BrandSelectItem
                        key={m.pk}
                        value={String(m.pk)}
                        data-testid={`manual-award-member-${m.pk}`}
                      >
                        {memberName(m)}
                      </BrandSelectItem>
                    ))}
                  </BrandSelectContent>
                </BrandSelect>
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
                    onChange={(e) => field.onChange(numberOrNaN(e.target.value))}
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
                onValueChange={(v) => field.onChange(v === NO_EVENT ? null : Number(v))}
                disabled={pending}
              >
                <FormControl>
                  <BrandSelectTrigger data-testid={`${prefix}-event`} aria-label="Event">
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
                      {e.name}
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
    </Form>
  );
}
