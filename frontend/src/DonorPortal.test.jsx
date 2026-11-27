import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";

const profile = {donor_id: 1, full_name: "Alex Demo", blood_type: "A+", email: "alex@example.com", phone: "2025550100", status: "active"};
const history = {
  as_of: "2026-11-17", no_donation_history: false,
  eligibility: [
    {donation_type: "whole_blood", label: "Whole blood", eligible: true, next_eligible_date: "2026-11-17", last_donation_date: null},
    {donation_type: "plasma", label: "Plasma", eligible: false, next_eligible_date: "2026-12-12", last_donation_date: "2026-11-14"},
  ],
  donations: [{donation_id: 7, donation_type: "plasma", donation_date: "2026-11-14", blood_type: "A+", volume_ml: 600, recorded_by: "Jordan Lee"}],
};
const response = (data, status = 200) => Promise.resolve({ok: status < 400, status, json: () => Promise.resolve(data)});
function open(path, role = "donor") {
  localStorage.setItem("access", "test-token");
  localStorage.setItem("bloodlink-user", JSON.stringify({email: profile.email, role}));
  window.history.replaceState({}, "", path);
  return render(<App />);
}
beforeEach(() => {
  localStorage.clear();
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
  vi.stubGlobal("fetch", vi.fn(url => response(url.endsWith("/profile/") ? profile : history)));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test("overview has separate donor navigation, identity and recent history", async () => {
  open("/me");
  expect(await screen.findByText("Alex Demo")).toBeInTheDocument();
  expect(screen.getByText("Recorded donations")).toBeInTheDocument();
  expect(screen.queryByLabelText("Phone number")).not.toBeInTheDocument();
  const nav = screen.getByRole("navigation");
  expect(within(nav).getByRole("link", {name: "Overview"})).toHaveAttribute("aria-current", "page");
  fireEvent.click(within(nav).getByRole("link", {name: "Donation history"}));
  expect(await screen.findByRole("heading", {name: "Donation history"})).toBeInTheDocument();
  expect(within(nav).getByRole("link", {name: "Overview"})).not.toHaveAttribute("aria-current");
  expect(screen.getByText(/Donors cannot edit or delete/)).toBeInTheDocument();
});

test("history shows recorder and filters without inventing empty records", async () => {
  open("/me/history");
  expect(await screen.findByRole("cell", {name: "Jordan Lee"})).toBeInTheDocument();
  expect(screen.getByRole("cell", {name: "DN-0007"})).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Donation type"), {target: {value: "whole_blood"}});
  expect(screen.getByText("No matching donations")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "Show all donations"}));
  expect(screen.getByRole("cell", {name: "Jordan Lee"})).toBeInTheDocument();
});

test("new donor overview offers guidance and an honest empty history", async () => {
  vi.stubGlobal("fetch", vi.fn(url => response(url.endsWith("/profile/") ? profile : {...history, donations: [], no_donation_history: true})));
  open("/me");
  expect(await screen.findByText("No donations recorded yet")).toBeInTheDocument();
  expect(screen.getByRole("link", {name: "Review contact information"})).toHaveAttribute("href", "/me/contact");
});

test("overview opens the appointment form from the identity row", async () => {
  open("/me");
  const booking = await screen.findByRole("button", {name: "Book a donation"});
  expect(booking.closest(".donor-identity")).toHaveTextContent("Alex Demo");
  fireEvent.click(booking);
  const form = await screen.findByRole("dialog", {name: "Book a donation"});
  expect(await within(form).findByLabelText("Donation type")).toBeInTheDocument();
  fireEvent.click(within(form).getByRole("button", {name: "Close dialog"}));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(fetch.mock.calls.some(([, options]) => options.method === "POST")).toBe(false);
});

