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

  return (
    <Tabs defaultValue="base">
      <TabsList>
        <TabsTrigger value="base" data-testid="edit-user-tab-base">
          Base
        </TabsTrigger>
        {/* T2 adds: <TabsTrigger value="dota">Dota</TabsTrigger> etc. */}
      </TabsList>
      <TabsContent value="base">
        <Suspense fallback={<ProfileSkeleton />}>
          <BaseTab profile={data} onSave={onSave} onClose={onClose} />
        </Suspense>
      </TabsContent>
    </Tabs>
  );
}
