import { useMutation, useQueryClient } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import type { z } from 'zod';

import { patchGameProfile } from '~/components/api/userProfileApi';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { CancelButton } from '~/components/ui/buttons/CancelButton';
import { SubmitButton } from '~/components/ui/buttons/SubmitButton';
import { getLogger } from '~/lib/logger';
import { Sentry } from '~/lib/sentry';
import { useUserProfileStore } from '~/store/userProfileStore';
import type { UserProfileEntry } from '~/store/userProfileTypes';

import {
  DeadlockProfileFormSchema,
  type DeadlockProfileFormValues,
} from '../schemas';

const log = getLogger('user.editProfile.deadlock');

interface DeadlockTabProps {
  profile: UserProfileEntry;
  onSave?: () => void;
  onClose: () => void;
}

export default function DeadlockTab({ profile, onSave, onClose }: DeadlockTabProps) {
  const queryClient = useQueryClient();

  const deadlock = profile.gameUser.deadlock;
  const form = useForm<
    z.input<typeof DeadlockProfileFormSchema>,
    unknown,
    DeadlockProfileFormValues
  >({
    resolver: zodResolver(DeadlockProfileFormSchema),
    defaultValues: {
      rank: deadlock?.rank ?? '',
      rank_date: deadlock?.rank_date ?? '',
    },
  });

  const mutation = useMutation({
    mutationFn: (vals: DeadlockProfileFormValues) =>
      patchGameProfile('deadlock', vals),
    onSuccess: (updated) => {
      // Edit layer — base on the `profile` prop (always full), NOT a
      // getState() lookup that can be undefined. No userCacheStore write:
      // deadlock rank is not a flat _users[] list-display field.
      useUserProfileStore.getState().upsert({
        ...profile,
        gameUser: {
          ...profile.gameUser,
          deadlock: { ...profile.gameUser?.deadlock, ...updated },
        },
        _fetchedAt: Date.now(),
      });

      queryClient.invalidateQueries({ queryKey: ['userProfile', profile.pk] });

      log.debug('deadlock_patch_success', { userPk: profile.pk, updated });
      toast.success('Deadlock profile updated');
      onSave?.();
      onClose();
    },
    onError: (err) => {
      log.error('deadlock_patch_failed', {
        userPk: profile.pk,
        error: String(err),
      });
      Sentry.captureException(err, {
        tags: { system: 'users', subsystem: 'profile' },
        extra: { userPk: profile.pk },
      });
      toast.error('Failed to update Deadlock profile');
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    // rank_date is a Django DateField — it rejects "" (the empty <input
    // type=date> value). Coerce empty → null so saving without a date works.
    mutation.mutate({ ...values, rank_date: values.rank_date || null });
  });

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <FormField
          control={form.control}
          name="rank"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Rank</FormLabel>
              <FormControl>
                <Input
                  placeholder="e.g. Archon"
                  data-testid="edit-user-deadlock-rank"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription>Your current Deadlock rank</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="rank_date"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Rank Date</FormLabel>
              <FormControl>
                <Input
                  type="date"
                  data-testid="edit-user-deadlock-rank-date"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription>When this rank was recorded</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex justify-end gap-2 pt-4">
          <CancelButton type="button" onClick={onClose}>
            Cancel
          </CancelButton>
          <SubmitButton
            loading={mutation.isPending}
            loadingText="Saving..."
            data-testid="edit-user-deadlock-save"
          >
            Save Changes
          </SubmitButton>
        </div>
      </form>
    </Form>
  );
}
