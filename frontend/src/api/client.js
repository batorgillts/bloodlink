const API_URL = (
  import.meta.env.VITE_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");
export const getToken = () => localStorage.getItem("access");
export function setToken(token) {
  if (token) localStorage.setItem("access", token);
  else localStorage.removeItem("access");
}
export function clearSession() {
  setToken(null);
  localStorage.removeItem("bloodlink-user");
}
export function readSession() {
  try {
    const user = JSON.parse(localStorage.getItem("bloodlink-user"));
    return getToken() && ["donor", "coordinator"].includes(user?.role)
      ? user
      : null;
  } catch {
    return null;
  }
}
export function saveSession(data) {
  setToken(data.access);
  const user = { email: data.email, role: data.role };
  localStorage.setItem("bloodlink-user", JSON.stringify(user));
  return user;
}
function messages(data) {
  if (typeof data === "string") return data;
  if (Array.isArray(data)) return data.map(messages).join(" ");
  if (data && typeof data === "object")
    return Object.entries(data)
      .map(
        ([key, value]) =>
          `${key === "detail" || key === "non_field_errors" ? "" : `${key.replaceAll("_", " ")}: `}${messages(value)}`,
      )
      .join(" · ");
  return "";
}
export async function api(
  path,
  { method = "GET", body, signal, anonymous = false } = {},
) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = anonymous ? null : getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      signal,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(
      "Unable to reach BloodLink. Check that the backend is running and try again.",
    );
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token) {
      clearSession();
      window.dispatchEvent(new Event("bloodlink-session-expired"));
    }
    const error = new Error(
      messages(data) || `Request failed (${res.status}). Please try again.`,
    );
    error.status = res.status;
    error.data = data;
    throw error;
  }
  return data;
}
