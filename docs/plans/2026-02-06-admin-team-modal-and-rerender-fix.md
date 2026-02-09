# Admin Team Modal + Rerender Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the inline `UserSearchInput` in `AdminTeamSection` with the richer `AddUserModal` component, and fix the organization rerender bug where admin/staff changes don't reflect on the org page after closing the edit modal.

**Architecture:** Two independent fixes. (1) Add a `force` parameter to `userStore.getOrganization()` to bypass the cache guard, then use it in the `useOrganization` refetch hook. (2) Refactor `AdminTeamSection` to use `AddUserModal` (with `hasDiscordServer={false}` since admins/staff must be existing site users) instead of the inline `UserSearchInput` dropdown.

**Tech Stack:** React, TypeScript, Zustand, TanStack Query, AddUserModal component

---

### Task 1: Fix organization rerender bug — add `force` param to `getOrganization`

**Files:**
- Modify: `frontend/app/store/userStore.ts:100,406-420`
- Modify: `frontend/app/components/organization/hooks/useOrganization.ts:9-15`

**Step 1: Update `getOrganization` type signature and implementation**

In `frontend/app/store/userStore.ts`, change the type at line 100:
```typescript
getOrganization: (pk: number, force?: boolean) => Promise<void>;
```

And change the implementation at line 406:
```typescript
getOrganization: async (pk: number, force = false) => {
  // Skip if already loaded for this pk (unless forced)
  if (!force && get().organizationPk === pk && get().organization) {
    log.debug('Organization already loaded:', pk);
    return;
  }
  try {
    const response = await fetchOrganization(pk);
    set({ organization: response, organizationPk: pk });
    log.debug('Organization fetched successfully:', response);
  } catch (error) {
    log.error('Error fetching organization:', error);
    set({ organization: null, organizationPk: null });
  }
},
```

**Step 2: Update `useOrganization` refetch to use force**

In `frontend/app/components/organization/hooks/useOrganization.ts`, simplify the refetch callback:
```typescript
const refetch = useCallback(() => {
  if (pk) {
    getOrganization(pk, true);
  }
}, [pk, getOrganization]);
```

This removes the race-condition-prone `setState({ organizationPk: null })` hack and uses the explicit `force` parameter.

