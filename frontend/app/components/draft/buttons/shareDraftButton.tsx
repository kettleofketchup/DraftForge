import { Share2 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '~/components/ui/button';
import { PrimaryButton } from '~/components/ui/buttons';
import { InfoDialog } from '~/components/ui/dialogs';
import { Input } from '~/components/ui/input';
import { useUserStore } from '~/store/userStore';

export const ShareDraftButton = () => {
  const [open, setOpen] = useState(false);
  const tournament = useUserStore((state) => state.tournament);
  const shareUrl = `${window.location.origin}/tournament/${tournament.pk}/teams/draft?draft=open`;

  const copyToClipboard = () => {
    navigator.clipboard.writeText(shareUrl);
    toast.success('Copied to clipboard!', {
      description: 'The draft URL has been copied to your clipboard.',
    });
  };

  return (
    <>
      <PrimaryButton onClick={() => setOpen(true)}>
        <Share2 className="mr-2 h-4 w-4" /> Share
      </PrimaryButton>
      <InfoDialog
        open={open}
        onOpenChange={setOpen}
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
