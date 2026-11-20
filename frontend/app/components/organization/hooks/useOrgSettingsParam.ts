import { useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
import { useLatestSearchParams } from '~/hooks/useLatestSearchParams';

const PARAM = 'settings';
const NAV_OPTIONS = { replace: true, preventScrollReset: true } as const;
const PUSH_OPTIONS = { preventScrollReset: true } as const;

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
  const [searchParams, setSearchParams] = useLatestSearchParams();
  const navigate = useNavigate();
  const pushed = useRef(false);
  const raw = searchParams.get(PARAM);
  const isLegacy = searchParams.get('tab') === 'settings';
  const denied = settled && !canOpen;

  useEffect(() => {
    if (raw === null) pushed.current = false;
  }, [raw]);

  useEffect(() => {
    if (isLegacy) {
      setSearchParams((next) => {
        const section = next.get('section') ?? '';
        next.delete('tab');
        next.delete('section');
        if (!denied) next.set(PARAM, section);
        return next;
      }, NAV_OPTIONS);
      return;
    }
    if (denied && raw !== null) {
      setSearchParams((next) => {
        next.delete(PARAM);
        return next;
      }, NAV_OPTIONS);
    }
  }, [isLegacy, denied, raw, setSearchParams]);

  const setParam = useCallback(
    (value: string | null, push = false) => {
      setSearchParams(
        (next) => {
          if (value === null) next.delete(PARAM);
          else next.set(PARAM, value);
          return next;
        },
        push ? PUSH_OPTIONS : NAV_OPTIONS,
      );
    },
    [setSearchParams],
  );

  const openSettings = useCallback(
    (section?: string) => {
      pushed.current = true;
      setParam(section ?? '', true);
    },
    [setParam],
  );
  const setSection = useCallback(
    (value: string) => setParam(value),
    [setParam],
  );
  // Pop the entry openSettings pushed so history ends as it began.
  const close = useCallback(() => {
    if (pushed.current) {
      pushed.current = false;
      void navigate(-1);
    } else setParam(null);
  }, [navigate, setParam]);

  return {
    open: raw !== null,
    section: raw || null,
    openSettings,
    setSection,
    close,
  };
}
