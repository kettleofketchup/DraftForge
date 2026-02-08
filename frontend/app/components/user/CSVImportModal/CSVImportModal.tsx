import { useState, useCallback, useRef } from 'react';
import { Upload, CheckCircle, XCircle, RefreshCw, AlertTriangle, UserPlus } from 'lucide-react';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Button } from '~/components/ui/button';
import { ConfirmButton, PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import { Label } from '~/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { importCSVToOrg, importCSVToTournament } from '~/components/api/api';
import type { CSVImportResponse, CSVImportRow, MMRTarget } from '~/components/api/api';
import type { UserType } from '~/components/user/types';
import { UserStrip } from '~/components/user/UserStrip';

import { parseCSV, validateRows } from './csvParser';
import type {
  CSVImportModalProps,
  CSVRow,
  ImportStep,
  ValidatedRow,
} from './types';

export function CSVImportModal({
  open,
  onOpenChange,
  entityContext,
  onComplete,
}: CSVImportModalProps) {
  const [step, setStep] = useState<ImportStep>('upload');
  const [validatedRows, setValidatedRows] = useState<ValidatedRow[]>([]);
  const [rawRows, setRawRows] = useState<CSVRow[]>([]);
  const [importResult, setImportResult] = useState<CSVImportResponse | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updateMmr, setUpdateMmr] = useState(false);
  const [mmrTarget, setMmrTarget] = useState<MMRTarget>('organization');
  const [resolvingRows, setResolvingRows] = useState<Set<number>>(new Set());

  // Maps backend row number → raw CSV data (for conflict resolution)
  const sentRowMapRef = useRef<Map<number, CSVRow>>(new Map());

  const reset = useCallback(() => {
    setStep('upload');
    setValidatedRows([]);
    setRawRows([]);
    setImportResult(null);
    setIsImporting(false);
    setError(null);
    setUpdateMmr(false);
    setMmrTarget('organization');
    setResolvingRows(new Set());
    sentRowMapRef.current = new Map();
  }, []);

  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (!open) reset();
      onOpenChange(open);
    },
    [onOpenChange, reset],
  );

  const handleFileSelect = useCallback(
    async (file: File) => {
      setError(null);
      try {
        const result = await parseCSV(file);
        if (result.errors.length > 0) {
          setError(`CSV parse error: ${result.errors[0].message}`);
          return;
        }
        if (result.data.length === 0) {
          setError('CSV file is empty');
          return;
        }
        setRawRows(result.data);
        setValidatedRows(validateRows(result.data));
        setStep('preview');
      } catch (err) {
        setError(`Failed to parse CSV: ${err instanceof Error ? err.message : 'Unknown error'}`);
      }
    },
    [],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file && file.name.endsWith('.csv')) {
        handleFileSelect(file);
      } else {
        setError('Please drop a .csv file');
      }
    },
    [handleFileSelect],
  );

  const handleImport = useCallback(async () => {
    setIsImporting(true);
    setError(null);
    try {
      // Filter to non-error rows and prepare payload
      const rowMap = new Map<number, CSVRow>();
      const validRows = validatedRows
        .filter((r) => r.status !== 'error')
        .map((r, filteredIndex) => {
          rowMap.set(filteredIndex + 1, r.raw); // backend uses 1-indexed rows
          return {
            steam_friend_id: r.raw.steam_friend_id?.trim() || undefined,
            discord_id: r.raw.discord_id?.trim() || undefined,
            discord_username: r.raw.discord_username?.trim() || undefined,
            name: r.raw.name?.trim() || undefined,
            mmr: r.raw.mmr?.trim() ? Number(r.raw.mmr.trim()) : null,
            team_name: r.raw.team_name?.trim() || undefined,
          };
        });
      sentRowMapRef.current = rowMap;

      const options = {
        update_mmr: updateMmr,
        mmr_target: mmrTarget,
      };

      let result: CSVImportResponse;
      if (entityContext.tournamentId) {
        result = await importCSVToTournament(entityContext.tournamentId, validRows, options);
      } else if (entityContext.orgId) {
        result = await importCSVToOrg(entityContext.orgId, validRows, options);
      } else {
        throw new Error('No entity context provided');
      }

      setImportResult(result);
      setStep('results');
      onComplete();
    } catch (err) {
      setError(`Import failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setIsImporting(false);
    }
  }, [validatedRows, entityContext, onComplete, updateMmr, mmrTarget]);

  const handleResolveConflict = useCallback(async (rowNumber: number, selectedUser: UserType) => {
    setResolvingRows((prev) => new Set(prev).add(rowNumber));
    try {
      // Build a single-row import using only the selected user's identifier
      const originalRaw = sentRowMapRef.current.get(rowNumber);
      const row: CSVImportRow = {};
      if (selectedUser.steamid) {
        row.steam_friend_id = String(selectedUser.steamid);
      } else if (selectedUser.discordId) {
        row.discord_id = selectedUser.discordId;
      }
      // Include mmr from the original CSV row
      if (originalRaw?.mmr?.trim()) {
        row.mmr = Number(originalRaw.mmr.trim());
      }
      if (originalRaw?.name?.trim()) {
        row.name = originalRaw.name.trim();
      }
      if (originalRaw?.team_name?.trim()) {
        row.team_name = originalRaw.team_name.trim();
      }

      const options = {
        update_mmr: updateMmr,
        mmr_target: mmrTarget,
      };

      let result: CSVImportResponse;
      if (entityContext.tournamentId) {
        result = await importCSVToTournament(entityContext.tournamentId, [row], options);
      } else if (entityContext.orgId) {
        result = await importCSVToOrg(entityContext.orgId, [row], options);
      } else {
        return;
      }

      const resolved = result.results[0];
      if (!resolved) return;

      // Merge the resolved result back into the existing import result
      setImportResult((prev) => {
        if (!prev) return prev;
        const newResults = prev.results.map((r) =>
          r.row === rowNumber
            ? { ...resolved, row: rowNumber }
            : r,
        );
        const newSummary = { ...prev.summary };
        // Decrement errors since this row was an error
        newSummary.errors = Math.max(0, newSummary.errors - 1);
        // Increment the appropriate counter based on the resolved status
        if (resolved.status === 'added') newSummary.added++;
        else if (resolved.status === 'updated') newSummary.updated++;
        else if (resolved.status === 'skipped') newSummary.skipped++;
        else if (resolved.status === 'error') newSummary.errors++;
        return { summary: newSummary, results: newResults };
      });
      onComplete();
    } catch (err) {
      setError(`Failed to resolve conflict: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setResolvingRows((prev) => {
        const next = new Set(prev);
        next.delete(rowNumber);
        return next;
      });
    }
  }, [entityContext, updateMmr, mmrTarget, onComplete]);

  const errorCount = validatedRows.filter((r) => r.status === 'error').length;
  const validCount = validatedRows.length - errorCount;

  // Check if any rows have mmr values (to show MMR update option)
  const hasMMRValues = validatedRows.some((r) => r.raw.mmr?.trim());

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Import CSV</DialogTitle>
          <DialogDescription className="sr-only">
            Upload a CSV file to bulk-import users
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive flex items-center gap-2">
            <XCircle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {/* Step 1: Upload */}
        {step === 'upload' && (
          <div
            className="border-2 border-dashed border-muted-foreground/25 rounded-lg p-12 text-center cursor-pointer hover:border-muted-foreground/50 transition-colors"
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => {
              const input = document.createElement('input');
              input.type = 'file';
              input.accept = '.csv';
              input.onchange = (e) => {
                const file = (e.target as HTMLInputElement).files?.[0];
                if (file) handleFileSelect(file);
              };
              input.click();
            }}
          >
            <Upload className="h-10 w-10 mx-auto mb-4 text-muted-foreground" />
            <p className="text-sm font-medium">Drop a CSV file here or click to browse</p>
            <p className="text-xs text-muted-foreground mt-2">
              Columns: steam_friend_id, discord_id, discord_username, name, mmr
              {entityContext.tournamentId && ', team_name'}
            </p>
          </div>
        )}

        {/* Step 2: Preview */}
        {step === 'preview' && (
          <div className="flex flex-col gap-4 min-h-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3 text-sm">
                <span className="text-success flex items-center gap-1">
                  <CheckCircle className="h-4 w-4" /> {validCount} valid
                </span>
                {errorCount > 0 && (
                  <span className="text-destructive flex items-center gap-1">
                    <XCircle className="h-4 w-4" /> {errorCount} errors
                  </span>
                )}
              </div>
              <Button variant="ghost" size="sm" onClick={reset}>
                Choose different file
              </Button>
            </div>

            <div className="overflow-auto border rounded-md max-h-[400px]">
              <table className="w-full text-sm">
                <thead className="bg-muted sticky top-0">
                  <tr>
                    <th className="px-3 py-2 text-left w-8">#</th>
                    <th className="px-3 py-2 text-left">Status</th>
                    <th className="px-3 py-2 text-left">Name</th>
                    <th className="px-3 py-2 text-left">Steam ID</th>
                    <th className="px-3 py-2 text-left">Discord</th>
                    <th className="px-3 py-2 text-left">MMR</th>
                    {entityContext.tournamentId && (
                      <th className="px-3 py-2 text-left">Team</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {validatedRows.map((row) => (
                    <tr
                      key={row.index}
                      className={
                        row.status === 'error'
                          ? 'bg-destructive/10'
                          : ''
                      }
                    >
                      <td className="px-3 py-1.5 text-muted-foreground">
                        {row.index + 1}
                      </td>
                      <td className="px-3 py-1.5">
                        {row.status === 'error' && (
                          <span className="text-destructive flex items-center gap-1" title={row.message}>
                            <XCircle className="h-3.5 w-3.5" />
                          </span>
                        )}
                        {row.status === 'valid' && (
                          <span className="text-success">
                            <CheckCircle className="h-3.5 w-3.5" />
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-1.5">
                        {row.raw.name || '\u2014'}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-xs">
                        {row.raw.steam_friend_id || '\u2014'}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-xs">
                        {row.raw.discord_username || row.raw.discord_id || '\u2014'}
                      </td>
                      <td className="px-3 py-1.5">{row.raw.mmr || '\u2014'}</td>
                      {entityContext.tournamentId && (
                        <td className="px-3 py-1.5">
                          {row.raw.team_name || '\u2014'}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* MMR Update Options */}
            {hasMMRValues && (
              <div className="rounded-md border border-border/50 bg-muted/30 p-3 space-y-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={updateMmr}
                    onChange={(e) => setUpdateMmr(e.target.checked)}
                    className="rounded border-border"
                  />
                  <span className="text-sm font-medium">
                    Update MMR for existing members
                  </span>
                </label>

                {updateMmr && (
                  <div className="flex items-center gap-3 pl-6">
                    <Label htmlFor="mmr-target" className="text-sm text-muted-foreground whitespace-nowrap">
                      Store MMR in:
                    </Label>
                    <Select
                      value={mmrTarget}
                      onValueChange={(v) => setMmrTarget(v as MMRTarget)}
                    >
                      <SelectTrigger id="mmr-target" className="w-[180px] h-8">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="organization">Organization</SelectItem>
                        {entityContext.tournamentId && (
                          <SelectItem value="league">League</SelectItem>
                        )}
                      </SelectContent>
                    </Select>
                  </div>
                )}

                {updateMmr && (
                  <p className="text-xs text-muted-foreground pl-6 flex items-center gap-1">
                    <AlertTriangle className="h-3.5 w-3.5 text-warning shrink-0" />
                    Existing members will have their {mmrTarget} MMR overwritten with CSV values
                  </p>
                )}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <SecondaryButton onClick={() => handleOpenChange(false)}>
                Cancel
              </SecondaryButton>
              <ConfirmButton
                onClick={handleImport}
                disabled={validCount === 0}
                loading={isImporting}
              >
                Import {validCount} rows
              </ConfirmButton>
            </div>
          </div>
        )}

        {/* Step 3: Results */}
        {step === 'results' && importResult && (
          <div className="flex flex-col gap-4 min-h-0">
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <div className="rounded-md bg-success/15 p-3 text-center">
                <div className="text-2xl font-bold text-success">
                  {importResult.summary.added}
                </div>
                <div className="text-xs text-muted-foreground">Added</div>
              </div>
              <div className="rounded-md bg-info/15 p-3 text-center">
                <div className="text-2xl font-bold text-info">
                  {importResult.summary.created}
                </div>
                <div className="text-xs text-muted-foreground">Created</div>
              </div>
              <div className="rounded-md bg-primary/15 p-3 text-center">
                <div className="text-2xl font-bold text-primary">
                  {importResult.summary.updated}
                </div>
                <div className="text-xs text-muted-foreground">Updated</div>
              </div>
              <div className="rounded-md bg-warning/15 p-3 text-center">
                <div className="text-2xl font-bold text-warning">
                  {importResult.summary.skipped}
                </div>
                <div className="text-xs text-muted-foreground">Skipped</div>
              </div>
              <div className="rounded-md bg-destructive/15 p-3 text-center">
                <div className="text-2xl font-bold text-destructive">
                  {importResult.summary.errors}
                </div>
                <div className="text-xs text-muted-foreground">Errors</div>
              </div>
            </div>

            {/* Detail rows with errors/skipped/updated */}
            {importResult.results.some(
              (r) => r.status === 'error' || r.status === 'skipped' || r.status === 'updated',
            ) && (
              <div className="overflow-auto border rounded-md max-h-[300px]">
                <table className="w-full text-sm">
                  <thead className="bg-muted sticky top-0">
                    <tr>
                      <th className="px-3 py-2 text-left w-8">Row</th>
                      <th className="px-3 py-2 text-left">Status</th>
                      <th className="px-3 py-2 text-left">Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {importResult.results
                      .filter(
                        (r) => r.status === 'error' || r.status === 'skipped' || r.status === 'updated',
                      )
                      .map((r) => (
                        <tr key={r.row} className={r.status === 'error' ? 'bg-destructive/5' : ''}>
                          <td className="px-3 py-1.5 text-muted-foreground">{r.row}</td>
                          <td className="px-3 py-1.5">
                            {r.status === 'error' && (
                              <span className="text-destructive">Error</span>
                            )}
                            {r.status === 'skipped' && (
                              <span className="text-warning">Skipped</span>
                            )}
                            {r.status === 'updated' && (
                              <span className="text-primary flex items-center gap-1">
                                <RefreshCw className="h-3 w-3" /> Updated
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-1.5">
                            <div className="text-xs">{r.reason}</div>
                            {r.conflict_users && r.conflict_users.length > 0 && (
                              <div className="mt-2 space-y-1">
                                {r.conflict_users.map((u) => (
                                  <UserStrip
                                    key={u.pk}
                                    user={u}
                                    compact
                                    showPositions={false}
                                    actionSlot={
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-7 text-xs gap-1"
                                        disabled={resolvingRows.has(r.row)}
                                        onClick={() => handleResolveConflict(r.row, u)}
                                      >
                                        <UserPlus className="h-3.5 w-3.5" />
                                        {resolvingRows.has(r.row) ? 'Adding...' : 'Use this instead'}
                                      </Button>
                                    }
                                  />
                                ))}
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex justify-end">
              <PrimaryButton onClick={() => handleOpenChange(false)}>Done</PrimaryButton>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
