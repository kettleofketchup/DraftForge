import { lazy, Suspense, useEffect } from 'react';
import { ErrorBoundary } from 'react-error-boundary';
import { useSuspenseQuery } from '@tanstack/react-query';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { ScrollArea } from '~/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { getUserProfile } from '~/components/api/userProfileApi';
import { useUserProfileStore } from '~/store/userProfileStore';

import { ProfileSkeleton } from './EditProfileModal/ProfileSkeleton';
import { ProfileErrorFallback } from './EditProfileModal/ProfileErrorFallback';

const BaseTab = lazy(() => import('./EditProfileModal/tabs/BaseTab'));
const DotaTab = lazy(() => import('./EditProfileModal/tabs/DotaTab'));
const DeadlockTab = lazy(() => import('./EditProfileModal/tabs/DeadlockTab'));

interface EditProfileModalProps {
  userPk: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave?: () => void;
}

export function EditProfileModal({
  userPk,
  open,
  onOpenChange,
  onSave,
}: EditProfileModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* ScrollArea contract for dialog body — DialogContent needs
          overflow-hidden (NOT overflow-y-auto) so Radix Viewport can
          drive its themed scrollbar inside <ScrollArea>. T1 body is
          short today (one nickname field) but the contract is in place
          now so T2/T3's Dota/Org tabs don't break it later. Ref:
          docs/theming-guide/ai/references/scrollbars-dialogs.md */}
      <DialogContent className="flex max-h-[90vh] flex-col overflow-hidden sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit Profile</DialogTitle>
          <DialogDescription>Update your profile information</DialogDescription>
        </DialogHeader>

        <ScrollArea className="-mx-6 min-h-0 flex-1 px-6">
          <div className="pb-4">
            <ErrorBoundary FallbackComponent={ProfileErrorFallback}>
              <Suspense fallback={<ProfileSkeleton />}>
                <EditProfileModalBody
                  userPk={userPk}
                  onSave={onSave}
                  onClose={() => onOpenChange(false)}
                />
              </Suspense>
            </ErrorBoundary>
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}

function EditProfileModalBody({
  userPk,
  onSave,
  onClose,
}: {
  userPk: number;
  onSave?: () => void;
  onClose: () => void;
}) {
  const { data } = useSuspenseQuery({
    queryKey: ['userProfile', userPk],
    queryFn: () => getUserProfile(userPk),
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });

  // Write-through to Zustand — NOT inside select (select must be pure).
  useEffect(() => {
    useUserProfileStore.getState().upsert(data);
  }, [data]);

  // Tabs invalidate ['userProfile', profile.pk] while this query is keyed by
  // userPk; they match only because getUserProfile ignores its arg (/me/) and
  // the modal mounts self-only. Surface a future non-self mount's latent
  // invalidate-miss instead of failing silently.
  if (import.meta.env.DEV && data.pk !== userPk) {
    console.warn('userProfile key/pk mismatch', { userPk, dataPk: data.pk });
  }

  return (
    <Tabs defaultValue="base">
      <TabsList>
        <TabsTrigger value="base" data-testid="edit-user-tab-base">
          Base
        </TabsTrigger>
        <TabsTrigger value="dota" data-testid="edit-user-tab-dota">
          Dota
        </TabsTrigger>
        <TabsTrigger value="deadlock" data-testid="edit-user-tab-deadlock">
          Deadlock
        </TabsTrigger>
      </TabsList>
      <TabsContent value="base">
        <Suspense fallback={<ProfileSkeleton />}>
          <BaseTab profile={data} onSave={onSave} onClose={onClose} />
        </Suspense>
      </TabsContent>
      <TabsContent value="dota">
        <Suspense fallback={<ProfileSkeleton />}>
          <DotaTab profile={data} onSave={onSave} onClose={onClose} />
        </Suspense>
      </TabsContent>
      <TabsContent value="deadlock">
        <Suspense fallback={<ProfileSkeleton />}>
          <DeadlockTab profile={data} onSave={onSave} onClose={onClose} />
        </Suspense>
      </TabsContent>
    </Tabs>
  );
}
