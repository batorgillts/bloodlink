import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";
import { StockAlerts } from "./StockAlerts";

const response = (data, status = 200) =>
  Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(data) });

const dashboard = {
  low_stock: [{ blood_type: "O-", component: "RBC", available: 1, minimum_units: 3 }],
  expiring_soon: [
    { component: "RBC", label: "Red blood cells", window_days: 7, overrides: [], units: [
      { id: 1, unit_code: "RBC-SOON", blood_type: "O-", component: "RBC", expires_at: "2026-11-27T10:00:00Z", window_days: 7 },
    ] },
    { component: "PLASMA", label: "Plasma", window_days: 30, units: [] },
    { component: "PLATELETS", label: "Platelets", window_days: 2, units: [] },
  ],
  stock: [
    { blood_type: "O-", component: "RBC", available: 1, minimum_units: 3, is_low: true, expiring_soon_days: 7,
      closest_to_expiry: { unit_code: "RBC-SOON", expires_at: "2026-11-27T10:00:00Z" } },
    { blood_type: "A+", component: "RBC", available: 0, minimum_units: null, is_low: false, expiring_soon_days: 7, closest_to_expiry: null },
  ],
};

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState({}, "", "/login");
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test("AC2/AC3: shows the low-stock alert, expiring units by component and closest to expiry", async () => {
  vi.stubGlobal("fetch", vi.fn(() => response(dashboard)));
  render(<StockAlerts />);
  expect(await screen.findByText("Low stock: O- Red blood cells")).toBeInTheDocument();
  expect(screen.getByText(/1 available, alert below 3/)).toBeInTheDocument();
  const rbc = screen.getByRole("heading", { name: /Red blood cells \(within 7 days by default\)/ }).parentElement;
  expect(within(rbc).getByText("RBC-SOON")).toBeInTheDocument();
  expect(screen.getByText("No plasma expiring soon.")).toBeInTheDocument();
  expect(screen.getByText("Low stock", { selector: ".badge" })).toBeInTheDocument();
  expect(screen.getByText(/RBC-SOON · /)).toBeInTheDocument();
  // A+ has no units and no threshold, so it is left out of the stock table.
  expect(screen.queryByText("Not set")).not.toBeInTheDocument();
});

test("no alerts shows a calm message", async () => {
  vi.stubGlobal("fetch", vi.fn(() => response({ ...dashboard, low_stock: [] })));
  render(<StockAlerts />);
  expect(await screen.findByText(/No low-stock alerts/)).toBeInTheDocument();
});

test("AC1: saving a threshold sends it and refreshes the dashboard", async () => {
  const fetch = vi.fn((url, options = {}) => {
    if (url.endsWith("/thresholds/") && options.method === "PUT")
      return response({ id: 1, blood_type: "O-", component: "RBC", minimum_units: 4, expiring_soon_days: null }, 201);
    if (url.endsWith("/thresholds/")) return response([]);
    return response(dashboard);
  });
  vi.stubGlobal("fetch", fetch);
  render(<StockAlerts />);
  fireEvent.click(await screen.findByRole("button", { name: "Alert settings" }));
  fireEvent.change(screen.getByLabelText("Blood type"), { target: { value: "O-" } });
  fireEvent.change(screen.getByLabelText("Component"), { target: { value: "RBC" } });
  fireEvent.change(screen.getByLabelText("Alert when available units drop below"), { target: { value: "4" } });
  fireEvent.click(screen.getByRole("button", { name: "Save threshold" }));
  expect(await screen.findByText(/Saved: alert when O- Red blood cells drops below 4 units/)).toBeInTheDocument();
  const put = fetch.mock.calls.find(([, o]) => o?.method === "PUT");
  expect(JSON.parse(put[1].body)).toEqual({ blood_type: "O-", component: "RBC", minimum_units: "4", expiring_soon_days: null });
  const dashboardCalls = fetch.mock.calls.filter(([u]) => u.endsWith("/inventory/dashboard/"));
  expect(dashboardCalls.length).toBeGreaterThan(1);
});

test("AC5: a threshold that is not positive is stopped before it is sent", async () => {
  const fetch = vi.fn((url) => response(url.endsWith("/thresholds/") ? [] : dashboard));
  vi.stubGlobal("fetch", fetch);
  render(<StockAlerts />);
  fireEvent.click(await screen.findByRole("button", { name: "Alert settings" }));
  fireEvent.change(screen.getByLabelText("Alert when available units drop below"), { target: { value: "0" } });
  fireEvent.click(screen.getByRole("button", { name: "Save threshold" }));
  expect(await screen.findByText("Enter a value of 1 or greater.")).toBeInTheDocument();
  expect(fetch.mock.calls.some(([, o]) => o?.method === "PUT")).toBe(false);
});