**Step 3: Verify TypeScript compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/admin-team-modal && npx tsc --noEmit --pretty 2>&1 | grep -E "(error TS|getOrganization)" | head -20`
Expected: No new errors related to `getOrganization`.

**Step 4: Commit**

```bash
git add frontend/app/store/userStore.ts frontend/app/components/organization/hooks/useOrganization.ts
git commit -m "fix: add force parameter to getOrganization to fix stale data after admin changes"
```

---

### Task 2: Replace `UserSearchInput` with `AddUserModal` in `AdminTeamSection`

**Files:**
- Modify: `frontend/app/components/admin-team/AdminTeamSection.tsx`
- Delete import of: `UserSearchInput` (file can remain but won't be used by AdminTeamSection)

**Step 1: Rewrite `AdminTeamSection` to use `AddUserModal`**

Replace the full contents of `frontend/app/components/admin-team/AdminTeamSection.tsx` with:

```tsx
/**
 * Admin Team management section for organizations and leagues.
 * Provides UI for managing owner, admins, and staff.
 * Uses AddUserModal for searching and adding users.
 * Uses local state to avoid full page re-renders on updates.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Crown, Plus, Shield, User, X } from 'lucide-react';
import { toast } from 'sonner';
import type { UserType } from '~/components/user/types';
import type { OrganizationType } from '~/components/organization/schemas';
import type { LeagueType } from '~/components/league/schemas';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import type { AddMemberPayload } from '~/components/api/api';
import {
  addOrgAdmin,
  removeOrgAdmin,
  addOrgStaff,
  removeOrgStaff,
  transferOrgOwnership,
  addLeagueAdmin,
  removeLeagueAdmin,
  addLeagueStaff,
  removeLeagueStaff,
} from '~/components/api/api';
import {
  useIsOrganizationOwner,
  useIsOrganizationAdmin,
  useIsLeagueAdmin,
  useIsSuperuser,
} from '~/hooks/usePermissions';
import { AddUserModal } from '~/components/user/AddUserModal';
import { Button } from '~/components/ui/button';

interface AdminTeamSectionProps {
  organization?: OrganizationType | null;
  league?: LeagueType | null;
  onUpdate?: () => void;
}

interface UserRowProps {
  user: UserType;
  role: 'owner' | 'admin' | 'staff';
  canRemove: boolean;
  canTransfer?: boolean;
  onRemove?: () => void;
  onTransfer?: () => void;
  isRemoving?: boolean;
}

function UserRow({
  user,
  role,
  canRemove,
  canTransfer,
  onRemove,
  onTransfer,
  isRemoving,
}: UserRowProps) {
  const roleIcon = {
    owner: <Crown className="h-4 w-4 text-yellow-500" />,
    admin: <Shield className="h-4 w-4 text-blue-500" />,
    staff: <User className="h-4 w-4 text-gray-500" />,
  };

  // Uses reusable UserAvatar and DisplayName from ~/components/user/
  return (
    <div className="flex items-center justify-between py-2 px-3 bg-base-200 rounded-lg">
      <div className="flex items-center gap-3">
        {roleIcon[role]}
        <UserAvatar user={user} size="md" />
        <span className="font-medium">{DisplayName(user)}</span>
      </div>
      <div className="flex gap-2">
        {canTransfer && onTransfer && (
          <button
            onClick={onTransfer}
            className="btn btn-xs btn-ghost text-yellow-600"
            title="Transfer ownership"
          >
            Transfer
          </button>
        )}
        {canRemove && onRemove && (
          <button
            onClick={onRemove}
            disabled={isRemoving}
            className="btn btn-xs btn-ghost text-error"
            title="Remove"
          >
            {isRemoving ? (
              <span className="loading loading-spinner loading-xs" />
            ) : (
              <X className="h-4 w-4" />
            )}
          </button>
        )}
      </div>
    </div>
  );
}

export function AdminTeamSection({
  organization,
  league,
  onUpdate,
}: AdminTeamSectionProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [transferTarget, setTransferTarget] = useState<UserType | null>(null);
  const [showTransferConfirm, setShowTransferConfirm] = useState(false);
  const [showAddAdmin, setShowAddAdmin] = useState(false);
  const [showAddStaff, setShowAddStaff] = useState(false);

  const isSuperuser = useIsSuperuser();
  const isOrgOwner = useIsOrganizationOwner(organization);
  const isOrgAdmin = useIsOrganizationAdmin(organization);
  const isLeagueAdmin = useIsLeagueAdmin(league, organization ? [organization] : undefined);

  const isOrgMode = !!organization && !league;
  const entityId = isOrgMode ? organization?.pk : league?.pk;

  // Local state for team members
  const [localOwner, setLocalOwner] = useState<UserType | null | undefined>(
    isOrgMode ? organization?.owner : null
  );
  const [localAdmins, setLocalAdmins] = useState<UserType[]>(
    (isOrgMode ? organization?.admins : league?.admins) || []
  );
  const [localStaff, setLocalStaff] = useState<UserType[]>(
    (isOrgMode ? organization?.staff : league?.staff) || []
  );

  // Sync local state when props change
  useEffect(() => {
    setLocalOwner(isOrgMode ? organization?.owner : null);
    setLocalAdmins((isOrgMode ? organization?.admins : league?.admins) || []);
    setLocalStaff((isOrgMode ? organization?.staff : league?.staff) || []);
  }, [organization, league, isOrgMode]);

  // Permissions
  const canManageAdmins = isOrgMode
    ? isOrgOwner || isOrgAdmin || isSuperuser
    : isLeagueAdmin || isSuperuser;
  const canRemoveAdmins = isOrgMode
    ? isOrgOwner || isSuperuser
    : isLeagueAdmin || isSuperuser;
  const canManageStaff = canManageAdmins;
  const canTransferOwnership = isOrgMode && (isOrgOwner || isSuperuser);

  // --- Mutations ---

  const addAdminMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      return isOrgMode ? addOrgAdmin(entityId, userId) : addLeagueAdmin(entityId, userId);
    },
    onSuccess: (user) => {
      toast.success('Admin added');
      setLocalAdmins((prev) => [...prev, user]);
      onUpdate?.();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const removeAdminMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      if (isOrgMode) {
        await removeOrgAdmin(entityId, userId);
      } else {
        await removeLeagueAdmin(entityId, userId);
      }
      return userId;
    },
    onSuccess: (userId) => {
      toast.success('Admin removed');
      setLocalAdmins((prev) => prev.filter((a) => a.pk !== userId));
      onUpdate?.();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const addStaffMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      return isOrgMode ? addOrgStaff(entityId, userId) : addLeagueStaff(entityId, userId);
    },
    onSuccess: (user) => {
      toast.success('Staff added');
      setLocalStaff((prev) => [...prev, user]);
      onUpdate?.();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const removeStaffMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      if (isOrgMode) {
        await removeOrgStaff(entityId, userId);
      } else {
        await removeLeagueStaff(entityId, userId);
      }
      return userId;
    },
    onSuccess: (userId) => {
      toast.success('Staff removed');
      setLocalStaff((prev) => prev.filter((s) => s.pk !== userId));
      onUpdate?.();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const transferOwnershipMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      return transferOrgOwnership(entityId, userId);
    },
    onSuccess: (newOwner) => {
      toast.success('Ownership transferred');
      if (localOwner) {
        setLocalAdmins((prev) => [...prev, localOwner]);
      }
      setLocalAdmins((prev) => prev.filter((a) => a.pk !== newOwner.pk));
      setLocalOwner(newOwner);
      setShowTransferConfirm(false);
      setTransferTarget(null);
      onUpdate?.();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  // --- AddUserModal handlers ---

  // Set of PKs that are already admins (owner + admins)
  const adminPkSet = useMemo(() => {
    const pks = new Set<number>();
    if (localOwner?.pk) pks.add(localOwner.pk);
    for (const a of localAdmins) {
      if (a.pk) pks.add(a.pk);
    }
    return pks;
  }, [localOwner, localAdmins]);

  // Set of PKs that are already staff
  const staffPkSet = useMemo(() => {
    const pks = new Set<number>();
    for (const s of localStaff) {
      if (s.pk) pks.add(s.pk);
    }
    return pks;
  }, [localStaff]);

  const handleAddAdmin = useCallback(
    async (payload: AddMemberPayload): Promise<UserType> => {
      if (!payload.user_id) throw new Error('User ID required');
      return new Promise((resolve, reject) => {
        addAdminMutation.mutate(payload.user_id!, {
          onSuccess: (user) => resolve(user),
          onError: (err) => reject(err),
        });
      });
    },
    [addAdminMutation]
  );

  const handleAddStaff = useCallback(
    async (payload: AddMemberPayload): Promise<UserType> => {
      if (!payload.user_id) throw new Error('User ID required');
      return new Promise((resolve, reject) => {
        addStaffMutation.mutate(payload.user_id!, {
          onSuccess: (user) => resolve(user),
          onError: (err) => reject(err),
        });
      });
    },
    [addStaffMutation]
  );

  const isAdminAdded = useCallback(
    (user: UserType) => user.pk != null && adminPkSet.has(user.pk),
    [adminPkSet]
  );

  const isStaffAdded = useCallback(
    (user: UserType) => user.pk != null && staffPkSet.has(user.pk),
    [staffPkSet]
  );

  const handleTransferClick = (user: UserType) => {
    setTransferTarget(user);
    setShowTransferConfirm(true);
  };

  const confirmTransfer = () => {
    if (transferTarget?.pk) {
      transferOwnershipMutation.mutate(transferTarget.pk);
    }
  };

  // Build entityContext for AddUserModal
  const entityContext = useMemo(() => {
    if (isOrgMode && organization?.pk) {
      return { orgId: organization.pk };
    }
    if (league?.pk) {
      return { orgId: league.organization?.pk, leagueId: league.pk };
    }
    return {};
  }, [isOrgMode, organization, league]);

  if (!entityId) return null;

  return (
    <div className="border border-base-300 rounded-lg overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 bg-base-200 hover:bg-base-300 transition-colors"
      >
        <span className="font-semibold">Admin Team</span>
        {isExpanded ? (
          <ChevronDown className="h-5 w-5" />
        ) : (
          <ChevronRight className="h-5 w-5" />
        )}
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="p-4 space-y-6">
          {/* Owner Section (Organization only) */}
          {isOrgMode && (
            <div>
              <h4 className="font-medium mb-2 flex items-center gap-2">
                <Crown className="h-4 w-4 text-yellow-500" />
                Owner
              </h4>
              {localOwner ? (
                <UserRow
                  user={localOwner}
                  role="owner"
                  canRemove={false}
                  canTransfer={false}
                />
              ) : (
                <p className="text-sm text-gray-500 italic">No owner set</p>
              )}
            </div>
          )}

          {/* Inherited Organization Note (League only) */}
          {!isOrgMode && league?.organization && (
            <div className="text-sm text-gray-500 bg-base-200 p-3 rounded-lg">
              <p className="font-medium mb-1">Inherited permissions from:</p>
              <ul className="list-disc list-inside">
                <li>{league.organization.name}</li>
              </ul>
            </div>
          )}

          {/* Admins Section */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-medium flex items-center gap-2">
                <Shield className="h-4 w-4 text-blue-500" />
                Admins
              </h4>
              {canManageAdmins && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowAddAdmin(true)}
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Admin
                </Button>
              )}
            </div>
            <div className="space-y-2">
              {localAdmins.length > 0 ? (
                localAdmins.map((admin) => (
                  <UserRow
                    key={admin.pk}
                    user={admin}
                    role="admin"
                    canRemove={canRemoveAdmins}
                    canTransfer={canTransferOwnership}
                    onRemove={() => admin.pk && removeAdminMutation.mutate(admin.pk)}
                    onTransfer={() => handleTransferClick(admin)}
                    isRemoving={removeAdminMutation.isPending}
                  />
                ))
              ) : (
                <p className="text-sm text-gray-500 italic">No admins</p>
              )}
            </div>
          </div>

          {/* Staff Section */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-medium flex items-center gap-2">
                <User className="h-4 w-4 text-gray-500" />
                Staff
              </h4>
              {canManageStaff && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowAddStaff(true)}
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Staff
                </Button>
              )}
            </div>
            <div className="space-y-2">
              {localStaff.length > 0 ? (
                localStaff.map((member) => (
                  <UserRow
                    key={member.pk}
                    user={member}
                    role="staff"
                    canRemove={canManageStaff}
                    onRemove={() => member.pk && removeStaffMutation.mutate(member.pk)}
                    isRemoving={removeStaffMutation.isPending}
                  />
                ))
              ) : (
                <p className="text-sm text-gray-500 italic">No staff</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Transfer Confirmation Modal */}
      {showTransferConfirm && transferTarget && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Transfer Ownership</h3>
            <p className="py-4">
              Are you sure you want to transfer ownership to{' '}
              <strong>
                {transferTarget.guildNickname ||
                  transferTarget.discordNickname ||
                  transferTarget.username}
              </strong>
              ?
            </p>
            <p className="text-sm text-gray-500">
              You will become an admin after the transfer.
            </p>
            <div className="modal-action">
              <button
                onClick={() => {
                  setShowTransferConfirm(false);
                  setTransferTarget(null);
                }}
                className="btn"
              >
                Cancel
              </button>
              <button
                onClick={confirmTransfer}
                disabled={transferOwnershipMutation.isPending}
                className="btn btn-warning"
              >
                {transferOwnershipMutation.isPending ? (
                  <span className="loading loading-spinner loading-sm" />
                ) : (
                  'Transfer'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Admin Modal */}
      {canManageAdmins && (
        <AddUserModal
          open={showAddAdmin}
          onOpenChange={setShowAddAdmin}
          title={isOrgMode
            ? `Add Admin to ${organization?.name || 'Organization'}`
            : `Add Admin to ${league?.name || 'League'}`
          }
          entityContext={entityContext}
          onAdd={handleAddAdmin}
          isAdded={isAdminAdded}
          hasDiscordServer={false}
        />
      )}

      {/* Add Staff Modal */}
      {canManageStaff && (
        <AddUserModal
          open={showAddStaff}
          onOpenChange={setShowAddStaff}
          title={isOrgMode
            ? `Add Staff to ${organization?.name || 'Organization'}`
            : `Add Staff to ${league?.name || 'League'}`
          }
          entityContext={entityContext}
          onAdd={handleAddStaff}
          isAdded={isStaffAdded}
          hasDiscordServer={false}
        />
      )}
    </div>
  );
}
```

**Step 2: Remove `UserSearchInput` export from barrel (optional cleanup)**

The `UserSearchInput` component can remain in the codebase but is no longer imported by `AdminTeamSection`. If nothing else imports it, consider removing the export from `frontend/app/components/admin-team/index.ts`:

```typescript
export { AdminTeamSection } from './AdminTeamSection';
```

Check if `UserSearchInput` is imported anywhere else before removing. If nothing else uses it, the file can be deleted too.

**Step 3: Verify TypeScript compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/admin-team-modal && npx tsc --noEmit --pretty 2>&1 | grep -E "error TS" | head -20`
Expected: No new errors.

**Step 4: Commit**

```bash
git add frontend/app/components/admin-team/
git commit -m "feat: replace UserSearchInput with AddUserModal in AdminTeamSection"
```

---

### Task 3: Manual verification

**Step 1: Start dev environment**

```bash
cd /home/kettle/git_repos/website/.worktrees/admin-team-modal && just dev::debug
```

**Step 2: Test org admin team management**

1. Navigate to an organization page as an org admin
2. Click "Edit" button
3. Scroll to "Admin Team" section — verify it shows Owner, Admins, Staff with user rows
4. Click "Add Admin" — verify `AddUserModal` opens with site user search
5. Search for a user, add them — verify they appear in the admins list
6. Click X on an admin to remove — verify they disappear
7. Close the edit modal — verify the org page updates (Edit button, Claims tab visibility)

**Step 3: Test league admin team management**

1. Navigate to a league page as a league admin
2. Click "Edit League" button
3. Scroll to "Admin Team" section
4. Click "Add Staff" — verify modal opens
5. Add a staff member — verify they appear

**Step 4: Test the rerender fix**

1. Navigate to an org page as a non-admin user
2. Have another admin add you as admin via the API
3. Refresh the page — verify Edit button appears
4. Click Edit, go to Admin Team, remove yourself
5. Close modal — verify Edit button disappears immediately (no page refresh needed)
