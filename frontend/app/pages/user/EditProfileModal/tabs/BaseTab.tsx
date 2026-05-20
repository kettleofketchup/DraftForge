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
import { EditButton } from '~/components/ui/buttons/EditButton';
import { SubmitButton } from '~/components/ui/buttons/SubmitButton';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { UserType } from '~/components/user/types';
import { Sentry } from '~/lib/sentry';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserProfileStore } from '~/store/userProfileStore';
import type { UserProfileEntry } from '~/store/userProfileTypes';
import { useUserStore } from '~/store/userStore';

import {
  BaseProfileFormSchema,
  type BaseProfileFormValues,
} from '../schemas';

const log = {
  debug: (...args: unknown[]) => console.debug('[user.editProfile.base]', ...args),
  warn: (...args: unknown[]) => console.warn('[user.editProfile.base]', ...args),
  error: (...args: unknown[]) => console.error('[user.editProfile.base]', ...args),
};

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
      avatar: profile.base.avatar ?? '',
    },
  });

  const mutation = useMutation({
    mutationFn: (patch: BasePatchPayload) => patchBaseProfile(patch),
    onSuccess: (updated) => {
      // 1. Dual-write to userCacheStore so UserCard / user lists refresh in
      //    the same microtask. upsert() requires a UserType with username,
      //    so we spread the existing UserEntry (which UserCard et al
      //    populated). If no entry exists yet (rare — user is editing their
      //    own profile, so typically loaded), skip the cache write — the
      //    invalidateQueries below + the userProfileStore mirror keep the
      //    UI consistent on the next read.
      const existing = useUserCacheStore.getState().getById(profile.pk);
      if (existing) {
        const merged: UserType = {
          ...existing,
          pk: profile.pk,
          nickname:
            updated.nickname !== undefined ? updated.nickname : existing.nickname,
          avatar:
            updated.avatar !== undefined ? updated.avatar : existing.avatar,
        };
        useUserCacheStore.getState().upsert(merged);
      }

      // 2. Refresh userStore.currentUser if the edited row is the logged-in
      //    user. Navbar, profile-page header, and other components read
      //    avatar/nickname directly off currentUser, so a stale value here
      //    leaves the post-PATCH UI inconsistent until a page reload or
      //    fetchCurrentUser() call. Merge the patched fields onto the
      //    existing currentUser snapshot.
      const currentUserState = useUserStore.getState().currentUser;
      if (currentUserState?.pk === profile.pk) {
        useUserStore.getState().setCurrentUser({
          ...currentUserState,
          nickname:
            updated.nickname !== undefined
              ? updated.nickname
              : currentUserState.nickname,
          avatar:
            updated.avatar !== undefined
              ? updated.avatar
              : currentUserState.avatar,
        } as UserType);
      }

      // 3. Mark the profile query stale so the next read refetches.
      queryClient.invalidateQueries({ queryKey: ['userProfile', profile.pk] });

      // 4. Mirror the change into the profile store immediately for any
      //    consumers reading via the adapter rather than the query.
      useUserProfileStore.setState((state) => {
        const current = state.entities[profile.pk];
        if (!current) return state;
        return {
          entities: {
            ...state.entities,
            [profile.pk]: {
              ...current,
              base: { ...current.base, ...updated },
              _fetchedAt: Date.now(),
            },
          },
        };
      });

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
    if (dirtyFields.avatar) {
      payload.avatar = values.avatar ?? null;
    }
    if (Object.keys(payload).length === 0) {
      onClose();
      return;
    }
    mutation.mutate(payload);
  });

  const watchedAvatar = form.watch('avatar');
  const watchedNickname = form.watch('nickname');

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="flex items-center gap-4">
          <UserAvatar
            user={{
              pk: profile.pk,
              nickname: watchedNickname ?? null,
              avatar: watchedAvatar ?? null,
            }}
            size="lg"
          />
          <EditButton
            type="button"
            onClick={() => document.getElementById('avatar-input')?.focus()}
            data-testid="edit-user-avatar-trigger"
          >
            Change avatar
          </EditButton>
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

        <FormField
          control={form.control}
          name="avatar"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Avatar URL</FormLabel>
              <FormControl>
                <Input
                  id="avatar-input"
                  placeholder="https://example.com/avatar.png"
                  data-testid="edit-user-avatar"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
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
