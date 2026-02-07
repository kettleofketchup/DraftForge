import { useState, useCallback } from 'react';
import { Upload, CheckCircle, XCircle } from 'lucide-react';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Button } from '~/components/ui/button';
import { ConfirmButton } from '~/components/ui/buttons';
import { importCSVToOrg, importCSVToTournament } from '~/components/api/api';
import type { CSVImportResponse } from '~/components/api/api';

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

  const reset = useCallback(() => {
    setStep('upload');
    setValidatedRows([]);
    setRawRows([]);
    setImportResult(null);
    setIsImporting(false);
    setError(null);
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
      const validRows = validatedRows
        .filter((r) => r.status !== 'error')
        .map((r) => ({
          steam_friend_id: r.raw.steam_friend_id?.trim() || undefined,
          discord_id: r.raw.discord_id?.trim() || undefined,
          base_mmr: r.raw.base_mmr?.trim() ? Number(r.raw.base_mmr.trim()) : null,
          team_name: r.raw.team_name?.trim() || undefined,
        }));

      let result: CSVImportResponse;
      if (entityContext.tournamentId) {
        result = await importCSVToTournament(entityContext.tournamentId, validRows);
      } else if (entityContext.orgId) {
        result = await importCSVToOrg(entityContext.orgId, validRows);
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
  }, [validatedRows, entityContext, onComplete]);

  const errorCount = validatedRows.filter((r) => r.status === 'error').length;
  const validCount = validatedRows.length - errorCount;

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
              Columns: steam_friend_id, discord_id, base_mmr
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
                    <th className="px-3 py-2 text-left">Steam ID</th>
                    <th className="px-3 py-2 text-left">Discord ID</th>
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
                      <td className="px-3 py-1.5 font-mono text-xs">
                        {row.raw.steam_friend_id || '\u2014'}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-xs">
                        {row.raw.discord_id || '\u2014'}
                      </td>
                      <td className="px-3 py-1.5">{row.raw.base_mmr || '\u2014'}</td>
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

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => handleOpenChange(false)}>
                Cancel
              </Button>
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
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
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

            {/* Detail rows with warnings/errors */}
            {importResult.results.some((r) => r.warning || r.status === 'error') && (
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
                      .filter((r) => r.warning || r.status === 'error' || r.status === 'skipped')
                      .map((r) => (
                        <tr key={r.row}>
                          <td className="px-3 py-1.5 text-muted-foreground">{r.row}</td>
                          <td className="px-3 py-1.5">
                            {r.status === 'error' && (
                              <span className="text-destructive">Error</span>
                            )}
                            {r.status === 'skipped' && (
                              <span className="text-warning">Skipped</span>
                            )}
                            {r.status === 'added' && r.warning && (
                              <span className="text-success">Added</span>
                            )}
                          </td>
                          <td className="px-3 py-1.5 text-xs">
                            {r.reason || r.warning}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex justify-end">
              <Button onClick={() => handleOpenChange(false)}>Done</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
