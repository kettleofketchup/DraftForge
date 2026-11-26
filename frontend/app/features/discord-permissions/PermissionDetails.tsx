import {
  BLOCKER_TEXT,
  permissionLabel,
  REASON_TEXT,
  remedyFor,
  VERIFICATION_LIMITATION,
} from './copy';
import type { PermissionCheckResult } from './schemas';

export function PermissionDetails({
  result,
  operationLabel,
  historical = false,
}: {
  result: PermissionCheckResult;
  operationLabel: string;
  historical?: boolean;
}) {
  const alternatives =
    result.status === 'missing_permissions'
      ? result.required_any.filter(
          (group) => !group.some((flag) => result.granted?.includes(flag)),
        )
      : [];
  const alternativeFlags = new Set(alternatives.flat());
  const missing = result.missing.filter((flag) => !alternativeFlags.has(flag));
  const beforeTimeout =
    result.base_granted &&
    result.granted &&
    (result.base_granted.length !== result.granted.length ||
      result.base_granted.some((flag) => !result.granted?.includes(flag)));
  const destination = result.destination;
  const checkedAt = result.checked_at ? new Date(result.checked_at) : null;
  const validTime = checkedAt && Number.isFinite(checkedAt.getTime());
  return (
    <div
      className="flex flex-col gap-3 text-sm"
      data-testid={`discord-permission-details-${result.key}`}
    >
      <h3 className="font-semibold">{operationLabel} permissions</h3>
      <p>Action: {permissionLabel(result.action)}</p>
      <p>
        Destination:{' '}
        {destination.name
          ? `#${destination.name}`
          : (destination.channel_id ?? permissionLabel(destination.kind))}
        {destination.source ? ` (${destination.source})` : ''}
      </p>
      {historical && (
        <p className="text-muted-foreground">
          This check has expired. These details are historical, not current
          verification.
        </p>
      )}
      {result.reason && <p>{REASON_TEXT[result.reason]}</p>}
      {(missing.length > 0 || alternatives.length > 0) && (
        <section
          aria-label="Missing permissions"
          className="flex flex-col gap-1"
        >
          <h4 className="font-medium">Missing</h4>
          <ul className="list-inside list-disc">
            {missing.map((flag) => (
              <li key={flag}>{permissionLabel(flag)}</li>
            ))}
            {alternatives.map((group) => (
              <li key={group.join('|')}>
                {group.map(permissionLabel).join(' or ')}
              </li>
            ))}
          </ul>
          {missing.map((flag) => (
            <p key={flag} className="text-muted-foreground">
              {remedyFor(flag)}
            </p>
          ))}
          {alternatives.map((group) => (
            <p key={group.join('|')} className="text-muted-foreground">
              Allow {group.map(permissionLabel).join(' or ')} on the bot's role.
            </p>
          ))}
        </section>
      )}
      {result.blockers.length > 0 && (
        <section aria-label="Operation blockers">
          <h4 className="font-medium">Blockers</h4>
          <ul className="list-inside list-disc">
            {result.blockers.map((blocker, index) => (
              <li key={`${blocker.code}-${index}`}>
                {BLOCKER_TEXT[blocker.code]}
                {blocker.role_id ? ` (Role ${blocker.role_id})` : ''}
              </li>
            ))}
          </ul>
        </section>
      )}
      {result.granted !== null && (
        <details>
          <summary className="cursor-pointer font-medium">
            {historical
              ? 'Previously observed permissions'
              : 'Granted permissions'}
          </summary>
          <ul className="list-inside list-disc">
            {result.granted.map((flag) => (
              <li key={flag}>{permissionLabel(flag)}</li>
            ))}
          </ul>
          {result.granted.length === 0 && (
            <p>No effective permissions granted.</p>
          )}
          {beforeTimeout && (
            <div className="mt-2">
              <h4 className="font-medium">Before timeout</h4>
              <ul className="list-inside list-disc">
                {result.base_granted?.map((flag) => (
                  <li key={flag}>{permissionLabel(flag)}</li>
                ))}
              </ul>
            </div>
          )}
        </details>
      )}
      <p className="text-muted-foreground">
        Checked at:{' '}
        {validTime
          ? `${checkedAt.toLocaleString()} (${checkedAt.toISOString()} UTC)`
          : 'Not checked'}
      </p>
      {result.refresh_state && (
        <p className="text-muted-foreground">Refresh: {result.refresh_state}</p>
      )}
      {result.retry_after_seconds !== null && (
        <p>Retry after {result.retry_after_seconds} seconds.</p>
      )}
      <p className="text-muted-foreground">{VERIFICATION_LIMITATION}</p>
    </div>
  );
}
