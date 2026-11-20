import { Send } from 'lucide-react';
import type { FormEvent, KeyboardEvent, Ref } from 'react';
import { PrimaryButton } from '~/components/ui/buttons';
import { Input } from '~/components/ui/input';
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
      <Input
        ref={inputRef}
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
        onFocus={onFocus}
        onKeyDown={handleKeyDown}
        disabled={state.inputDisabled}
        placeholder={state.placeholder}
        aria-label="Chat message"
        autoComplete="off"
        className="flex-1 bg-input border-border placeholder:text-muted-foreground"
        data-testid="herodraft-chat-input"
      />
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
