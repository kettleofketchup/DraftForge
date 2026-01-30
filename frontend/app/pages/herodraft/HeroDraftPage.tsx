// frontend/app/pages/herodraft/HeroDraftPage.tsx
import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router';
import axios from '~/components/api/axios';
import { HeroDraftModal } from '~/components/herodraft/HeroDraftModal';
import { getLogger } from '~/lib/logger';
import type { HeroDraft } from '~/components/herodraft/types';

const log = getLogger('HeroDraftPage');

/**
 * Standalone page for HeroDraft that renders the full HeroDraftModal.
 *
 * This page is used when navigating directly to /herodraft/:id
 * (e.g., from a demo test or direct URL access).
 *
 * Note: Draft state is managed by the WebSocket store. This page only
 * does an initial HTTP fetch to validate the draft exists before opening
 * the modal. The modal's WebSocket connection provides real-time state.
 */
export const HeroDraftPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const draftId = id ? parseInt(id, 10) : null;
  const [draft, setDraft] = useState<HeroDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch draft data initially to validate it exists
  // WebSocket store will receive full state via initial_state message
  const fetchDraft = useCallback(async () => {
    if (!draftId) return;
    try {
      const response = await axios.get(`/herodraft/${draftId}/`);
      const draftData = response.data as HeroDraft;
      setDraft(draftData);
      setError(null);
      log.debug('Draft loaded:', draftData.state);
    } catch (err) {
      log.error('Failed to fetch draft:', err);
      setError('Failed to load hero draft');
    } finally {
      setLoading(false);
    }
  }, [draftId]);

  useEffect(() => {
    fetchDraft();
  }, [fetchDraft]);

  const handleClose = useCallback(() => {
    // Navigate back or to home
    navigate(-1);
  }, [navigate]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center" data-testid="herodraft-loading">
        <div className="text-white text-lg">Loading draft...</div>
      </div>
    );
  }

  if (error || !draft) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-red-500 text-lg">{error || 'Draft not found'}</div>
      </div>
    );
  }

  return (
    <HeroDraftModal
      draftId={draftId!}
      open={true}
      onClose={handleClose}
    />
  );
};

export default HeroDraftPage;