test("donor navigation opens the separate appointment page", async () => {
  vi.stubGlobal("fetch", vi.fn(url => response(url.endsWith("/appointments/") ? [] : url.endsWith("/profile/") ? profile : history)));
  open("/me");
  await screen.findByText("Alex Demo");
  const nav = within(screen.getByRole("navigation"));
  fireEvent.click(nav.getByRole("link", {name: "Donation appointments"}));
  expect(await screen.findByRole("heading", {name: "Donation appointments", level: 1})).toBeInTheDocument();
  expect(nav.getByRole("link", {name: "Donation appointments"})).toHaveAttribute("aria-current", "page");
  expect(nav.getByRole("link", {name: "Overview"})).not.toHaveAttribute("aria-current");
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => url.endsWith("/appointments/"))).toBe(true));
});

test("coordinator cannot load donor appointments", () => {
  open("/me/appointments", "coordinator");
  expect(screen.getByRole("heading", {name: "You do not have access"})).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

test("anonymous appointment access redirects to sign-in", () => {
  window.history.replaceState({}, "", "/me/appointments");
  render(<App />);
  expect(screen.getByRole("heading", {name: "Sign in to BloodLink"})).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

test("invalid contact fields stay editable, do not save, and can be cancelled", async () => {
  open("/me/contact");
  const phone = await screen.findByLabelText("Phone number");
  fireEvent.change(phone, {target: {value: "123"}});
  fireEvent.click(screen.getByRole("button", {name: "Save changes"}));
  expect(phone).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByText("Enter exactly 10 digits.")).toBeInTheDocument();
  expect(fetch.mock.calls.some(([,options]) => options.method === "PATCH")).toBe(false);
  fireEvent.click(screen.getByRole("button", {name: "Cancel changes"}));
  expect(phone).toHaveValue(profile.phone);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("server duplicate email stays inline without changing session or losing input", async () => {
  vi.stubGlobal("fetch", vi.fn((url, options) => options.method === "PATCH" ? response({email: ["An account with this email is already registered."]}, 409) : response(profile)));
  open("/me/contact");
  const email = await screen.findByLabelText("Email address");
  fireEvent.change(email, {target: {value: "taken@example.com"}});
  fireEvent.click(screen.getByRole("button", {name: "Save changes"}));
  expect(await screen.findByText("An account with this email is already registered.")).toBeInTheDocument();
  expect(email).toHaveValue("taken@example.com");
  expect(JSON.parse(localStorage.getItem("bloodlink-user")).email).toBe(profile.email);
});

test("saved email updates session and cancel restores the last saved values", async () => {
  vi.stubGlobal("fetch", vi.fn((url, options) => response(options.method === "PATCH" ? {...profile, ...JSON.parse(options.body)} : profile)));
  open("/me/contact");
  const email = await screen.findByLabelText("Email address");
  fireEvent.change(email, {target: {value: "updated@example.com"}});
  fireEvent.click(screen.getByRole("button", {name: "Save changes"}));
  await screen.findByText("Contact information saved. Your registration remains active.");
  expect(JSON.parse(localStorage.getItem("bloodlink-user")).email).toBe("updated@example.com");
  fireEvent.change(email, {target: {value: "unsaved@example.com"}});
  fireEvent.click(screen.getByRole("button", {name: "Cancel changes"}));
  expect(email).toHaveValue("updated@example.com");
});

test("profile load failure can be retried", async () => {
  vi.stubGlobal("fetch", vi.fn().mockImplementationOnce(() => response({detail: "Temporarily unavailable"}, 503)).mockImplementation(() => response(profile)));
  open("/me/contact");
  expect(await screen.findByRole("alert")).toHaveTextContent("Temporarily unavailable");
  fireEvent.click(screen.getByRole("button", {name: "Try again"}));
  await waitFor(() => expect(screen.getByLabelText("Phone number")).toHaveValue(profile.phone));
});

test("coordinator cannot load donor contact page", () => {
  open("/me/contact", "coordinator");
  expect(screen.getByText("You do not have access")).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});
