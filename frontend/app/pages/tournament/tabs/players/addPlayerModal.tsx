import type { FormEvent } from 'react';
import React, { useState, useEffect } from 'react';
import type { UserType } from '~/components/user/types';

import { PlusIconButton } from '~/components/ui/buttons';
import { FormDialog } from '~/components/ui/dialogs';
import UserCreateModal from '~/components/user/userCard/createModal';
import { useOrgUsers } from '~/hooks/useOrgUsers';
import { useResolvedUsers } from '~/hooks/useResolvedUsers';
import { useOrgStore } from '~/store/orgStore';
import { useUserStore } from '~/store/userStore';
import { AddPlayerDropdown } from './addPlayerDropdown';

import { AdminOnlyButton } from '~/components/reusable/adminButton';
import { getLogger } from '~/lib/logger';

const log = getLogger('addPlayerModal');

interface Props {
  users: UserType[];
  addedUsers?: UserType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  addPlayerCallback?: (user: UserType) => Promise<void>;
  removePlayerCallback?: (e: FormEvent, user: UserType) => Promise<void>;
  orgId?: number;
}

export const AddPlayerModal: React.FC<Props> = ({
  addedUsers,
  addPlayerCallback,
  removePlayerCallback,
  query,
  setQuery,
  orgId,
}) => {
  const [open, setOpen] = useState(false);
  const currentUser = useUserStore((state) => state.currentUser);
  const isStaff = useUserStore((state) => state.isStaff);

  // Global users fallback (resolved from cache)
  const globalUserPks = useUserStore((state) => state.globalUserPks);
  const globalUsers = useResolvedUsers(globalUserPks);
  const getUsers = useUserStore((state) => state.getUsers);

  // Org-specific users resolved from cache
  const orgUsers = useOrgUsers(orgId ?? 0);
  const getOrgUsers = useOrgStore((state) => state.getOrgUsers);
  const orgUsersLoading = useOrgStore((state) => state.orgUsersLoading);

  // Determine which users to show
  const users = orgId ? orgUsers : globalUsers;

  // Lazy load users when modal opens
  useEffect(() => {
    if (open) {
      if (orgId) {
        // Load org-specific users
        getOrgUsers(orgId);
      } else if (globalUserPks.length === 0) {
        // Fallback to global users
        getUsers();
      }
    }
  }, [open, orgId, globalUserPks.length, getOrgUsers, getUsers]);

  if (!isStaff()) {
    return (
      <AdminOnlyButton
        buttonTxt=""
        tooltipTxt={'Only Admins can add users to the tournament'}
      />
    );
  }

  return (
    <>
      <PlusIconButton
        tooltip="Add users to the tournament"
        data-testid="tournamentAddPlayerBtn"
        onClick={() => setOpen(true)}
      />

      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title="Add Users to Tournament"
        description={
          orgId
            ? 'Search for organization members to add to the tournament.'
            : 'Search for a user to add to the tournament. You can search by name or username.'
        }
        submitLabel="Done"
        isSubmitting={false}
        onSubmit={() => {
          setOpen(false);
        }}
        size="md"
        showFooter={false}
      >
        <div className="flex flex-col justify-start align-start items-start content-start w-full gap-4 mb-4">
          <div className="justify-self-start self-start w-full">
            {orgUsersLoading && orgId ? (
              <div className="text-sm text-gray-500">
                Loading organization members...
              </div>
            ) : (
              <AddPlayerDropdown
                users={users}
                query={query}
                setQuery={setQuery}
                addPlayerCallback={addPlayerCallback}
                removePlayerCallback={removePlayerCallback}
                addedUsers={addedUsers}
                placeholder={
                  orgId
                    ? 'Search organization members...'
                    : 'Search all users...'
                }
              />
            )}
          </div>
        </div>
        <div className="flex flex-row gap-x-4 sm:gap-x-8 justify-center align-center items-center w-full">
          <UserCreateModal query={query} setQuery={setQuery} />
        </div>
      </FormDialog>
    </>
  );
};
