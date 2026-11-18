import { useEffect, useState } from "react";
import { api } from "./api/client";
export const BLOOD = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];
export const COMPONENTS = {
  RBC: "Red blood cells",
  PLASMA: "Plasma",
  PLATELETS: "Platelets",
};
export const title = (text) =>
  String(text ?? "")
    .replaceAll("_", " ")
    .replace(/^./, (c) => c.toUpperCase());
export const date = (value) =>
  value
    ? (value.length === 10
        ? new Date(`${value}T12:00:00`)
        : new Date(value)
      ).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "—";
export const time = (value) => (value ? new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true }) : "—");


export function useResource(path, {refreshInterval = 0} = {}) {
  const [state, setState] = useState({ data: null, error: "", key: null });
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let controller;
    function fetchLatest() {
      controller?.abort();
      controller = new AbortController();
      const request = controller;
      api(path, { signal: request.signal })
      .then((data) => {
        if (!request.signal.aborted)
          setState({ data, error: "", key: `${path}:${version}` });
      })
      .catch((error) => {
        if (!request.signal.aborted)
          setState(previous => ({
            data: previous.key === `${path}:${version}` ? previous.data : null,
            error: error.message,
            key: `${path}:${version}`,
          }));
      });
    }
    fetchLatest();
    function refreshVisible() { if (document.visibilityState !== "hidden") fetchLatest(); }
    const timer = refreshInterval ? setInterval(refreshVisible, refreshInterval) : null;
    if (refreshInterval) {
      window.addEventListener("focus", refreshVisible);
      document.addEventListener("visibilitychange", refreshVisible);
    }
    return () => {
      controller?.abort(); clearInterval(timer);
      window.removeEventListener("focus", refreshVisible);
      document.removeEventListener("visibilitychange", refreshVisible);
    };
  }, [path, version, refreshInterval]);
  const current = state.key === `${path}:${version}`;
  return {
    data: current ? state.data : null,
    error: current ? state.error : "",
    loading: !current,
    reload: () => setVersion((v) => v + 1),
  };
}
