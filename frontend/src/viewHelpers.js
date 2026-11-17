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


export function useResource(path) {
  const [state, setState] = useState({ data: null, error: "", key: null });
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api(path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ data, error: "", key: `${path}:${version}` });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({
            data: null,
            error: error.message,
            key: `${path}:${version}`,
          });
      });
    return () => controller.abort();
  }, [path, version]);
  const current = state.key === `${path}:${version}`;
  return {
    data: current ? state.data : null,
    error: current ? state.error : "",
    loading: !current,
    reload: () => setVersion((v) => v + 1),
  };
}
