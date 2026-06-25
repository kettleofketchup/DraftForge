import { useMutation, useQueryClient } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import type { z } from 'zod';

import { patchGameProfile } from '~/components/api/userProfileApi';
import { Form } from '~/components/ui/form';
import { CancelButton } from '~/components/ui/buttons/CancelButton';
import { SubmitButton } from '~/components/ui/buttons/SubmitButton';
import { PositionFormFields } from '~/pages/profile/forms/position';
import { getLogger } from '~/lib/logger';
import { Sentry } from '~/lib/sentry';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserProfileStore } from '~/store/userProfileStore';
import type { UserProfileEntry } from '~/store/userProfileTypes';

import {
  DotaProfileFormSchema,
  type DotaProfileFormValues,
} from '../schemas';

const log = getLogger('user.editProfile.dota');

interface DotaTabProps {
  profile: UserProfileEntry;
  onSave?: () => void;
  onClose: () => void;
}

export default function DotaTab({ profile, onSave, onClose }: DotaTabProps) {
  const queryClient = useQueryClient();

  const positions = profile.gameUser.dota?.positions;
  const form = useForm<
    z.input<typeof DotaProfileFormSchema>,
    unknown,
    DotaProfileFormValues
  >({
    resolver: zodResolver(DotaProfileFormSchema),
    defaultValues: {
      positions: {
        carry: positions?.carry ?? 0,
        mid: positions?.mid ?? 0,
        offlane: positions?.offlane ?? 0,
        soft_support: positions?.soft_support ?? 0,
        hard_support: positions?.hard_support ?? 0,
      },
    },
  });

  const mutation = useMutation({
    mutationFn: (vals: DotaProfileFormValues) => patchGameProfile('dota', vals),
    onSuccess: (updated) => {
      // 1. list/display source — every roster/card/table reading positions off
      // userCacheStore updates immediately (onClose unmounts before any refetch).
      // Spread the existing entry so the adapter's upsert() preserves the rest of
      // the user; skip if not cached (the invalidation below covers that case).
      const cached = useUserCacheStore.getState().getById(profile.pk);
      if (cached && updated.positions) {
        useUserCacheStore
          .getState()
          .upsert({ ...cached, pk: profile.pk, positions: updated.positions });
      }

      // 2. edit layer — base on the `profile` prop (always full), NOT a
      // getState() lookup that can be undefined.
      useUserProfileStore.getState().upsert({
        ...profile,
        gameUser: {
          ...profile.gameUser,
          dota: { ...profile.gameUser?.dota, positions: updated.positions },
        },
        _fetchedAt: Date.now(),
      });

      // 3. refetch-on-next-mount. Invalidate BOTH keys: the modal reads
      // ['userProfile', pk]; UserProfilePage's Overview renders <RolePositions>
      // off the ['user', pk] query (fetchUser) — without this, the profile
      // positions badge stays stale until a manual refresh (same fix BaseTab
      // applies for the nickname header).
      queryClient.invalidateQueries({ queryKey: ['userProfile', profile.pk] });
      queryClient.invalidateQueries({ queryKey: ['user', profile.pk] });

      log.debug('dota_patch_success', { userPk: profile.pk, updated });
      toast.success('Dota profile updated');
      onSave?.();
      onClose();
    },
    onError: (err) => {
      log.error('dota_patch_failed', { userPk: profile.pk, error: String(err) });
      Sentry.captureException(err, {
        tags: { system: 'users', subsystem: 'profile' },
        extra: { userPk: profile.pk },
      });
      toast.error('Failed to update Dota profile');
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    mutation.mutate(values);
  });

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <PositionFormFields form={form} />

        <div className="flex justify-end gap-2 pt-4">
          <CancelButton type="button" onClick={onClose}>
            Cancel
          </CancelButton>
          <SubmitButton
            loading={mutation.isPending}
            loadingText="Saving..."
            data-testid="edit-user-dota-save"
          >
            Save Changes
          </SubmitButton>
        </div>
      </form>
    </Form>
  );
}
