import { getErrorMessage } from './getErrorMessage';

/** The `{error: "..."}` message our action endpoints return, else the usual readable fallback. */
export function errText(err: any, fallback?: string): string {
    const msg = err?.response?.data?.error;
    return typeof msg === 'string' && msg ? msg : getErrorMessage(err, fallback);
}
