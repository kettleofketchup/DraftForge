import { Share2 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '~/components/ui/button';
import { SecondaryButton } from '~/components/ui/buttons';
import { InfoDialog } from '~/components/ui/dialogs';
import { Input } from '~/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { useUserStore } from '~/store/userStore';

export const ShareDraftButton = () => {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const tournament = useUserStore((state) => state.tournament);
  const shareUrl = `${window.location.origin}/tournament/${tournament.pk}/teams/draft?draft=open`;

  const copyToClipboard = () => {
    navigator.clipboard.writeText(shareUrl);
    toast.success('Copied to clipboard!', {
      description: 'The draft URL has been copied to your clipboard.',
    });
    setPopoverOpen(false);
  };

  return (
    <>
      {/* Desktop: Full button with text and dialog */}
      <SecondaryButton
        color="sky"
        onClick={() => setDialogOpen(true)}
        className="hidden lg:inline-flex"
      >
        <Share2 className="mr-2 h-4 w-4" /> Share
      </SecondaryButton>

      {/* Mobile/Tablet: Icon-only button with popover */}
      <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
        <PopoverTrigger asChild>
          <SecondaryButton color="sky" className="lg:hidden">
            <Share2 className="h-4 w-4" />
          </SecondaryButton>
        </PopoverTrigger>
        <PopoverContent className="w-80" align="end">
          <div className="space-y-2">
            <h4 className="font-medium leading-none">Share Draft</h4>
            <p className="text-sm text-muted-foreground">
              Copy the URL to share with others.
            </p>
            <div className="flex items-center space-x-2">
              <Input value={shareUrl} readOnly className="text-xs" />
              <Button size="sm" onClick={copyToClipboard}>
                Copy
              </Button>
            </div>
          </div>
        </PopoverContent>
      </Popover>

      {/* Full dialog for desktop */}
      <InfoDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title="Share Draft"
        size="sm"
        showClose={false}
      >
        <p className="text-sm text-muted-foreground mb-4">
          Share this URL with others to invite them to the live draft.
        </p>
        <div className="flex items-center space-x-2">
          <Input value={shareUrl} readOnly />
          <Button onClick={copyToClipboard}>Copy</Button>
        </div>
      </InfoDialog>
    </>
  );
};
