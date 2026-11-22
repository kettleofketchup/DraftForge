import { extractApiError } from '~/lib/apiError';

interface HttpErrorShape {
  response?: { status?: number; data?: unknown };
}

export interface ReviewError {
  status: number | null;
  data: Record<string, unknown>;
}

export function readReviewError(error: unknown): ReviewError {
  const response = (error as HttpErrorShape)?.response;
  const data =
    response?.data && typeof response.data === 'object'
      ? (response.data as Record<string, unknown>)
      : {};
  return { status: response?.status ?? null, data };
}

export function firstFieldError(value: unknown): string | null {
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
  return typeof value === 'string' ? value : null;
}

const SCREENSHOT_MESSAGES: Record<string, string> = {
  too_large: 'The image must be 8 MB or smaller.',
  unsupported_type: 'Use a PNG, JPEG or WebP image.',
  invalid_image: "That file isn't a readable image.",
};

export function screenshotErrorMessage(code: string): string {
  return SCREENSHOT_MESSAGES[code] ?? code;
}

export function reviewErrorMessage(error: unknown, fallback: string): string {
  const { status, data } = readReviewError(error);
  if (status === 409 && data.error === 'not_pending') {
    return 'This request was already reviewed or cancelled.';
  }
  if (status === 403 && data.error === 'self_review') {
    return "You can't verify your own MMR. Ask another staff member.";
  }
  if (status === 403) {
    return 'You need admin access to review this request.';
  }
  if (status === 413) return SCREENSHOT_MESSAGES.too_large;
  if (status === 503) {
    return 'The server is busy processing images. Try again in a moment.';
  }
  if (status === 507) return 'Uploads are unavailable right now.';
  return extractApiError(error) || fallback;
}
