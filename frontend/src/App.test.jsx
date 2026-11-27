import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";
import { api } from "./api/client";

const response = (data, status = 200) =>
  Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(data),
  });
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
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("sign-in sends credentials without an old token and routes coordinator to requests", async () => {
  localStorage.setItem("access", "stale-token");
  const fetch = vi.fn((url) =>
    url.endsWith("/token/")
      ? response({
          access: "fresh",
          email: "test@example.com",
          role: "coordinator",
        })
      : response([{
          id: 42,
          logged_at: "2026-11-17T12:00:00Z",
          blood_type: "A+",
          component: "RBC",
          quantity: 2,
          reserved_units: [],
          status: "pending",
        }]),
  );
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  fireEvent.change(screen.getByLabelText("Email address"), {
    target: { value: "test@example.com" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "Password123" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(
    await screen.findByRole("heading", { name: "Blood requests" }),
  ).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: "REQ-42" })).toHaveAttribute("href", "/requests/42");
  expect(screen.getByRole("cell", { name: "Nov 17, 2026" })).toBeInTheDocument();
  expect(fetch.mock.calls[0][1].headers.Authorization).toBeUndefined();
  expect(localStorage.getItem("access")).toBe("fresh");
});
test("invalid credentials remain on sign-in with the backend message", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => response({ detail: "No active account found" }, 401)),
  );
  render(<App />);
  fireEvent.change(screen.getByLabelText("Email address"), {
    target: { value: "test@example.com" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "wrong" },
  });
  fireEvent.submit(
    screen.getByRole("button", { name: "Sign in" }).closest("form"),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "No active account found",
  );
});
test.each(["/inventory", "/appointments"])("a donor cannot load coordinator route %s", (path) => {
  login("donor");
  window.history.replaceState({}, "", path);
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  expect(
    screen.getByRole("heading", { name: "You do not have access" }),
  ).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});
test("coordinator appointments are linked in navigation and load their own API", async () => {
  login();
  window.history.replaceState({}, "", "/appointments");
  const fetch = vi.fn(() => response({ appointments: [], donation_types: [] }));
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  expect(screen.getByRole("link", { name: "Donation appointments" })).toHaveAttribute("href", "/appointments");
  expect(await screen.findByText("No donation appointments yet.")).toBeInTheDocument();
  expect(fetch.mock.calls[0][0]).toMatch(/\/api\/appointments\/$/);
});
test("protected 401 clears the session and prompts sign-in", async () => {
  login();
  window.history.replaceState({}, "", "/requests");
  vi.stubGlobal(
    "fetch",
    vi.fn(() => response({ detail: "Token expired" }, 401)),
  );
  render(<App />);
  expect(
    await screen.findByRole("heading", { name: "Sign in to BloodLink" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("session has expired");
  expect(localStorage.getItem("access")).toBeNull();
});
test("reservation requires confirmation and refreshes persisted request details", async () => {
  login();
  window.history.replaceState({}, "", "/requests/1");
  let reserved = false;
  const request = () => ({
    id: 1,
    quantity: 2,
    blood_type: "A+",
    component: "RBC",
    status: reserved ? "partially_fulfilled" : "pending",
    can_cancel: true,
    reserved_units: reserved
      ? [
          {
            unit_id: 7,
            unit_code: "UNIT-7",
            blood_type: "O-",
            component: "RBC",
            expires_at: "2026-12-01T12:00:00Z",
          },
        ]
      : [],
  });
  const fetch = vi.fn((url, options) => {
    if (url.endsWith("/reserve/")) {
      reserved = true;
      expect(JSON.parse(options.body)).toEqual({ unit_ids: [7] });
      return response({ ...request(), remaining_quantity: 1 }, 201);
    }
    if (url.endsWith("/matches/"))
      return response({
        units: [
          {
            id: 7,
            unit_code: "UNIT-7",
            blood_type: "O-",
            expires_at: "2026-12-01T12:00:00Z",
          },
        ],
      });
    return response(request());
  });
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Find compatible units" }),
  );
  fireEvent.click(await screen.findByLabelText("Select UNIT-7"));
  fireEvent.click(
    screen.getByRole("button", { name: "Reserve selected units" }),
  );
  expect(reserved).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Confirm", exact: true }));
  expect(await screen.findByText(/Reservation saved/)).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByText("Partially fulfilled")).toBeInTheDocument(),
  );
  expect(screen.getByText("UNIT-7")).toBeInTheDocument();
});
test("API preserves field validation messages and handles empty responses", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementationOnce(() =>
        response({ email: ["Already registered."] }, 409),
      )
      .mockImplementationOnce(() => response(null, 204)),
  );
  await expect(api("/api/auth/register/", { anonymous: true })).rejects.toThrow(
    "email: Already registered.",
  );
  await expect(api("/api/example/")).resolves.toBeNull();
});

test("coordinator can reload a populated requests page and filter it to empty", async () => {
  login();
  window.history.replaceState({}, "", "/requests");
  const fetch = vi.fn((url) => response(url.includes("status=fulfilled") ? [] : [{
    id: 17,
    logged_at: "2026-11-17T12:00:00Z",
    blood_type: "O-",
    component: "RBC",
    quantity: 1,
    reserved_units: [],
    status: "pending",
  }]));
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  expect(await screen.findByRole("link", { name: "REQ-17" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "Nov 17, 2026" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Fulfilled", exact: true }));
  expect(await screen.findByText("No requests found. Log a request to begin matching.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "All requests", exact: true }));
  expect(await screen.findByRole("link", { name: "REQ-17" })).toBeInTheDocument();
});
