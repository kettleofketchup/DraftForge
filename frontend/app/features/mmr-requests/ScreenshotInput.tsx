import { ImageUp, X } from 'lucide-react';
import { useEffect, useId, useRef, useState, type DragEvent } from 'react';
import { SecondaryButton } from '~/components/ui/buttons';
import { cn } from '~/lib/utils';
import { MAX_SCREENSHOT_MB, screenshotErrorMessage } from './reviewErrors';
import { MAX_SCREENSHOT_BYTES, SCREENSHOT_TYPES } from './schemas';

const ACCEPT = SCREENSHOT_TYPES.join(',');

export interface ScreenshotInputProps {
  value: File | null;
  onChange: (file: File | null) => void;
  required?: boolean;
  error?: string;
  id?: string;
  'aria-describedby'?: string;
}

function checkFile(file: File): string | null {
  if (!(SCREENSHOT_TYPES as readonly string[]).includes(file.type)) {
    return screenshotErrorMessage('unsupported_type');
  }
  if (file.size > MAX_SCREENSHOT_BYTES) {
    return screenshotErrorMessage('too_large');
  }
  return null;
}

function formatSize(bytes: number): string {
  return bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function ScreenshotInput({
  value,
  onChange,
  required = false,
  error,
  id,
  'aria-describedby': describedBy,
}: ScreenshotInputProps) {
  const fallbackId = useId();
  const inputId = id ?? fallbackId;
  const messageId = `${inputId}-error`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!value) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(value);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [value]);

  const accept = (file: File | undefined) => {
    if (!file) return;
    const problem = checkFile(file);
    setLocalError(problem);
    if (!problem) onChange(file);
  };

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    accept(event.dataTransfer.files?.[0]);
  };

  const remove = () => {
    setLocalError(null);
    if (inputRef.current) inputRef.current.value = '';
    onChange(null);
  };

  const message = localError ?? error;
  const inputDescribedBy =
    [describedBy, message ? messageId : null].filter(Boolean).join(' ') ||
    undefined;

  return (
    <div className="flex flex-col gap-2">
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={ACCEPT}
        className="peer sr-only"
        data-testid="mmr-screenshot-input"
        aria-required={required}
        aria-invalid={message ? true : undefined}
        aria-describedby={inputDescribedBy}
        onChange={(event) => {
          accept(event.target.files?.[0]);
          event.target.value = '';
        }}
      />
      {value && previewUrl ? (
        <div className="flex items-center gap-3 rounded-lg border border-border p-2">
          <img
            src={previewUrl}
            alt="Screenshot preview"
            className="h-16 w-28 rounded object-cover"
            data-testid="mmr-screenshot-preview"
          />
          <div className="min-w-0 flex-1 text-sm">
            <p className="truncate font-medium">{value.name}</p>
            <p className="text-xs text-muted-foreground">
              {formatSize(value.size)}
            </p>
          </div>
          <SecondaryButton type="button" size="sm" onClick={remove}>
            <X className="size-3.5" aria-hidden />
            Remove
          </SecondaryButton>
        </div>
      ) : (
        <label
          htmlFor={inputId}
          data-testid="mmr-screenshot-dropzone"
          className={cn(
            'cursor-pointer rounded-lg border-2 border-dashed border-muted-foreground/25 p-6 text-center transition-colors hover:border-muted-foreground/50 peer-focus-visible:border-ring peer-focus-visible:ring-[3px] peer-focus-visible:ring-ring/50',
            message && 'border-destructive/50',
          )}
          onDrop={handleDrop}
          onDragOver={(event) => event.preventDefault()}
        >
          <ImageUp
            className="mx-auto mb-2 size-8 text-muted-foreground"
            aria-hidden
          />
          <span className="block text-sm font-medium">
            Drop an image or click to choose
          </span>
          <span className="mt-1 block text-xs text-muted-foreground">
            PNG, JPEG or WebP, up to {MAX_SCREENSHOT_MB} MB
          </span>
        </label>
      )}
      {message && (
        <p id={messageId} role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
    </div>
  );
}
