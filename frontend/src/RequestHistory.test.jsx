import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";

const response = (data, status = 200) =>
  Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(data),
  });

const audit = {
  message: "",
  requests: [
    {
      id: 3,
      blood_type: "O-",
      component: "RBC",
      quantity: 2,
      status: "fulfilled",
      logged_at: "2026-11-02T15:04:00Z",
      logged_by: 1,
      coordinator: "Ava Chen",
      events: [
        {
          id: 1,
          event_type: "logged",
          from_status: "",
          to_status: "pending",
          unit: null,
          unit_code: "",
          matched_unit_codes: [],
          created_at: "2026-11-02T15:04:00Z",
          actor: 1,
          actor_email: "coord@example.com",
          actor_name: "Ava Chen",
        },
        {
          id: 2,
          event_type: "matched",
          from_status: "",
          to_status: "",
          unit: null,
          unit_code: "",
          matched_unit_codes: ["US20-A", "US20-O"],
          created_at: "2026-11-02T15:10:00Z",
          actor: 1,
          actor_email: "coord@example.com",
          actor_name: "Ava Chen",
        },
        {
          id: 3,
          event_type: "reserved",
          from_status: "",
          to_status: "",
          unit: 9,
          unit_code: "US20-A",
          matched_unit_codes: [],
          created_at: "2026-11-02T15:12:00Z",
          actor: 1,
          actor_email: "coord@example.com",
          actor_name: "Ava Chen",
        },
        {
          id: 4,
          event_type: "status_changed",
          from_status: "pending",
          to_status: "fulfilled",
          unit: null,
          unit_code: "",
          matched_unit_codes: [],
          created_at: "2026-11-02T15:12:00Z",
          actor: 1,
          actor_email: "coord@example.com",
          actor_name: "Ava Chen",
        },
      ],
    },
  ],
};

function login(role = "coordinator") {
  localStorage.setItem("access", "test-access");
  localStorage.setItem(
    "bloodlink-user",
    JSON.stringify({ email: "test@example.com", role }),
  );
}

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState({}, "", "/login");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("request history shows the audit trail and filters by logged date", async () => {
  login();
  window.history.replaceState({}, "", "/request-history");
  const fetch = vi.fn((url) =>
    response(String(url).includes("logged_from")
      ? { message: "No requests found for this period", requests: [] }
      : audit),
  );
  vi.stubGlobal("fetch", fetch);
  render(<App />);

  expect(await screen.findByRole("heading", { name: "Request history" })).toBeInTheDocument();
  expect(screen.getByText("History entries are kept for traceability and cannot be edited or deleted.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "REQ-3" })).toHaveAttribute("href", "/requests/3");
  expect(screen.getByText("Ava Chen", { selector: "dd" })).toBeInTheDocument();
  expect(screen.getByText("Red blood cells")).toBeInTheDocument();
  expect(screen.getByText("Fulfilled", { exact: false, selector: ".status-label" })).toBeInTheDocument();
  expect(screen.getByText("US20-A, US20-O")).toBeInTheDocument();
  expect(screen.getByText("Unit 9 · US20-A")).toBeInTheDocument();
  expect(screen.getByText("Pending → Fulfilled")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /edit|delete/i })).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Logged from"), { target: { value: "11/01/2026" } });
  fireEvent.change(screen.getByLabelText("Logged to"), { target: { value: "11/30/2026" } });
  fireEvent.submit(screen.getByRole("button", { name: "Apply date range" }).closest("form"));

  expect(await screen.findByText("No requests found for this period")).toBeInTheDocument();
  const filtered = fetch.mock.calls.map(([url]) => String(url)).find((url) => url.includes("logged_from"));
  expect(filtered).toContain("logged_from=2026-11-01");
  expect(filtered).toContain("logged_to=2026-11-30");
});

test("a donor cannot open request history", () => {
  login("donor");
  window.history.replaceState({}, "", "/request-history");
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  expect(screen.getByRole("heading", { name: "You do not have access" })).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});
