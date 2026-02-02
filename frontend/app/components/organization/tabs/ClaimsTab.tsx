import { useCallback, useEffect, useState } from 'react';
import { Check, Clock, X, AlertCircle } from 'lucide-react';
import {
  getClaimRequests,
  approveClaimRequest,
  rejectClaimRequest,
  type ProfileClaimRequest,
} from '~/components/api/api';
import { ConfirmButton, CancelButton } from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs/ConfirmDialog';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { Badge } from '~/components/ui/badge';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '~/components/ui/alert-dialog';
import { ClaimCard } from './ClaimCard';

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
      console.error('Error fetching claims:', err);
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
      console.error('Error approving claim:', err);
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
      console.error('Error rejecting claim:', err);
      setError('Failed to reject claim request');
    } finally {
      setIsRejecting(false);
      setRejectingClaim(null);
      setRejectionReason('');
    }
  };

  const pendingCount = claims.filter((c) => c.status === 'pending').length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Profile Claim Requests</h2>
      </div>

      {/* Status filter tabs */}
      <Tabs value={statusFilter} onValueChange={(v) => setStatusFilter(v as ClaimStatus)}>
        <TabsList>
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
      <AlertDialog
        open={!!rejectingClaim}
        onOpenChange={(open) => !open && setRejectingClaim(null)}
      >
        <AlertDialogContent className="bg-red-950/95 border-red-800">
          <AlertDialogHeader>
            <AlertDialogTitle>Reject Claim Request</AlertDialogTitle>
            <AlertDialogDescription className="text-slate-300">
              Reject the claim request from{' '}
              <strong>{rejectingClaim?.claimer_username}</strong> for{' '}
              <strong>
                {rejectingClaim?.target_nickname ||
                  `Steam ID ${rejectingClaim?.target_steamid}`}
              </strong>
              .
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="py-4">
            <Label htmlFor="rejection-reason" className="text-slate-300">
              Reason (optional)
            </Label>
            <Input
              id="rejection-reason"
              placeholder="Enter a reason for rejection..."
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              className="mt-2"
              data-testid="rejection-reason-input"
            />
          </div>
          <AlertDialogFooter className="flex-col-reverse sm:flex-row gap-3">
            <CancelButton onClick={() => setRejectingClaim(null)} disabled={isRejecting}>
              Cancel
            </CancelButton>
            <ConfirmButton
              onClick={handleReject}
              loading={isRejecting}
              variant="destructive"
              data-testid="confirm-reject-claim"
            >
              Reject
            </ConfirmButton>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
