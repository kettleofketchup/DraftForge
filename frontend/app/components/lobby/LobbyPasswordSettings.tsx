import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Control, FieldValues, UseFormWatch } from 'react-hook-form';
import { Eye, EyeOff, Loader2, RefreshCw } from 'lucide-react';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { CopyPasswordButton } from './CopyPasswordButton';
import {
  LOBBY_PASSWORD_MAX_LENGTH,
  type LobbyPasswordIssue,
  type LobbyPasswordMode,
} from './password';
import type { LobbyPasswordInfo } from './schemas';

/** The form fields this section edits (see refineLobbyPassword). */
interface LobbyPasswordFields {
  dota_lobby_password_mode?: LobbyPasswordMode;
  dota_lobby_password?: string;
}

interface LobbyPasswordSettingsProps<T extends FieldValues & LobbyPasswordFields> {
  control: Control<T>;
  watch: UseFormWatch<T>;
  /** A series hands its setting to its events; an event has one password. */
  scope: 'series' | 'event';
  /** The saved settings (edit forms), from the lobby-password endpoint. */
  saved?: LobbyPasswordInfo | null;
  /** Generate a new random password now (events in random mode). */
  onRegenerate?: () => void;
  regenerating?: boolean;
}

/**
 * Series and event setting for the lobby password every lobby of an event
 * uses: random (generated per event) or fixed (typed by staff).
 */
export function LobbyPasswordSettings<T extends FieldValues & LobbyPasswordFields>({
  control: parentControl,
  watch: parentWatch,
  scope,
  saved,
  onRegenerate,
  regenerating = false,
}: LobbyPasswordSettingsProps<T>) {
  const { t } = useTranslation('lobby');
  const [shown, setShown] = useState(false);
  const control = parentControl as unknown as Control<LobbyPasswordFields>;
  const watch = parentWatch as unknown as UseFormWatch<LobbyPasswordFields>;
  const mode = watch('dota_lobby_password_mode');
  const savedRandom = saved?.mode === 'random' && saved.password ? saved.password : null;

  const issueText = (issue: string | undefined): string | null => {
    switch (issue as LobbyPasswordIssue | undefined) {
      case 'required':
        return t('password.errors.required');
      case 'too_long':
        return t('password.errors.too_long', { max: LOBBY_PASSWORD_MAX_LENGTH });
      case 'invalid_characters':
        return t('password.errors.invalid_characters');
      case 'surrounding_spaces':
        return t('password.errors.surrounding_spaces');
      default:
        return issue ?? null;
    }
  };

  return (
    <div className="space-y-3" data-testid="lobby-password-settings">
      <h4 className="text-sm font-medium text-muted-foreground">
        {t('password.settings.title')}
      </h4>
      <div className="rounded-md border border-border p-3 space-y-3">
        <FormField
          control={control}
          name="dota_lobby_password_mode"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('password.settings.mode_label')}</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger className="w-full" data-testid="lobby-password-mode">
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="random" data-testid="lobby-password-mode-random">
                    {t('password.settings.mode.random')}
                  </SelectItem>
                  <SelectItem value="fixed" data-testid="lobby-password-mode-fixed">
                    {t('password.settings.mode.fixed')}
                  </SelectItem>
                </SelectContent>
              </Select>
            </FormItem>
          )}
        />

        {mode === 'fixed' ? (
          <FormField
            control={control}
            name="dota_lobby_password"
            render={({ field, fieldState }) => (
              <FormItem>
                <FormLabel>{t('password.settings.password_label')}</FormLabel>
                <div className="flex items-center gap-2">
                  <FormControl>
                    <Input
                      type={shown ? 'text' : 'password'}
                      autoComplete="off"
                      maxLength={LOBBY_PASSWORD_MAX_LENGTH}
                      data-testid="lobby-password-input"
                      {...field}
                      value={field.value ?? ''}
                    />
                  </FormControl>
                  <SecondaryButton
                    type="button"
                    size="sm"
                    onClick={() => setShown((s) => !s)}
                    aria-label={shown ? t('password.settings.hide') : t('password.settings.show')}
                    data-testid="lobby-password-toggle"
                  >
                    {shown ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </SecondaryButton>
                </div>
                {fieldState.error && (
                  <p className="text-sm text-destructive" data-testid="lobby-password-error">
                    {issueText(fieldState.error.message)}
                  </p>
                )}
              </FormItem>
            )}
          />
        ) : scope === 'series' ? (
          <p className="text-sm text-muted-foreground">{t('password.settings.random_series')}</p>
        ) : savedRandom ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted-foreground">{t('password.settings.current')}</span>
            <code
              className="rounded bg-muted px-1.5 py-0.5"
              data-testid="lobby-password-current"
            >
              {savedRandom}
            </code>
            <CopyPasswordButton password={savedRandom} data-testid="lobby-password-copy" />
            {onRegenerate && (
              <SecondaryButton
                type="button"
                size="sm"
                onClick={onRegenerate}
                disabled={regenerating}
                data-testid="lobby-password-regenerate"
              >
                {regenerating ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <RefreshCw className="size-4" />
                )}
                {t('password.settings.regenerate')}
              </SecondaryButton>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{t('password.settings.random_new')}</p>
        )}

        <FormDescription>{t('password.settings.help_shared')}</FormDescription>
        <FormDescription>{t('password.settings.help_changes')}</FormDescription>
        {scope === 'event' && saved?.source === 'series' && (
          <FormDescription data-testid="lobby-password-from-series">
            {t('password.settings.from_series')}
          </FormDescription>
        )}
      </div>
    </div>
  );
}
