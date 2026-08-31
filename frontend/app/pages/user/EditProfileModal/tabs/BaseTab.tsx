import { useMutation, useQueryClient } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import {
  patchBaseProfile,
  type BasePatchPayload,
} from '~/components/api/userProfileApi';
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
import { UserAvatar } from '~/components/user/UserAvatar';
import { getLogger } from '~/lib/logger';
import { Sentry } from '~/lib/sentry';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserProfileStore } from '~/store/userProfileStore';
import type { UserProfileEntry } from '~/store/userProfileTypes';
import { useUserStore } from '~/store/userStore';

import {
  BaseProfileFormSchema,
  type BaseProfileFormValues,
} from '../schemas';

const log = getLogger('user.editProfile.base');

interface BaseTabProps {
  profile: UserProfileEntry;
  onSave?: () => void;
  onClose: () => void;
}

export default function BaseTab({ profile, onSave, onClose }: BaseTabProps) {
  const queryClient = useQueryClient();

  const form = useForm<BaseProfileFormValues>({
    resolver: zodResolver(BaseProfileFormSchema),
    defaultValues: {
      nickname: profile.base.nickname ?? '',
    },
  });

  const mutation = useMutation({
    mutationFn: (patch: BasePatchPayload) => patchBaseProfile(patch),
    onSuccess: (updated) => {
      // userCacheStore: spread existing entry through the adapter's
      // upsert(), which preserves orgData/leagueData and runs its own
      // change-detection. Skip if the user isn't cached yet — the query
      // invalidation below covers that case.
      const existing = useUserCacheStore.getState().getById(profile.pk);
      if (existing) {
        useUserCacheStore.getState().upsert({ ...existing, ...updated });
      }

      // userProfileStore: same idea via its upsert() — built-in
      // hasChanged() short-circuits no-op writes.
      const currentProfile = useUserProfileStore.getState().entities[profile.pk];
      if (currentProfile) {
        useUserProfileStore.getState().upsert({
          ...currentProfile,
          base: { ...currentProfile.base, ...updated },
          _fetchedAt: Date.now(),
        });
      }

      // Navbar/header read nickname off currentUser, so patch it if the
      // edited row is the logged-in user.
      if (useUserStore.getState().currentUser?.pk === profile.pk) {
        useUserStore.getState().patchCurrentUser(updated);
      }

      queryClient.invalidateQueries({ queryKey: ['userProfile', profile.pk] });
      // The profile-page header (UserProfilePage) reads the ['user', pk] query
      // (fetchUser), a DIFFERENT key — invalidate it too or the header keeps the
      // stale nickname until a manual refresh. (Pre-existing key mismatch; the
      // 06-profile-edit acceptance spec asserts the header updates without reload.)
      queryClient.invalidateQueries({ queryKey: ['user', profile.pk] });

      log.debug('base_patch_success', { userPk: profile.pk, updated });
      toast.success('Profile updated');
      onSave?.();
      onClose();
    },
    onError: (err) => {
      log.error('base_patch_failed', { userPk: profile.pk, error: String(err) });
      Sentry.captureException(err, {
        tags: { system: 'users', subsystem: 'profile' },
        extra: { userPk: profile.pk },
      });
      toast.error('Failed to update profile');
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    // Only send dirty fields — dirtyFields semantics per react-hook-form.
    const { dirtyFields } = form.formState;
    const payload: BasePatchPayload = {};
    if (dirtyFields.nickname) {
      payload.nickname = values.nickname ?? null;
    }
    if (Object.keys(payload).length === 0) {
      onClose();
      return;
    }
    mutation.mutate(payload);
  });

  const watchedNickname = form.watch('nickname');

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        {/* Avatar is Discord-synced (avatar-hash, not URL) and not user-editable.
            Showing the current avatar here as a read-only display so the user
            can confirm their identity in the modal. */}
        <div className="flex items-center gap-4">
          <UserAvatar
            user={{
              pk: profile.pk,
              nickname: watchedNickname ?? null,
              avatar: profile.base.avatar ?? null,
            }}
            size="lg"
          />
          <p className="text-sm text-base-content/70">
            Avatar is synced from Discord automatically.
          </p>
        </div>

        <FormField
          control={form.control}
          name="nickname"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Nickname</FormLabel>
              <FormControl>
                <Input
                  placeholder="Enter your nickname"
                  data-testid="edit-user-nickname"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription>Display name shown on your profile</FormDescription>
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
            data-testid="edit-user-save"
          >
            Save Changes
          </SubmitButton>
        </div>
      </form>
    </Form>
  );
}
