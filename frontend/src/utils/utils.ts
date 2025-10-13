export function toQueryParams(params: Record<string, any>): string {
    return Object.entries(params)
        .map(([key, value]) =>
            value !== undefined && value !== null
                ? `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`
                : ''
        )
        .filter(Boolean)
        .join('&');
}