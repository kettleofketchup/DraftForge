import { motion } from 'framer-motion';
import { ClipboardPen } from 'lucide-react';
import { useActiveDraft } from '~/hooks/useActiveDraft';

/**
 * Floating indicator shown at bottom-right of screen when user has an active draft turn.
 *
 * Provides a prominent, always-visible notification that follows scroll.
 * Clicking navigates to the tournament page with the draft modal open.
 *
 * @example
 * // Add to root layout
 * <FloatingDraftIndicator />
 */
export const FloatingDraftIndicator: React.FC = () => {
  const { activeDraft, hasActiveTurn } = useActiveDraft();

  if (!hasActiveTurn || !activeDraft) {
    return null;
  }

  return (
    <motion.a
      data-testid="floating-draft-indicator"
      href={`/tournaments/${activeDraft.tournament_pk}?draft=open`}
      className="fixed bottom-6 right-6 z-50 bg-red-600 hover:bg-red-700
                 text-white px-4 py-3 rounded-full shadow-lg
                 flex items-center gap-2 cursor-pointer
                 transition-colors duration-200"
      animate={{
        scale: [1, 1.05, 1],
      }}
      transition={{
        duration: 1.5,
        repeat: Infinity,
        ease: 'easeInOut',
      }}
      aria-label={`Your turn to pick in ${activeDraft.tournament_name}`}
      role="alert"
    >
      <ClipboardPen className="w-5 h-5" />
      <span className="font-medium">Your turn to pick!</span>
    </motion.a>
  );
};
