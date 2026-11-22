import { chromium, type Browser, type LaunchOptions } from '@playwright/test';

/** chromium.launch with the same executablePath the config's projects use. */
export function launchChromium(options: LaunchOptions = {}): Promise<Browser> {
  return chromium.launch({
    executablePath:
      process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
    ...options,
  });
}
