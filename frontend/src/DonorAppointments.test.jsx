import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AppointmentForm, DonorAppointments } from "./DonorAppointments";

const eligibility = {
  as_of: "2026-11-26",
  eligibility: [
    { donation_type: "whole_blood", label: "Whole blood", eligible: true, next_eligible_date: "2026-11-20" },
    { donation_type: "plasma", label: "Plasma", eligible: false, next_eligible_date: "2026-12-12" },
  ],
};
const appointment = {
  id: 4, donation_type: "plasma", donation_type_label: "Plasma",
  appointment_date: "2026-12-12", appointment_time: "09:30", scheduled_at: "2026-12-12T09:30:00-05:00",
  timezone: "America/New_York", status: "scheduled", can_modify: true,
};
const response = (data, status = 200) => Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(data) });
function fillForm({ type = "plasma", day = "12/12/2026", time = "09:30" } = {}) {
  fireEvent.change(screen.getByRole("combobox", { name: "Donation type" }), { target: { value: type } });
  fireEvent.change(screen.getByLabelText("Appointment date"), { target: { value: day } });
  fireEvent.change(screen.getByLabelText("Appointment time"), { target: { value: time } });
}
const writes = () => fetch.mock.calls.filter(([, options]) => options?.method !== "GET");

beforeEach(() => {
  localStorage.clear();
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test("a donor who is not eligible today can book on the earliest eligible date in bank time", async () => {
  const saved = vi.fn();
  vi.stubGlobal("fetch", vi.fn((url, options) => response(options.method === "POST" ? appointment : eligibility)));
  render(<AppointmentForm onClose={vi.fn()} onSaved={saved} />);
  await screen.findByRole("option", { name: "Plasma" });
  fillForm();
  expect(screen.getByText("Dec 12, 2026")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
  await waitFor(() => expect(saved).toHaveBeenCalledWith(appointment));
  const [url, options] = writes()[0];
  expect(url).toMatch(/\/api\/donors\/me\/appointments\/$/);
  expect(JSON.parse(options.body)).toEqual({ donation_type: "plasma", appointment_date: "2026-12-12", appointment_time: "09:30" });
  expect(writes()).toHaveLength(1);
});

test("booking before the chosen type's eligibility date is blocked and a type change clears the old error", async () => {
  vi.stubGlobal("fetch", vi.fn(() => response(eligibility)));
  render(<AppointmentForm onClose={vi.fn()} onSaved={vi.fn()} />);
  await screen.findByRole("option", { name: "Plasma" });
  fillForm({ day: "12/11/2026" });
  fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
  expect(screen.getByText("Choose Dec 12, 2026 or later for Plasma.")).toBeInTheDocument();
  expect(screen.getByLabelText("Appointment date")).toHaveAttribute("aria-invalid", "true");
  expect(writes()).toHaveLength(0);
  fireEvent.change(screen.getByLabelText("Donation type"), { target: { value: "whole_blood" } });
  expect(screen.queryByText("Choose Dec 12, 2026 or later for Plasma.")).not.toBeInTheDocument();
  expect(screen.getByText("Nov 26, 2026")).toBeInTheDocument();
});

test.each([
  ["11/25/2026", "09:30", "Choose Nov 26, 2026 or later for Whole blood."],
  ["12/12/2026", "24:00", "Enter a valid time in HH:mm format (24-hour time)."],
  ["12/12/2026", "09:70", "Enter a valid time in HH:mm format (24-hour time)."],
])("invalid booking date/time is blocked: %s %s", async (day, time, message) => {
  vi.stubGlobal("fetch", vi.fn(() => response(eligibility)));
  render(<AppointmentForm onClose={vi.fn()} onSaved={vi.fn()} />);
  await screen.findByRole("option", { name: "Whole blood" });
  fillForm({ type: "whole_blood", day, time });
  fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
  expect(screen.getByText(message)).toBeInTheDocument();
  expect(writes()).toHaveLength(0);
});

test("eligibility load failure blocks booking and can be retried", async () => {
  vi.stubGlobal("fetch", vi.fn().mockImplementationOnce(() => response({ detail: "Eligibility is unavailable." }, 503)).mockImplementation(() => response(eligibility)));
  render(<AppointmentForm onClose={vi.fn()} onSaved={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Eligibility is unavailable.");
  expect(screen.getByRole("button", { name: "Book appointment" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByRole("option", { name: "Plasma" });
  fillForm();
  expect(screen.getByRole("button", { name: "Book appointment" })).toBeEnabled();
});

test("edit pre-fills bank-local values, rechecks eligibility, and PATCHes only the booking fields", async () => {
  const saved = vi.fn();
  const updated = { ...appointment, appointment_date: "2026-12-13", appointment_time: "14:30" };
  vi.stubGlobal("fetch", vi.fn((url, options) => response(options.method === "PATCH" ? updated : eligibility)));
  render(<AppointmentForm appointment={appointment} onClose={vi.fn()} onSaved={saved} />);
  await screen.findByRole("option", { name: "Plasma" });
  expect(screen.getByLabelText("Appointment date")).toHaveValue("12/12/2026");
  expect(screen.getByLabelText("Appointment time")).toHaveValue("09:30");
  fillForm({ day: "12/13/2026", time: "14:30" });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(saved).toHaveBeenCalledWith(updated));
  const [url, options] = writes()[0];
  expect(url).toMatch(/\/appointments\/4\/$/);
  expect(options.method).toBe("PATCH");
  expect(JSON.parse(options.body)).toEqual({ donation_type: "plasma", appointment_date: "2026-12-13", appointment_time: "14:30" });
});

test("a server eligibility rejection preserves the draft and refreshes the earliest date", async () => {
  let rejected = false;
  vi.stubGlobal("fetch", vi.fn((url, options) => {
    if (options.method === "POST") {
      rejected = true;
      return response({ appointment_date: ["Your earliest eligible date is now 2026-12-20."] }, 400);
    }
    return response(rejected ? {
      ...eligibility,
      eligibility: eligibility.eligibility.map(row => row.donation_type === "plasma" ? { ...row, next_eligible_date: "2026-12-20" } : row),
    } : eligibility);
  }));
  const saved = vi.fn();
  render(<AppointmentForm onClose={vi.fn()} onSaved={saved} />);
  await screen.findByRole("option", { name: "Plasma" });
  fillForm();
  fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
  expect(await screen.findByText("Dec 20, 2026")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Your earliest eligible date is now 2026-12-20.");
  expect(screen.getByLabelText("Appointment date")).toHaveValue("12/12/2026");
  expect(screen.getByLabelText("Appointment time")).toHaveValue("09:30");
  expect(screen.getByRole("button", { name: "Book appointment" })).toBeEnabled();
  expect(saved).not.toHaveBeenCalled();
});

test("saving disables controls and prevents duplicate submissions", async () => {
  let finish;
  vi.stubGlobal("fetch", vi.fn((url, options) => options.method === "POST"
    ? new Promise(resolve => { finish = () => resolve({ ok: true, status: 201, json: () => Promise.resolve(appointment) }); })
    : response(eligibility)));
  const saved = vi.fn();
  render(<AppointmentForm onClose={vi.fn()} onSaved={saved} />);
  await screen.findByRole("option", { name: "Plasma" });
  fillForm();
  const form = screen.getByRole("button", { name: "Book appointment" }).closest("form");
  fireEvent.submit(form);
  expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Close dialog" })).toBeDisabled();
  fireEvent.submit(form);
  expect(writes()).toHaveLength(1);
  finish();
  await waitFor(() => expect(saved).toHaveBeenCalledOnce());
});

test("past scheduled appointments stay active and await coordinator review", async () => {
  vi.stubGlobal("fetch", vi.fn(() => response([
    appointment,
    { ...appointment, id: 5, status: "cancelled", can_modify: false },
    { ...appointment, id: 6, appointment_date: "2026-11-01", scheduled_at: "2026-11-01T09:30:00-05:00", can_modify: false },
  ])));
  render(<DonorAppointments />);
  const upcoming = await screen.findByRole("region", { name: "Active appointments" });
  const previous = screen.getByRole("region", { name: "Appointment history" });
  expect(within(upcoming).getByText("Appointment #4")).toBeInTheDocument();
  expect(within(upcoming).getByRole("button", { name: "Edit appointment 4" })).toBeInTheDocument();
  expect(within(previous).getByText("Appointment #5")).toBeInTheDocument();
  expect(within(upcoming).getByText("Appointment #6")).toBeInTheDocument();
  expect(within(upcoming).getByText("Awaiting coordinator review.")).toBeInTheDocument();
  expect(within(upcoming).queryByRole("button", { name: "Edit appointment 6" })).not.toBeInTheDocument();
  expect(within(previous).queryByText("Appointment #6")).not.toBeInTheDocument();
  expect(within(previous).queryByRole("button")).not.toBeInTheDocument();
  expect(screen.getByText(/Completed donations appear in Donation history/)).toBeInTheDocument();
});

test("coordinator progress stays active while completed and historical cancellations show their outcomes", async () => {
  vi.stubGlobal("fetch", vi.fn(() => response([
    { ...appointment, status: "in_progress", can_modify: false },
    { ...appointment, id: 5, status: "completed", can_modify: false },
    { ...appointment, id: 6, status: "cancelled", cancellation_reason: "expired", can_modify: false },
    { ...appointment, id: 7, status: "cancelled", cancellation_reason: "coordinator", can_modify: false },
  ])));
  render(<DonorAppointments />);
  const active = await screen.findByRole("region", { name: "Active appointments" });
  const history = screen.getByRole("region", { name: "Appointment history" });
  expect(within(active).getByText("In progress")).toBeInTheDocument();
  expect(within(active).getByText("The blood bank has started recording this appointment.")).toBeInTheDocument();
  expect(within(active).queryByRole("button")).not.toBeInTheDocument();
  expect(within(history).getByText("Completed")).toBeInTheDocument();
  expect(within(history).getByText("Cancelled after the appointment time.")).toBeInTheDocument();
  expect(within(history).getByText("Cancelled by the blood bank coordinator.")).toBeInTheDocument();
  expect(within(history).queryByRole("button")).not.toBeInTheDocument();
});

test("cancellation requires confirmation, persists via API, and reloads the list", async () => {
  let cancelled = false;
  vi.stubGlobal("fetch", vi.fn((url, options) => {
    if (options.method === "POST") {
      cancelled = true;
      return response({ ...appointment, status: "cancelled", can_modify: false });
    }
    return response([{ ...appointment, status: cancelled ? "cancelled" : "scheduled", can_modify: !cancelled }]);
  }));
  render(<DonorAppointments />);
  fireEvent.click(await screen.findByRole("button", { name: "Cancel appointment 4" }));
  expect(screen.getByRole("dialog", { name: "Cancel appointment?" })).toBeInTheDocument();
  expect(writes()).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Keep appointment" }));
  expect(writes()).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Cancel appointment 4" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel appointment", exact: true }));
  expect(await screen.findByText("Appointment cancelled.")).toBeInTheDocument();
  const [url, options] = writes()[0];
  expect(url).toMatch(/\/appointments\/4\/cancel\/$/);
  expect(JSON.parse(options.body)).toEqual({ confirm: true });
  expect(await screen.findByText("No active appointments")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Appointment history" })).getByText("Appointment #4")).toBeInTheDocument();
});

test("a failed cancellation stays open and does not remove the appointment", async () => {
  vi.stubGlobal("fetch", vi.fn((url, options) => options.method === "POST"
    ? response({ detail: "This appointment can no longer be cancelled." }, 409)
    : response([appointment])));
  render(<DonorAppointments />);
  fireEvent.click(await screen.findByRole("button", { name: "Cancel appointment 4" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel appointment", exact: true }));
  const dialog = screen.getByRole("dialog", { name: "Cancel appointment?" });
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("This appointment can no longer be cancelled.");
  expect(screen.getByText("Appointment #4")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Keep appointment" })).toBeEnabled();
});

test("an empty appointments page can book and show the newly saved appointment", async () => {
  let booked = false;
  vi.stubGlobal("fetch", vi.fn((url, options) => {
    if (url.endsWith("/eligibility/")) return response(eligibility);
    if (options.method === "POST") { booked = true; return response(appointment); }
    return response(booked ? [appointment] : []);
  }));
  render(<DonorAppointments />);
  await screen.findByText("No active appointments");
  fireEvent.click(screen.getByRole("button", { name: "Book a donation" }));
  await screen.findByRole("option", { name: "Plasma" });
  fillForm();
  fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
  expect(await screen.findByText("Appointment booked.")).toBeInTheDocument();
  expect(await screen.findByText("Appointment #4")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
