import { ArrowRight, ChevronDown } from 'lucide-react';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { ScrollArea } from '~/components/ui/scroll-area';
import { Separator } from '~/components/ui/separator';
import { HIDE_DELAY_MS } from '~/components/ui/shared-popover-context';
import { LazyChangelogPreview } from './changelog/LazyChangelogPreview';
import { DocsIcon } from './icons';
import { DOCS_URL } from './links';
import { NavItem } from './NavItem';

export const HOVER_OPEN_DELAY_MS = 250;

type OpenedBy = 'hover' | 'pinned' | null;

export function DocsDropdown(): React.JSX.Element {
  const { t } = useTranslation('navbar');
  const whatsNewHeadingId = useId();
  const { pathname, search, hash } = useLocation();
  const [openedBy, setOpenedByState] = useState<OpenedBy>(null);
  const openedByRef = useRef<OpenedBy>(null);
  const openerRef = useRef<OpenedBy>(null);
  const openTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const open = openedBy !== null;

  const setOpenedBy = useCallback((next: OpenedBy) => {
    openedByRef.current = next;
    if (next !== null) openerRef.current = next;
    setOpenedByState(next);
  }, []);

  const clearTimers = useCallback(() => {
    if (openTimer.current) clearTimeout(openTimer.current);
    if (closeTimer.current) clearTimeout(closeTimer.current);
    openTimer.current = null;
    closeTimer.current = null;
  }, []);

  const close = useCallback(() => {
    clearTimers();
    setOpenedBy(null);
  }, [clearTimers, setOpenedBy]);

  useEffect(() => clearTimers, [clearTimers]);

  useEffect(() => {
    close();
  }, [pathname, search, hash, close]);

  const handleOpenChange = (next: boolean) => {
    if (!next) close();
  };

  const handleTriggerClick = (e: React.MouseEvent) => {
    e.preventDefault();
    clearTimers();
    setOpenedBy(openedByRef.current === 'pinned' ? null : 'pinned');
  };

  const handlePointerEnter = (e: React.PointerEvent) => {
    if (e.pointerType !== 'mouse') return;
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = null;
    if (openedByRef.current !== null || openTimer.current) return;
    openTimer.current = setTimeout(() => {
      openTimer.current = null;
      setOpenedBy('hover');
    }, HOVER_OPEN_DELAY_MS);
  };

  const handlePointerLeave = () => {
    if (openTimer.current) clearTimeout(openTimer.current);
    openTimer.current = null;
    if (openedByRef.current !== 'hover') return;
    if (contentRef.current?.contains(document.activeElement)) return;
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => {
      closeTimer.current = null;
      if (openedByRef.current === 'hover') setOpenedBy(null);
    }, HIDE_DELAY_MS);
  };

  const preventFocusOnHover = (e: Event) => {
    if (openerRef.current === 'hover') e.preventDefault();
  };

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger
        asChild
        onClick={handleTriggerClick}
        onPointerEnter={handlePointerEnter}
        onPointerLeave={handlePointerLeave}
      >
        <NavItem
          as="button"
          data-testid="nav-docs-trigger"
          icon={<DocsIcon />}
          title={t('nav.docs')}
          aria-label={t('aria.docs_menu')}
          indicator={<ChevronDown className="size-3" />}
          hideTextOnSmall
          className="[&_svg]:text-info"
        />
      </PopoverTrigger>
      <PopoverContent
        ref={contentRef}
        data-testid="nav-docs-panel"
        align="end"
        aria-label={t('aria.docs_menu')}
        className="bg-popover border-primary/30 w-96 p-0 flex flex-col overflow-hidden max-h-[min(32rem,var(--radix-popover-content-available-height))]"
        onPointerEnter={handlePointerEnter}
        onPointerLeave={handlePointerLeave}
        onOpenAutoFocus={preventFocusOnHover}
        onCloseAutoFocus={preventFocusOnHover}
      >
        <a
          data-testid="nav-docs-documentation-link"
          href={DOCS_URL}
          target="_blank"
          rel="noopener noreferrer"
          onClick={close}
          className="flex items-center gap-3 px-4 py-3 rounded-t-md hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&_svg]:text-info"
        >
          <DocsIcon />
          <span className="flex flex-col">
            <span className="text-sm font-medium text-foreground">
              {t('nav.documentation')}
            </span>
            <span className="text-xs text-muted-foreground">
              {t('nav.docs_subtitle')}
            </span>
          </span>
        </a>
        <Separator />
        <h2
          id={whatsNewHeadingId}
          className="px-4 pt-3 pb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        >
          {t('nav.whats_new')}
        </h2>
        <ScrollArea
          viewportProps={{
            tabIndex: 0,
            role: 'region',
            'aria-labelledby': whatsNewHeadingId,
            className: 'focus-visible:ring-inset',
          }}
          className="flex-1 min-h-0 max-h-72 flex flex-col [&>[data-slot=scroll-area-viewport]]:min-h-0 [&_[data-slot=scroll-area-viewport]>div]:!block"
        >
          <div className="px-4 pb-3">
            <LazyChangelogPreview
              data-testid="nav-changelog-preview"
              onNavigate={close}
            />
          </div>
        </ScrollArea>
        <Separator />
        <Link
          data-testid="nav-changelog-full-link"
          to="/changelog"
          onClick={close}
          className="flex items-center gap-1 px-4 py-2 text-sm text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
        >
          {t('nav.full_changelog')}
          <ArrowRight aria-hidden="true" className="size-3.5" />
        </Link>
      </PopoverContent>
    </Popover>
  );
}
