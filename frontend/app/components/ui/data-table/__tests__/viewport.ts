/**
 * jsdom has no `matchMedia`, so `useMediaQuery` reads every breakpoint as
 * "small". This answers `(min-width: Npx)` / `(max-width: Npx)` queries as if
 * the window were `width` px wide. Returns a restore function.
 */
export function setViewportWidth(width: number): () => void {
  const original = window.matchMedia;
  window.matchMedia = ((query: string) => {
    const min = /min-width:\s*(\d+)px/.exec(query);
    const max = /max-width:\s*(\d+)px/.exec(query);
    const matches =
      (!min || width >= Number(min[1])) && (!max || width <= Number(max[1]));
    return {
      matches,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    };
  }) as typeof window.matchMedia;
  return () => {
    window.matchMedia = original;
  };
}
