import * as React from 'react';
import { ExternalLink } from 'lucide-react';
import { Button } from '~/components/ui/button';
import { DiscordIcon } from '~/components/ui/icons';
import { Tooltip, TooltipContent, TooltipTrigger } from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';

const DISCORD_BOT_INVITE_URL =
  'https://discord.com/oauth2/authorize?client_id=1357100182134849670';

export interface AddDiscordBotButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'asChild'> {
  /** Compact mode shows just an icon + short text */
  compact?: boolean;
  /** Optional tooltip text */
  tooltip?: string;
}

const AddDiscordBotButton = React.forwardRef<HTMLButtonElement, AddDiscordBotButtonProps>(
  ({ compact, tooltip, className, ...props }, ref) => {
    const button = (
      <Button
        ref={ref}
        variant="outline"
        className={cn(
          'border-indigo-500/50 text-indigo-400 hover:bg-indigo-500/10 hover:text-indigo-300',
          className
        )}
        asChild
        {...props}
      >
        <a
          href={DISCORD_BOT_INVITE_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          <DiscordIcon className="h-4 w-4 shrink-0" />
          {compact ? 'Add Bot' : 'Add DraftForge Bot to Your Discord'}
          <ExternalLink className="h-3.5 w-3.5 shrink-0" />
        </a>
      </Button>
    );

    if (tooltip) {
      return (
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          <TooltipContent>{tooltip}</TooltipContent>
        </Tooltip>
      );
    }

    return button;
  }
);

AddDiscordBotButton.displayName = 'AddDiscordBotButton';

export { AddDiscordBotButton };
