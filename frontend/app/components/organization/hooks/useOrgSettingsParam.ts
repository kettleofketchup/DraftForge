import { useCallback, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router';

const PARAM = 'settings';
const NAV_OPTIONS = { replace: true, preventScrollReset: true } as const;

export interface OrgSettingsParam {
  /** The `settings` param is present; an empty value counts as open. */
  open: boolean;
  section: string | null;
  openSettings: (section?: string) => void;
  setSection: (value: string) => void;
  close: () => void;
}

/** Org settings modal state in `?settings=<section>`. */
export function useOrgSettingsParam(access: {
  settled: boolean;
  canOpen: boolean;
}): OrgSettingsParam {
  const { settled, canOpen } = access;
  const [searchParams, setSearchParams] = useSearchParams();
  const legacyHandled = useRef(false);
  const raw = searchParams.get(PARAM);
  const isLegacy = searchParams.get('tab') === 'settings';
  const denied = settled && !canOpen;

  useEffect(() => {
    if (isLegacy && !legacyHandled.current) {
      legacyHandled.current = true;
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        const section = next.get('section') ?? '';
        next.delete('tab');
        next.delete('section');
        if (!denied) next.set(PARAM, section);
        return next;
      }, NAV_OPTIONS);
      return;
    }
    if (denied && raw !== null) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete(PARAM);
        return next;
      }, NAV_OPTIONS);
    }
  }, [isLegacy, denied, raw, setSearchParams]);

  const setParam = useCallback(
    (value: string | null) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value === null) next.delete(PARAM);
        else next.set(PARAM, value);
        return next;
      }, NAV_OPTIONS);
    },
    [setSearchParams],
  );

  const openSettings = useCallback(
    (section?: string) => setParam(section ?? ''),
    [setParam],
  );
  const setSection = useCallback(
    (value: string) => setParam(value),
    [setParam],
  );
  const close = useCallback(() => setParam(null), [setParam]);

  return {
    open: raw !== null,
    section: raw || null,
    openSettings,
    setSection,
    close,
  };
}
