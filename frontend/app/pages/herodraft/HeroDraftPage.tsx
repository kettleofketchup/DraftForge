// frontend/app/pages/herodraft/HeroDraftPage.tsx
import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router';
import axios from '~/components/api/axios';
import { HeroDraftModal } from '~/components/herodraft/HeroDraftModal';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { getLogger } from '~/lib/logger';
import type { HeroDraft } from '~/components/herodraft/types';

const log = getLogger('HeroDraftPage');

/**
 * Standalone page for HeroDraft that renders the full HeroDraftModal.
 *
 * This page is used when navigating directly to /herodraft/:id
 * (e.g., from a demo test or direct URL access).
 */
export const HeroDraftPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const draftId = id ? parseInt(id, 10) : null;
  const [draft, setDraft] = useState<HeroDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Store setters
  const setStoreDraft = useHeroDraftStore((state) => state.setDraft);

  // Fetch draft data initially
  const fetchDraft = useCallback(async () => {
    if (!draftId) return;
    try {
      const response = await axios.get(`/herodraft/${draftId}/`);
      const draftData = response.data as HeroDraft;
      setDraft(draftData);
      setStoreDraft(draftData);
      setError(null);
      log.debug('Draft loaded:', draftData.state);
    } catch (err) {
      log.error('Failed to fetch draft:', err);
      setError('Failed to load hero draft');
    } finally {
      setLoading(false);
    }
  }, [draftId, setStoreDraft]);

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
