import { Share2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '~/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '~/components/ui/dialog';
import { Input } from '~/components/ui/input';
import { useUserStore } from '~/store/userStore';

export const ShareDraftButton = () => {
  const tournament = useUserStore((state) => state.tournament);
  const shareUrl = `${window.location.origin}/tournament/${tournament.pk}/teams/draft?draft=open`;

  const copyToClipboard = () => {
    navigator.clipboard.writeText(shareUrl);
    toast.success('Copied to clipboard!', {
      description: 'The draft URL has been copied to your clipboard.',
    });
  };

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline">
          <Share2 className="mr-2 h-4 w-4" /> Share
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Share Draft</DialogTitle>
          <DialogDescription>
            Share this URL with others to invite them to the live draft.
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-center space-x-2">
          <Input value={shareUrl} readOnly />
          <Button onClick={copyToClipboard}>Copy</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
