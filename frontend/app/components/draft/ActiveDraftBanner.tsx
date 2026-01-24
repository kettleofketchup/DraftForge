import { ChevronDown, ClipboardPen, X } from 'lucide-react';
import { useState } from 'react';
import { Link, useLocation } from 'react-router';
import { Button } from '~/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import { useUserStore } from '~/store/userStore';
import { getDraftLabel, getDraftUrl } from './utils';

/**
 * Check if user is currently on a draft page.
 */
function isOnDraftPage(pathname: string): boolean {
  return pathname.includes('/draft');
}

/**
 * Banner displayed below navbar when user has active drafts.
 * Hidden on mobile (use FloatingDraftIndicator instead).
 * Hidden when user is on a draft page.
 */
export const ActiveDraftBanner: React.FC = () => {
  const [dismissed, setDismissed] = useState(false);
  const location = useLocation();
  const activeDrafts = useUserStore(
    (state) => state.currentUser?.active_drafts,
  );

  // Don't show if no active drafts, dismissed, or on draft page
  if (
    !activeDrafts ||
    activeDrafts.length === 0 ||
    dismissed ||
    isOnDraftPage(location.pathname)
  ) {
    return null;
  }

  const singleDraft = activeDrafts.length === 1;

  return (
    <div
      data-testid="active-draft-banner"
      className="hidden md:flex w-full bg-red-600 text-white px-4 py-2 items-center justify-center gap-3"
    >
      <ClipboardPen className="w-5 h-5 flex-shrink-0" />

      {singleDraft ? (
        // Single draft: direct link
        <Link
          to={getDraftUrl(activeDrafts[0])}
          className="font-medium hover:underline"
        >
          You have an active{' '}
          {activeDrafts[0].type === 'team_draft' ? 'team' : 'hero'} draft - Click
          to join
        </Link>
      ) : (
        // Multiple drafts: dropdown
        <div className="flex items-center gap-2">
          <span className="font-medium">
            You have {activeDrafts.length} active drafts
          </span>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="text-white hover:bg-red-700 h-7 px-2"
              >
                Select <ChevronDown className="ml-1 h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="center">
              {activeDrafts.map((draft, index) => (
                <DropdownMenuItem key={index} asChild>
                  <Link to={getDraftUrl(draft)}>{getDraftLabel(draft)}</Link>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

      <button
        onClick={() => setDismissed(true)}
        className="ml-auto p-1 hover:bg-red-700 rounded"
        aria-label="Dismiss banner"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};