test("AC5: the server's validation message is shown", async () => {
  const fetch = vi.fn((url, options = {}) => {
    if (options.method === "PUT")
      return response({ minimum_units: ["The low-stock threshold must be a positive whole number."] }, 400);
    return response(url.endsWith("/thresholds/") ? [] : dashboard);
  });
  vi.stubGlobal("fetch", fetch);
  render(<StockAlerts />);
  fireEvent.click(await screen.findByRole("button", { name: "Alert settings" }));
  fireEvent.change(screen.getByLabelText("Alert when available units drop below"), { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "Save threshold" }));
  expect(await screen.findByText(/The low-stock threshold must be a positive whole number/)).toBeInTheDocument();
});

test("alerts have a separate coordinator page and refresh after inventory changes", async () => {
  localStorage.setItem("access", "test-access");
  localStorage.setItem("bloodlink-user", JSON.stringify({ email: "demo@example.com", role: "coordinator" }));
  window.history.replaceState({}, "", "/inventory");
  let discarded = false;
  const fetch = vi.fn((url) => {
    if (url.endsWith("/discard/")) { discarded = true; return response({}); }
    if (url.endsWith("/inventory/dashboard/"))
      return response(discarded ? { ...dashboard, expiring_soon: dashboard.expiring_soon.map((g) => ({ ...g, units: [] })) } : dashboard);
    return response([{ id: 1, unit_code: "RBC-SOON", blood_type: "O-", component: "RBC", status: discarded ? "discarded" : "available", can_discard: !discarded, discard_reason: discarded ? "damaged" : "" }]);
  });
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  await screen.findByRole("button", { name: "Discard RBC-SOON" });
  expect(screen.getByLabelText("Search inventory")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Low-stock alerts" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Alert settings" })).not.toBeInTheDocument();
  expect(fetch.mock.calls.some(([url]) => url.endsWith("/inventory/dashboard/"))).toBe(false);
  const navigation = within(screen.getByRole("navigation", { name: "Main navigation" }));
  expect(navigation.getByRole("link", { name: /Blood inventory/ })).toHaveAttribute("aria-current", "page");
  expect(navigation.getByRole("link", { name: /Inventory alerts/ })).toHaveAttribute("href", "/inventory-alerts");

  fireEvent.click(navigation.getByRole("link", { name: /Inventory alerts/ }));
  expect(await screen.findByRole("heading", { name: "Inventory alerts", level: 1 })).toBeInTheDocument();
  const rbcHeading = await screen.findByRole("heading", { name: /Red blood cells \(within 7 days by default\)/ });
  expect(within(rbcHeading.parentElement).getByText("RBC-SOON")).toBeInTheDocument();
  expect(screen.queryByLabelText("Search inventory")).not.toBeInTheDocument();
  expect(navigation.getByRole("link", { name: /Inventory alerts/ })).toHaveAttribute("aria-current", "page");
  expect(navigation.getByRole("link", { name: /Blood inventory/ })).not.toHaveAttribute("aria-current");

  fireEvent.click(navigation.getByRole("link", { name: /Blood inventory/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Discard RBC-SOON" }));
  fireEvent.change(screen.getByLabelText("Discard reason"), { target: { value: "damaged" } });
  fireEvent.click(screen.getByRole("button", { name: "Discard unit", exact: true }));
  await screen.findByText("Unit discarded. Any affected request has been updated.");
  await waitFor(() => expect(screen.queryByRole("button", { name: "Discard RBC-SOON" })).not.toBeInTheDocument());

  fireEvent.click(navigation.getByRole("link", { name: /Inventory alerts/ }));
  expect(await screen.findByText("No red blood cells expiring soon.")).toBeInTheDocument();
  expect(fetch.mock.calls.filter(([url]) => url.endsWith("/inventory/dashboard/")).length).toBe(2);
});

test.each(["donor", "anonymous"])("%s cannot load the inventory alerts page", async (role) => {
  if (role === "donor") {
    localStorage.setItem("access", "test-access");
    localStorage.setItem("bloodlink-user", JSON.stringify({ email: "demo@example.com", role }));
  }
  window.history.replaceState({}, "", "/inventory-alerts");
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  expect(await screen.findByRole("heading", {
    name: role === "donor" ? "You do not have access" : "Sign in to BloodLink",
  })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /Inventory alerts/ })).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

test("review: a blood type's own window is shown, not just the default", async () => {
  const withOverride = {
    ...dashboard,
    expiring_soon: [
      { component: "RBC", label: "Red blood cells", window_days: 7,
        overrides: [{ blood_type: "O-", window_days: 14 }],
        units: [{ id: 2, unit_code: "RBC-TEN", blood_type: "O-", component: "RBC", expires_at: "2026-12-05T10:00:00Z", window_days: 14 }] },
      ...dashboard.expiring_soon.slice(1),
    ],
  };
  vi.stubGlobal("fetch", vi.fn(() => response(withOverride)));
  render(<StockAlerts />);
  expect(await screen.findByRole("heading", { name: /Red blood cells \(within 7 days by default\)/ })).toBeInTheDocument();
  expect(screen.getByText("Own window: O- 14 days")).toBeInTheDocument();
  expect(screen.getByText("14 days (O- setting)")).toBeInTheDocument();
});
