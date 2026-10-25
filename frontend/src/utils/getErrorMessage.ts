/**
 * A readable message for a toast from an axios error -- never the raw
 * response body. Without this, a non-JSON error response (nginx's HTML
 * "413 Request Entity Too Large" page, a Django 500 debug page, etc.) ends
 * up getting JSON.stringify'd and dumped straight into the user's face as
 * an unreadable blob of markup.
 */
export function getErrorMessage(err: any, fallback = 'Something went wrong. Please try again.'): string {
    const status = err?.response?.status;
    const data = err?.response?.data;

    if (status === 413) return 'That file is too large. Please choose a smaller file.';
    if (status === 401) return 'Your session has expired -- please log in again.';
    if (status === 403) return "You don't have permission to do that.";
    if (status === 404) return 'Not found.';
    if (typeof status === 'number' && status >= 500) return 'Server error -- please try again in a moment.';
    if (!err?.response) return 'Network error -- check your connection and try again.';

    // DRF validation errors: {field: ["msg", ...]} or {non_field_errors: [...]} or {detail: "msg"}
    if (data && typeof data === 'object') {
        const firstKey = Object.keys(data)[0];
        if (firstKey) {
            const value = data[firstKey];
            const message = Array.isArray(value) ? value[0] : value;
            if (typeof message === 'string') {
                return firstKey === 'non_field_errors' || firstKey === 'detail' ? message : `${firstKey}: ${message}`;
            }
        }
    }

    // A string body that isn't markup (HTML error pages always start with
    // a tag) is usually short and safe to show as-is; anything else falls
    // back to the generic message rather than risk showing raw HTML.
    if (typeof data === 'string' && !data.trim().startsWith('<') && data.length < 200) return data;

    return fallback;
}
