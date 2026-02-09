import { useState, useCallback, useEffect } from 'react';

interface UseListKeyboardNavOptions {
  /** Length of the site results list */
  siteCount: number;
  /** Length of the discord results list */
  discordCount: number;
  /** Whether discord column exists (has server configured) */
  hasDiscordColumn: boolean;
  /** Callback when Enter is pressed on a highlighted item */
  onSelect: (column: 'site' | 'discord', index: number) => void;
  /** Whether on desktop layout (both columns visible) */
  isDesktop: boolean;
}

interface UseListKeyboardNavReturn {
  highlightedIndex: number;
  activeColumn: 'site' | 'discord';
  setActiveColumn: (col: 'site' | 'discord') => void;
  handleKeyDown: (e: React.KeyboardEvent) => void;
  reset: () => void;
}

export function useListKeyboardNav({
  siteCount,
  discordCount,
  hasDiscordColumn,
  onSelect,
  isDesktop,
}: UseListKeyboardNavOptions): UseListKeyboardNavReturn {
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [activeColumn, setActiveColumn] = useState<'site' | 'discord'>('site');

  const count = activeColumn === 'site' ? siteCount : discordCount;

  const reset = useCallback(() => {
    setHighlightedIndex(-1);
  }, []);

  // Auto-select first result when results change or column switches
  useEffect(() => {
    const activeCount = activeColumn === 'site' ? siteCount : discordCount;
    setHighlightedIndex(activeCount > 0 ? 0 : -1);
  }, [siteCount, discordCount, activeColumn]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setHighlightedIndex((prev) => {
            if (count === 0) return -1;
            return Math.min(prev + 1, count - 1);
          });
          break;

        case 'ArrowUp':
          e.preventDefault();
          setHighlightedIndex((prev) => Math.max(prev - 1, -1));
          break;

        case 'Enter':
          // Always prevent default to avoid FormDialog form submission
          e.preventDefault();
          if (highlightedIndex >= 0 && highlightedIndex < count) {
            onSelect(activeColumn, highlightedIndex);
          }
          break;

        case 'Tab':
          if (isDesktop && hasDiscordColumn) {
            e.preventDefault();
            setActiveColumn((prev) => prev === 'site' ? 'discord' : 'site');
          }
          break;
      }
    },
    [count, highlightedIndex, activeColumn, onSelect, isDesktop, hasDiscordColumn],
  );

  return {
    highlightedIndex,
    activeColumn,
    setActiveColumn,
    handleKeyDown,
    reset,
  };
}
