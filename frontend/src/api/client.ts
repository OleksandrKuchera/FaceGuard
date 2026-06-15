import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';
const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const USER_KEY = 'fg_user';

const client = axios.create({
    baseURL: API_BASE,
    headers: { 'Content-Type': 'application/json' },
});

function parseJwtExp(token: string): number | null {
    try {
        const payload = JSON.parse(atob(token.split('.')[1])) as { exp?: number };
        return typeof payload.exp === 'number' ? payload.exp : null;
    } catch {
        return null;
    }
}

function clearStoredAuth() {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
}

export async function refreshAccessToken(): Promise<string | null> {
    const refresh = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (!refresh) return null;

    try {
        const { data } = await axios.post<{ access: string }>(
            `${API_BASE}/auth/token/refresh/`,
            { refresh },
        );
        localStorage.setItem(ACCESS_TOKEN_KEY, data.access);
        return data.access;
    } catch {
        clearStoredAuth();
        return null;
    }
}

export async function getValidAccessToken(skewSeconds = 30): Promise<string | null> {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    if (!token) return refreshAccessToken();

    const exp = parseJwtExp(token);
    if (exp === null) return refreshAccessToken();

    const now = Math.floor(Date.now() / 1000);
    if (exp - now <= skewSeconds) {
        return refreshAccessToken();
    }

    return token;
}

// Attach access token to every request
client.interceptors.request.use((config) => {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

// Handle 401 — try to refresh token, then redirect to login
client.interceptors.response.use(
    (res) => res,
    async (err) => {
        const original = err.config;
        if (err.response?.status === 401 && !original._retry) {
            original._retry = true;
            try {
                const access = await refreshAccessToken();
                if (!access) {
                    throw new Error('refresh_failed');
                }
                original.headers.Authorization = `Bearer ${access}`;
                return client(original);
            } catch {
                clearStoredAuth();
                window.location.href = '/login';
            }
        }
        return Promise.reject(err);
    }
);

export default client;

// ── Users (system accounts) ──────────────────────────────────────────────────
export const getUsers        = () => client.get('/users/');
export const createUser      = (data: object) => client.post('/users/', data);
export const updateUser      = (id: number, data: object) => client.patch(`/users/${id}/`, data);
export const deleteUser      = (id: number) => client.delete(`/users/${id}/`);
export const resetPassword   = (id: number, password: string) =>
    client.post(`/users/${id}/reset_password/`, { password });

// ── Auth ─────────────────────────────────────────────────────────────────────
export const login  = (username: string, password: string) =>
    client.post('/auth/token/', { username, password });

export const logout = (refresh: string) =>
    client.post('/auth/logout/', { refresh });

// ── Events ────────────────────────────────────────────────────────────────────
export const getEvents       = (params?: Record<string, string>) => client.get('/events/', { params });
export const getEventStats   = () => client.get('/events/stats/');
export const getDailyStats   = () => client.get('/events/daily_stats/');
export const getHourlyHeatmap = () => client.get('/events/hourly_heatmap/');
export const getTopVisitors  = () => client.get('/events/top_visitors/');
export const getCameraStats  = () => client.get('/events/camera_stats/');
export const reviewEvent     = (id: number) => client.patch(`/events/${id}/review/`);

// ── Persons ───────────────────────────────────────────────────────────────────
export const getPersons  = (params?: Record<string, string>) => client.get('/persons/', { params });
export const getPerson   = (id: number) => client.get(`/persons/${id}/`);

export const createPerson = (data: FormData) =>
    client.post('/persons/', data, { headers: { 'Content-Type': 'multipart/form-data' } });

export const updatePerson = (id: number, data: FormData) =>
    client.patch(`/persons/${id}/`, data, { headers: { 'Content-Type': 'multipart/form-data' } });

export const deletePerson = (id: number) => client.delete(`/persons/${id}/`);

export const uploadPhoto = (personId: number, files: File[]) => {
    const fd = new FormData();
    files.forEach(f => fd.append('image', f));
    return client.post(`/persons/${personId}/photos/`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
};

export const getPhotos        = (personId: number) =>
    client.get(`/persons/${personId}/photos/`);

export const deletePhoto      = (personId: number, photoId: number) =>
    client.delete(`/persons/${personId}/photos/${photoId}/`);

export const trainPerson      = (id: number) => client.post(`/persons/${id}/train/`);
export const getTrainStatus   = (id: number) => client.get(`/persons/${id}/train/status/`);
export const getDepartments   = () => client.get('/departments/');

// ── Cameras ───────────────────────────────────────────────────────────────────
export const getCameras  = () => client.get('/cameras/');
export const createCamera = (data: object) => client.post('/cameras/', data);
export const updateCamera = (id: number, data: object) => client.patch(`/cameras/${id}/`, data);
export const deleteCamera = (id: number) => client.delete(`/cameras/${id}/`);
export const testCamera   = (id: number) => client.post(`/cameras/${id}/test/`);
export const startCamera  = (id: number) => client.post(`/cameras/${id}/start/`);
export const stopCamera   = (id: number) => client.post(`/cameras/${id}/stop/`);
export const getSnapshot  = (id: number) => client.get(`/cameras/${id}/snapshot/`);

// ── Reports ───────────────────────────────────────────────────────────────────
export const getReports    = () => client.get('/reports/');
export const getReport     = (id: number) => client.get(`/reports/${id}/`);
export const createReport  = (data: object) => client.post('/reports/', data);
export const downloadReport = (id: number) => client.get(`/reports/${id}/download/`, { responseType: 'blob' });

// ── Security ──────────────────────────────────────────────────────────────────
export const getSpoofing      = (params?: Record<string, string>) => client.get('/security/spoofing/', { params });
export const getAuditLog      = (params?: Record<string, string>) => client.get('/security/audit-log/', { params });
export const getSecurityStats = () => client.get('/security/spoofing/stats/');

// ── System Settings ───────────────────────────────────────────────────────────
export const getSystemSettings  = () => client.get('/settings/');
export const saveSystemSettings = (data: object) => client.put('/settings/', data);

// ── Camera Zones ──────────────────────────────────────────────────────────────
export const getCameraZones   = (cameraId: number) => client.get(`/cameras/${cameraId}/zones/`);
export const createCameraZone = (cameraId: number, data: object) => client.post(`/cameras/${cameraId}/zones/`, data);
export const updateCameraZone = (cameraId: number, zoneId: number, data: object) => client.put(`/cameras/${cameraId}/zones/${zoneId}/`, data);
export const deleteCameraZone = (cameraId: number, zoneId: number) => client.delete(`/cameras/${cameraId}/zones/${zoneId}/`);
