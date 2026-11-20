import { MessageSquare } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from '~/components/ui/sheet';
import { VisuallyHidden } from '~/components/ui/visually-hidden';
import { useMediaQuery } from '~/hooks/useMediaQuery';
import { cn } from '~/lib/utils';
import { heroDraftSelectors, useHeroDraftStore } from '~/store/heroDraftStore';
import { ChatComposer } from './ChatComposer';
import { chatErrorText } from './chatErrors';
import { ChatLog } from './ChatLog';
import { composerState } from './composerState';
import { parseChatInput } from './parseChatInput';

const PAUSED_STATES = new Set(['paused', 'resuming']);

export interface HeroDraftChatProps {
  draftState: string;
}

export function HeroDraftChat({ draftState }: HeroDraftChatProps) {
  const isDesktop = useMediaQuery('(min-width: 768px)');
  const chat = useHeroDraftStore((s) => s.chat);
  const connected = useHeroDraftStore(heroDraftSelectors.isConnected);
  const sendChat = useHeroDraftStore((s) => s.sendChat);
  const setChatPanelOpen = useHeroDraftStore((s) => s.setChatPanelOpen);
  const clearChatError = useHeroDraftStore((s) => s.clearChatError);
  const setSelectedHeroId = useHeroDraftStore((s) => s.setSelectedHeroId);

  const [raw, setRaw] = useState('');
  const rawRef = useRef(raw);
  rawRef.current = raw;
  const [restoredError, setRestoredError] =
    useState<typeof chat.lastError>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { viewer, lastError, panelOpen, unread, messages } = chat;
  const state = composerState({ viewer, draftState, connected, raw });
  const target = viewer?.can_post_team ? parseChatInput(raw).channel : null;

  useEffect(() => {
    if (lastError?.text && rawRef.current === '') {
      setRaw(lastError.text);
      setRestoredError(lastError);
    }
  }, [lastError]);

  useEffect(() => {
    if (!isDesktop || !panelOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setChatPanelOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [isDesktop, panelOpen, setChatPanelOpen]);

  const submit = useCallback(() => {
    clearChatError();
    if (sendChat(raw) !== null) setRaw('');
  }, [clearChatError, sendChat, raw]);

  const focusInput = () => {
    if (inputRef.current && !inputRef.current.disabled)
      inputRef.current.focus();
  };

  const toggle = () => {
    const next = !panelOpen;
    setChatPanelOpen(next);
    if (next && isDesktop) focusInput();
  };

  const emptyText = viewer?.can_post_team
    ? 'No messages yet. Type /all to talk to everyone.'
    : 'No messages yet.';

  const errorLine = lastError && (
    <p
      role="alert"
      className="rounded-md bg-destructive/15 px-2 py-1 text-xs text-destructive"
      data-testid="herodraft-chat-error"
    >
      {chatErrorText(lastError.code)}
      {lastError.text && restoredError !== lastError && (
        <span className="text-muted-foreground">
          {' — not sent: '}
          <span className="whitespace-pre-wrap">{lastError.text}</span>
        </span>
      )}
    </p>
  );

  const composer = (
    <ChatComposer
      inputRef={inputRef}
      value={raw}
      onValueChange={setRaw}
      onSubmit={submit}
      state={state}
      target={target}
      onFocus={isDesktop ? () => setChatPanelOpen(true) : undefined}
      onEscape={() => setChatPanelOpen(false)}
    />
  );

  const toggleButton = (
    <SecondaryButton
      type="button"
      size="icon"
      onClick={toggle}
      aria-label={panelOpen ? 'Hide chat' : 'Show chat'}
      aria-expanded={panelOpen}
      className="relative shrink-0"
      data-testid="herodraft-chat-toggle"
    >
      <MessageSquare className="size-4" />
      {unread > 0 && (
        <span
          className="absolute -right-1 -top-1 min-w-4 rounded-full bg-primary px-1 text-[10px] leading-4 text-primary-foreground"
          data-testid="herodraft-chat-unread"
        >
          {unread > 99 ? '99+' : unread}
        </span>
      )}
    </SecondaryButton>
  );

  const log = (
    <ChatLog
      messages={messages}
      emptyText={emptyText}
      onHeroClick={setSelectedHeroId}
      className="flex-1"
    />
  );

  if (!isDesktop) {
    return (
      <>
        {toggleButton}
        <div className="flex-1" />
        <Sheet open={panelOpen} onOpenChange={setChatPanelOpen}>
          <SheetContent
            side="bottom"
            className="flex h-[70vh] flex-col gap-2 p-3 pt-10"
            onOpenAutoFocus={(e) => {
              if (inputRef.current && !inputRef.current.disabled) {
                e.preventDefault();
                inputRef.current.focus();
              }
            }}
            data-herodraft-chat=""
            data-testid="herodraft-chat-sheet"
          >
            <VisuallyHidden>
              <SheetTitle>Draft chat</SheetTitle>
              <SheetDescription>
                Team and all chat for this draft
              </SheetDescription>
            </VisuallyHidden>
            {log}
            {errorLine}
            {composer}
          </SheetContent>
        </Sheet>
      </>
    );
  }

  return (
    <div
      ref={rootRef}
      className="relative flex min-w-0 flex-1 items-center gap-2"
      data-herodraft-chat=""
    >
      {(panelOpen || errorLine) && (
        <div className="absolute bottom-full left-0 right-0 z-20 mb-2 flex flex-col gap-1">
          {panelOpen && (
            <div
              className={cn(
                'flex flex-col overflow-hidden rounded-md border border-border bg-card/95 shadow-lg backdrop-blur',
                PAUSED_STATES.has(draftState) ? 'h-[25vh]' : 'h-[40vh]',
              )}
              data-testid="herodraft-chat-panel"
            >
              {log}
            </div>
          )}
          {errorLine}
        </div>
      )}
      {toggleButton}
      {composer}
    </div>
  );
}
