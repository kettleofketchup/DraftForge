import { Send } from 'lucide-react';
import type { FormEvent, KeyboardEvent, Ref } from 'react';
import { PrimaryButton } from '~/components/ui/buttons';
import { Input } from '~/components/ui/input';
import { Kbd } from '~/components/ui/kbd';
import { cn } from '~/lib/utils';
import { ChannelBadge } from './ChatMessageRow';
import type { ComposerState } from './composerState';
import type { ChatChannel } from './parseChatInput';

export interface ChatComposerProps {
  inputRef: Ref<HTMLInputElement>;
  value: string;
  onValueChange: (value: string) => void;
  onSubmit: () => void;
  state: ComposerState;
  target: ChatChannel | null;
  onFocus?: () => void;
  onEscape?: () => void;
  enterHint?: boolean;
  className?: string;
}

export function ChatComposer({
  inputRef,
  value,
  onValueChange,
  onSubmit,
  state,
  target,
  onFocus,
  onEscape,
  enterHint = false,
  className,
}: ChatComposerProps) {
  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (state.sendDisabled) return;
    onSubmit();
  };
  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') onEscape?.();
  };

  const showHint = enterHint && !state.inputDisabled && value === '';

  return (
    <form
      onSubmit={handleSubmit}
      className={cn('flex min-w-0 flex-1 items-center gap-2', className)}
    >
      {target && (
        <span data-testid="herodraft-chat-target" className="shrink-0">
          <ChannelBadge channel={target} />
        </span>
      )}
      <div className="relative min-w-0 flex-1">
        <Input
          ref={inputRef}
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
          onFocus={onFocus}
          onKeyDown={handleKeyDown}
          disabled={state.inputDisabled}
          placeholder={state.placeholder}
          aria-label="Chat message"
          aria-keyshortcuts={showHint ? 'Enter' : undefined}
          autoComplete="off"
          className={cn(
            'peer w-full bg-input border-border placeholder:text-muted-foreground',
            showHint && 'pr-16',
          )}
          data-testid="herodraft-chat-input"
        />
        {showHint && (
          <Kbd
            className="absolute top-1/2 right-2 -translate-y-1/2 peer-focus:hidden"
            aria-hidden="true"
            data-testid="herodraft-chat-enter-hint"
          >
            Enter
          </Kbd>
        )}
      </div>
      <PrimaryButton
        type="submit"
        size="icon"
        disabled={state.sendDisabled}
        aria-label="Send message"
        className="shrink-0"
        data-testid="herodraft-chat-send"
      >
        <Send className="size-4" />
      </PrimaryButton>
    </form>
  );
}
