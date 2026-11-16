import { useEffect, useState } from "react";
import { api } from "./api/client";

// Setup page only: proves the frontend can reach the backend. Real pages replace this.
export default function App() {
  const [status, setStatus] = useState("Checking the API...");

  useEffect(() => {
    api("/api/health/")
      .then(() => setStatus("API is connected"))
      .catch(() => setStatus("API is not reachable. Is the backend running?"));
  }, []);

  return (
    <main style={{ maxWidth: "40rem", margin: "0 auto", padding: "var(--space-6) var(--space-3)" }}>
      <h1>BloodLink</h1>
      <p role="status">{status}</p>
    </main>
  );
}