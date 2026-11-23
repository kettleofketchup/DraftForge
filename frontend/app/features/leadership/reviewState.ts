import type { PendingReview } from './schemas';

export type ReviewAction = {
  state: 'todo' | 'submitted' | 'moderated';
  label: 'Rate' | 'Edit' | 'View';
  badge: string | null;
};

export function reviewAction(
  item: Pick<PendingReview, 'scores' | 'void_kind'>,
): ReviewAction {
  if (item.scores === null)
    return { state: 'todo', label: 'Rate', badge: null };
  switch (item.void_kind) {
    case 'withdrawn':
      return { state: 'todo', label: 'Rate', badge: 'Withdrawn' };
    case 'lifecycle':
      return { state: 'todo', label: 'Rate', badge: 'No longer counted' };
    case 'moderated':
      return {
        state: 'moderated',
        label: 'View',
        badge: 'Removed by an organizer',
      };
    default:
      return { state: 'submitted', label: 'Edit', badge: 'Submitted' };
  }
}
