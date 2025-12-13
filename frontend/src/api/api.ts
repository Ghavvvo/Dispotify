// Leader Resolver configuration
const LEADER_RESOLVER_URL = import.meta.env.VITE_LEADER_RESOLVER_URL || "http://localhost:3001";
const USE_LEADER_RESOLVER = import.meta.env.VITE_USE_LEADER_RESOLVER !== "false"; // Default true
const FALLBACK_API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/api/v1/";

// Cache for leader URL
let cachedLeaderUrl: string | null = null;
let lastLeaderCheck = 0;
const LEADER_CACHE_TTL = 5000; // 5 seconds

/**
 * Get the current cluster leader URL from the leader-resolver service
 */
async function getLeaderUrl(): Promise<string> {
    const now = Date.now();
    
    // Return cached value if still valid
    if (cachedLeaderUrl && (now - lastLeaderCheck) < LEADER_CACHE_TTL) {
        return cachedLeaderUrl;
    }

    try {
        const response = await fetch(`${LEADER_RESOLVER_URL}/cluster/leader`, {
            signal: AbortSignal.timeout(3000) // 3 second timeout
        });
        
        if (!response.ok) {
            throw new Error(`Leader resolver returned ${response.status}`);
        }
        
        const data = await response.json();
        const leaderUrl = `http://${data.leaderHost}:${data.leaderPort}/api/v1/`;
        
        // Update cache
        cachedLeaderUrl = leaderUrl;
        lastLeaderCheck = now;
        
        console.log(`[API] Leader resolved: ${leaderUrl}`);
        return leaderUrl;
    } catch (error) {
        console.warn(`[API] Failed to resolve leader, using fallback:`, error);
        return FALLBACK_API_URL;
    }
}

/**
 * Get the API URL (either from leader-resolver or fallback)
 */
async function getApiUrl(): Promise<string> {
    if (!USE_LEADER_RESOLVER) {
        return FALLBACK_API_URL;
    }
    return getLeaderUrl();
}

const get = async (endpoint: string) => {
    const apiUrl = await getApiUrl();
    return fetch(apiUrl + endpoint).then(res => res.json());
}

const post = async (endpoint: string, body: any) => {
    const apiUrl = await getApiUrl();
    // Si body es FormData, no establecer Content-Type
    const isFormData = body instanceof FormData;
    return fetch(apiUrl + endpoint, {
        method: "POST",
        body: body,
        ...(isFormData ? {} : { headers: { "Content-Type": "application/json" } })
    }).then(res => res.json());
}

const put = async (endpoint: string, body: any) => {
    const apiUrl = await getApiUrl();
    return fetch(apiUrl + endpoint, {
        method: "PUT",
        body: body
    }).then(res => res.json());
}

const deleteReq = async (endpoint: string, id: number) => {
    const apiUrl = await getApiUrl();
    return fetch(apiUrl + endpoint +  `/${id}`, {
        method: "DELETE"
    }).then(res => res.json());
}

/**
 * Get the base server URL (without /api/v1/)
 * Used for constructing static file URLs (e.g., music files)
 */
async function getServerUrl(): Promise<string> {
    const apiUrl = await getApiUrl();
    // Remove /api/v1/ from the end
    return apiUrl.replace(/\/api\/v1\/?$/, '');
}

export const api = {
    get,
    post,
    put,
    deleteReq,
}

// Export for debugging/testing and static file URLs
export { getLeaderUrl, getApiUrl, getServerUrl };