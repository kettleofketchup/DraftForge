import { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, Clock, X, AlertCircle } from 'lucide-react';
import {
  getClaimRequests,
  approveClaimRequest,
  rejectClaimRequest,
  type ProfileClaimRequest,
} from '~/components/api/api';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { Badge } from '~/components/ui/badge';
import { MobileNavDropdown } from '~/components/ui/mobile-nav-dropdown';
import { getLogger } from '~/lib/logger';
import { ClaimCard } from './ClaimCard';

const log = getLogger('ClaimsTab');

interface Props {
  organizationId: number;
}

type ClaimStatus = 'pending' | 'approved' | 'rejected';

export const ClaimsTab: React.FC<Props> = ({ organizationId }) => {
  const [claims, setClaims] = useState<ProfileClaimRequest[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<ClaimStatus>('pending');

  // Rejection modal state
  const [rejectingClaim, setRejectingClaim] = useState<ProfileClaimRequest | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [isRejecting, setIsRejecting] = useState(false);

  // Approval confirmation state
  const [approvingClaim, setApprovingClaim] = useState<ProfileClaimRequest | null>(null);
  const [isApproving, setIsApproving] = useState(false);

  const fetchClaims = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getClaimRequests({
        organizationId,
        status: statusFilter,
      });
      setClaims(data);
    } catch (err) {
      setError('Failed to load claim requests');
      log.error('fetch claims failed', { err });
    } finally {
      setIsLoading(false);
    }
  }, [organizationId, statusFilter]);

  useEffect(() => {
    fetchClaims();
  }, [fetchClaims]);

  const handleApprove = async () => {
    if (!approvingClaim) return;

    setIsApproving(true);
    try {
      await approveClaimRequest(approvingClaim.id);
      fetchClaims();
    } catch (err) {
      log.error('approve claim failed', { err });
      setError('Failed to approve claim request');
    } finally {
      setIsApproving(false);
      setApprovingClaim(null);
    }
  };

  const handleReject = async () => {
    if (!rejectingClaim) return;

    setIsRejecting(true);
    try {
      await rejectClaimRequest(rejectingClaim.id, rejectionReason);
      fetchClaims();
    } catch (err) {
      log.error('reject claim failed', { err });
      setError('Failed to reject claim request');
    } finally {
      setIsRejecting(false);
      setRejectingClaim(null);
      setRejectionReason('');
    }
  };

  const pendingCount = claims.filter((c) => c.status === 'pending').length;

  const claimStatusOptions = useMemo(() => [
    { value: 'pending', label: 'Pending' },
    { value: 'approved', label: 'Approved' },
    { value: 'rejected', label: 'Rejected' },
  ], []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Profile Claim Requests</h2>
      </div>

      {/* Status filter tabs */}
      <Tabs value={statusFilter} onValueChange={(v) => setStatusFilter(v as ClaimStatus)}>
        {/* Mobile dropdown */}
        <MobileNavDropdown
          options={claimStatusOptions}
          value={statusFilter}
          onValueChange={(v) => setStatusFilter(v as ClaimStatus)}
          variant="secondary"
          className="md:hidden mb-4"
        />

        {/* Desktop tabs */}
        <TabsList className="hidden md:flex">
          <TabsTrigger value="pending" className="gap-2" data-testid="claims-tab-pending">
            <Clock className="w-4 h-4" />
            Pending
            {statusFilter !== 'pending' && pendingCount > 0 && (
              <Badge variant="secondary" className="ml-1 text-xs">
                {pendingCount}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="approved" data-testid="claims-tab-approved">
            <Check className="w-4 h-4 mr-2" />
            Approved
          </TabsTrigger>
          <TabsTrigger value="rejected" data-testid="claims-tab-rejected">
            <X className="w-4 h-4 mr-2" />
            Rejected
          </TabsTrigger>
        </TabsList>

        <TabsContent value={statusFilter} className="mt-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-8" data-testid="claims-loading">
              <span className="loading loading-spinner loading-lg"></span>
            </div>
          ) : error ? (
            <div role="alert" className="alert alert-error" data-testid="claims-error">
              <AlertCircle className="w-5 h-5" />
              <span>{error}</span>
            </div>
          ) : claims.length === 0 ? (
            <div className="alert alert-info" data-testid="claims-empty">
              <span>No {statusFilter} claim requests</span>
            </div>
          ) : (
            <div className="space-y-3" data-testid="claims-list">
              {claims.map((claim, index) => (
                <ClaimCard
                  key={claim.id}
                  claim={claim}
                  index={index}
                  onApprove={setApprovingClaim}
                  onReject={setRejectingClaim}
                />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Approval confirmation dialog */}
      <ConfirmDialog
        open={!!approvingClaim}
        onOpenChange={(open) => !open && setApprovingClaim(null)}
        title="Approve Claim Request"
        description={`${approvingClaim?.claimer_username} will receive the profile data from ${approvingClaim?.target_nickname || `Steam ID ${approvingClaim?.target_steamid}`}. This action will merge the profiles and cannot be undone.`}
        confirmLabel="Approve"
        variant="default"
        isLoading={isApproving}
        onConfirm={handleApprove}
        confirmTestId="confirm-approve-claim"
      />

      {/* Rejection dialog with reason input */}
      <ConfirmDialog
        open={!!rejectingClaim}
        onOpenChange={(open) => !open && setRejectingClaim(null)}
        title="Reject Claim Request"
        description={
          <>
            Reject the claim request from{' '}
            <strong>{rejectingClaim?.claimer_username}</strong> for{' '}
            <strong>
              {rejectingClaim?.target_nickname ||
                `Steam ID ${rejectingClaim?.target_steamid}`}
            </strong>
            .
          </>
        }
        confirmLabel="Reject"
        variant="destructive"
        isLoading={isRejecting}
        onConfirm={handleReject}
        confirmTestId="confirm-reject-claim"
        bodyContent={
          <div className="flex flex-col gap-2">
            <Label htmlFor="rejection-reason">Reason (optional)</Label>
            <Input
              id="rejection-reason"
              placeholder="Enter a reason for rejection..."
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              disabled={isRejecting}
              data-testid="rejection-reason-input"
            />
          </div>
        }
      />
    </div>
  );
};
