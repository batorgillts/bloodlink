// One place for every call to the Django API.
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export function getToken() {
  return localStorage.getItem("access");
}

export function setToken(access) {
  if (access) localStorage.setItem("access", access);
  else localStorage.removeItem("access");
}

// api("/api/units/") or api("/api/auth/token/", { method: "POST", body: { email, password } })
export async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const error = new Error(data?.detail ?? `Request failed (${res.status})`);
    error.status = res.status;
    error.data = data; // field errors from the backend, e.g. { email: ["..."] }
    throw error;
  }
  return data;
}