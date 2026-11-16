import { CancelButton } from '~/components/ui/buttons/CancelButton';
import { UserAvatar } from '~/components/user/UserAvatar';
import { resolveDisplayName } from '~/lib/userDisplayName';
import { useUserCacheStore } from '~/store/userCacheStore';
import type { UserProfileEntry } from '~/store/userProfileTypes';
import { useUserStore } from '~/store/userStore';

interface BaseTabProps {
  profile: UserProfileEntry;
  onSave?: () => void;
  onClose: () => void;
}

export default function BaseTab({ profile, onClose }: BaseTabProps) {
  const currentUser = useUserStore((s) => s.currentUser);
  const cached = useUserCacheStore((s) => s.entities[profile.pk]);
  const src = currentUser?.pk === profile.pk ? currentUser : cached;
  const name = resolveDisplayName(src ?? { pk: profile.pk }, { orgId: null });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-4">
        <UserAvatar
          user={{
            pk: profile.pk,
            username: src?.username ?? null,
            avatar: profile.base.avatar ?? null,
          }}
          size="lg"
        />
        <div className="flex flex-col gap-1">
          <p className="text-sm text-muted-foreground">Discord name</p>
          <p className="font-medium" data-testid="profile-discord-name">
            {name}
          </p>
          <p className="text-sm text-muted-foreground">
            Synced from Discord. Change your name in Discord.
          </p>
        </div>
      </div>

      <div className="flex justify-end pt-4">
        <CancelButton type="button" onClick={onClose}>
          Close
        </CancelButton>
      </div>
    </div>
  );
}
