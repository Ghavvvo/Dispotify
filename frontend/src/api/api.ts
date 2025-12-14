// API URL apunta al Leader Proxy
// El proxy se encarga de redirigir automáticamente al líder actual
export const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:3001/api/v1/";

const get = (endpoint: string) => 
    fetch(apiUrl + endpoint).then(res => res.json())

const post = (endpoint: string, body: any) => {
    // Si body es FormData, no establecer Content-Type
    const isFormData = body instanceof FormData;
    return fetch(apiUrl + endpoint, {
        method: "POST",
        body: body,
        ...(isFormData ? {} : { headers: { "Content-Type": "application/json" } })
    }).then(async res => {
        const text = await res.text();
        if (!res.ok) {
            throw new Error(text || `HTTP error! status: ${res.status}`);
        }
        try {
            return text ? JSON.parse(text) : {};
        } catch (e) {
            return text;
        }
    })
}

const put = (endpoint: string, body: any) => 
    fetch(apiUrl + endpoint, {
        method: "PUT",
        body: body
    }).then(res => res.json())

const deleteReq = (endpoint: string, id: number) =>
    fetch(apiUrl + endpoint +  `/${id}`, {
        method: "DELETE"
    }).then(res => res.json())

export const api = {
    get,
    post,
    put,
    deleteReq,
}
