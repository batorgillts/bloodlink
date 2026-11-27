import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { CoordinatorAppointments, RecordAppointmentUnit } from "./CoordinatorAppointments";

const appointment = {
  id: 7,
  donor: { id: 4, full_name: "Anna Chen", email: "anna@example.com", blood_type: "A+" },
  donation_type: "whole_blood", donation_type_label: "Whole blood", allowed_components: ["RBC", "PLASMA"],
  appointment_date: "2026-11-26", appointment_time: "19:15", scheduled_at: "2026-11-27T00:15:00Z",
  timezone: "America/New_York", status: "scheduled", can_record: true, can_cancel: true,
  donation_id: null, unit_id: null, unit_code: "", cancellation_reason: "",
};
const metadata = {
  donation_types: [
    { donation_type: "whole_blood", label: "Whole blood", allowed_components: ["RBC", "PLASMA"] },
    { donation_type: "plasma", label: "Plasma", allowed_components: ["PLASMA"] },
  ],
  timezone: "America/New_York", as_of: "2026-11-26T19:00:00-05:00",
};
const response = (data, status = 200) => Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(data) });
const list = (rows = [appointment]) => ({ ...metadata, appointments: rows });
const completed = { ...appointment, status: "completed", can_record: false, can_cancel: false, unit_code: "APPT-UNIT-7", unit_id: 9, donation_id: 12 };
const recorded = { appointment: completed, unit: { id: 9, unit_code: "APPT-UNIT-7" } };
function openPage() { return render(<MemoryRouter><CoordinatorAppointments /></MemoryRouter>); }
function fillRecord({ code = "APPT-UNIT-7", volume = "450", component = "PLASMA", day, time } = {}) {
  fireEvent.change(screen.getByLabelText("Unique unit code"), { target: { value: code } });
  fireEvent.change(screen.getByLabelText("Donation volume (mL)"), { target: { value: volume } });
  fireEvent.change(screen.getByRole("combobox", { name: "Component" }), { target: { value: component } });
  if (day !== undefined) fireEvent.change(screen.getByLabelText("Collection date"), { target: { value: day } });
  if (time !== undefined) fireEvent.change(screen.getByLabelText("Collection time"), { target: { value: time } });
}
const mutationCalls = () => fetch.mock.calls.filter(([, options]) => options?.method === "POST");

beforeEach(() => {
  localStorage.clear();
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test("coordinator filters combine encoded fuzzy search, donation type, blood type and status, then clear", async () => {
  vi.stubGlobal("fetch", vi.fn(url => response(list(String(url).includes("?") ? [] : [appointment]))));
  openPage();
  await screen.findByRole("link", { name: "Anna Chen" });
  expect(screen.getByText("Nov 26, 2026 at 19:15")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Search appointments"), { target: { value: "  anna+demo@  " } });
  fireEvent.change(screen.getByLabelText("Donation type"), { target: { value: "whole_blood" } });
  fireEvent.change(screen.getByLabelText("Blood type"), { target: { value: "A+" } });
  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "in_progress" } });
  fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
  await screen.findByText("No appointments match these filters.");
  const params = new URL(String(fetch.mock.calls.at(-1)[0]), "http://localhost").searchParams;
  expect(Object.fromEntries(params)).toEqual({ search: "anna+demo@", donation_type: "whole_blood", blood_type: "A+", status: "in_progress" });
  expect(screen.getByLabelText("Donation type")).toHaveValue("whole_blood");
  for (const label of ["Search appointments", "Donation type", "Blood type", "Status"]) {
    fireEvent.change(screen.getByLabelText(label), { target: { value: "" } });
  }
  fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
  await screen.findByRole("link", { name: "Anna Chen" });
  expect(String(fetch.mock.calls.at(-1)[0])).toMatch(/\/api\/appointments\/$/);
});

test("record form fixes donor identity and donation type, limits components and sends only collection fields", async () => {
  vi.stubGlobal("fetch", vi.fn(() => response(recorded, 201)));
  const onRecorded = vi.fn();
  render(<RecordAppointmentUnit appointment={{ ...appointment, status: "in_progress" }} onClose={vi.fn()} onRecorded={onRecorded} />);
  const dialog = screen.getByRole("dialog", { name: "Record blood unit" });
  expect(within(dialog).getByText("Anna Chen")).toBeInTheDocument();
  expect(within(dialog).getByText("anna@example.com")).toBeInTheDocument();
  expect(within(dialog).getByText("Whole blood")).toBeInTheDocument();
  expect(within(dialog).getByText("A+")).toBeInTheDocument();
  expect(within(dialog).queryByRole("combobox", { name: "Donation type" })).not.toBeInTheDocument();
  expect(within(dialog).queryByLabelText("Blood type")).not.toBeInTheDocument();
  expect(within(dialog).queryByLabelText("Donation record")).not.toBeInTheDocument();
  expect(within(dialog).queryByRole("searchbox")).not.toBeInTheDocument();
  expect(within(screen.getByRole("combobox", { name: "Component" })).getAllByRole("option").map(option => option.value)).toEqual(["RBC", "PLASMA"]);
  expect(screen.getByLabelText("Collection date")).toHaveValue("11/26/2026");
  expect(screen.getByLabelText("Collection time")).toHaveValue("19:15");
  fillRecord({ day: "11/25/2026", time: "14:30" });
  fireEvent.click(screen.getByRole("button", { name: "Record unit" }));
  await waitFor(() => expect(onRecorded).toHaveBeenCalledWith(recorded));
  const [url, options] = mutationCalls()[0];
  expect(url).toMatch(/\/api\/appointments\/7\/record\/$/);
  expect(JSON.parse(options.body)).toEqual({ unit_code: "APPT-UNIT-7", volume_ml: 450, component: "PLASMA", collected_date: "2026-11-25", collected_time: "14:30" });
});

test.each([
  ["0", "19:15", "Enter a value of 1 or greater."],
  ["1.5", "19:15", "Enter a whole number."],
  ["450", "24:00", "Enter a valid time in HH:mm format (24-hour time)."],
])("invalid collection volume/time is rejected before submitting: %s %s", (volume, time, message) => {
  vi.stubGlobal("fetch", vi.fn());
  render(<RecordAppointmentUnit appointment={appointment} onClose={vi.fn()} onRecorded={vi.fn()} />);
  fillRecord({ volume, time });
  fireEvent.click(screen.getByRole("button", { name: "Record unit" }));
  expect(screen.getByText(message)).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

test("server collection-time errors keep the record form and all entered values", async () => {
  vi.stubGlobal("fetch", vi.fn(() => response({ collected_time: ["Collection time cannot be in the future."] }, 400)));
  const onRecorded = vi.fn();
  render(<RecordAppointmentUnit appointment={appointment} onClose={vi.fn()} onRecorded={onRecorded} />);
  fillRecord({ time: "23:30" });
  fireEvent.click(screen.getByRole("button", { name: "Record unit" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Collection time cannot be in the future.");
  expect(screen.getByLabelText("Unique unit code")).toHaveValue("APPT-UNIT-7");
  expect(screen.getByLabelText("Donation volume (mL)")).toHaveValue("450");
  expect(screen.getByLabelText("Component")).toHaveValue("PLASMA");
  expect(screen.getByLabelText("Collection time")).toHaveValue("23:30");
  expect(screen.getByRole("button", { name: "Record unit" })).toBeEnabled();
  expect(onRecorded).not.toHaveBeenCalled();
});

test("recording prevents duplicate submissions while a request is pending", async () => {
  let finish;
  vi.stubGlobal("fetch", vi.fn(() => new Promise(resolve => {
    finish = () => resolve({ ok: true, status: 201, json: () => Promise.resolve(recorded) });
  })));
  const onRecorded = vi.fn();
  render(<RecordAppointmentUnit appointment={appointment} onClose={vi.fn()} onRecorded={onRecorded} />);
  fillRecord();
  const form = screen.getByRole("button", { name: "Record unit" }).closest("form");
  fireEvent.submit(form);
  expect(screen.getByRole("button", { name: "Recording…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Close dialog" })).toBeDisabled();
  fireEvent.submit(form);
  expect(mutationCalls()).toHaveLength(1);
  finish();
  await waitFor(() => expect(onRecorded).toHaveBeenCalledOnce());
});

test.each(["2026-11-27", "2020-01-01"])("starting, closing, resuming and recording works for appointment date %s", async (day) => {
  let current = { ...appointment, appointment_date: day, scheduled_at: `${day}T14:30:00-05:00` };
  vi.stubGlobal("fetch", vi.fn((url) => {
    if (url.endsWith("/start/")) { current = { ...current, status: "in_progress" }; return response(current); }
    if (url.endsWith("/record/")) { current = completed; return response(recorded, 201); }
    return response(list([current]));
  }));
  openPage();
  fireEvent.click(await screen.findByRole("button", { name: "Record blood unit for appointment 7" }));
  await screen.findByRole("dialog", { name: "Record blood unit" });
  expect(mutationCalls()[0][0]).toMatch(/\/appointments\/7\/start\/$/);
  expect(screen.getByText(/You can close this form and continue recording later/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Close", exact: true }));
  expect(await screen.findByText("In progress", { selector: ".badge" })).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Record blood unit for appointment 7" }));
  await screen.findByRole("dialog", { name: "Record blood unit" });
  fillRecord();
  fireEvent.click(screen.getByRole("button", { name: "Record unit" }));
  expect(await screen.findByText("Unit APPT-UNIT-7 recorded. Appointment completed.")).toBeInTheDocument();
  expect(await screen.findByText("Completed", { selector: ".badge" })).toBeInTheDocument();
  expect(screen.getByText("APPT-UNIT-7", { selector: "strong" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Record blood unit for appointment 7" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Cancel appointment 7" })).not.toBeInTheDocument();
  expect(mutationCalls().filter(([url]) => url.endsWith("/start/"))).toHaveLength(2);
});

test("a rejected start does not open a recording form and refreshes a manually cancelled appointment", async () => {
  let cancelled = false;
  vi.stubGlobal("fetch", vi.fn(url => {
    if (url.endsWith("/start/")) { cancelled = true; return response({ detail: "The appointment has already been cancelled." }, 409); }
    return response(list([{ ...appointment, ...(cancelled ? { status: "cancelled", can_record: false, can_cancel: false, cancellation_reason: "coordinator" } : {}) }]));
  }));
  openPage();
  fireEvent.click(await screen.findByRole("button", { name: "Record blood unit for appointment 7" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("The appointment has already been cancelled.");
  expect(await screen.findByText("Cancelled by coordinator")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Record blood unit for appointment 7" })).not.toBeInTheDocument();
});

test("coordinator cancellation requires confirmation and reloads the cancelled record", async () => {
  let cancelled = false;
  vi.stubGlobal("fetch", vi.fn(url => {
    if (url.endsWith("/cancel/")) { cancelled = true; return response({ ...appointment, status: "cancelled" }); }
    return response(list([{ ...appointment, ...(cancelled ? { status: "cancelled", can_record: false, can_cancel: false, cancellation_reason: "coordinator" } : {}) }]));
  }));
  openPage();
  fireEvent.click(await screen.findByRole("button", { name: "Cancel appointment 7" }));
  const dialog = screen.getByRole("dialog", { name: "Cancel appointment?" });
  expect(dialog).toHaveTextContent("Anna Chen");
  expect(mutationCalls()).toHaveLength(0);
  fireEvent.click(within(dialog).getByRole("button", { name: "Keep appointment" }));
  expect(mutationCalls()).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Cancel appointment 7" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel appointment", exact: true }));
  expect(await screen.findByText("Appointment cancelled.")).toBeInTheDocument();
  expect(await screen.findByText("Cancelled by coordinator")).toBeInTheDocument();
  expect(JSON.parse(mutationCalls()[0][1].body)).toEqual({ confirm: true });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("cancellation failure leaves the confirmation open and the original record visible", async () => {
  vi.stubGlobal("fetch", vi.fn(url => url.endsWith("/cancel/")
    ? response({ detail: "This appointment has already been completed." }, 409)
    : response(list())));
  openPage();
  fireEvent.click(await screen.findByRole("button", { name: "Cancel appointment 7" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel appointment", exact: true }));
  expect(await screen.findByRole("alert")).toHaveTextContent("This appointment has already been completed.");
  expect(screen.getByRole("dialog", { name: "Cancel appointment?" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Keep appointment" })).toBeEnabled();
});

test("appointments load failures can be retried without losing the filter controls", async () => {
  vi.stubGlobal("fetch", vi.fn().mockImplementationOnce(() => response({ detail: "Appointments temporarily unavailable." }, 503)).mockImplementation(() => response(list([]))));
  openPage();
  expect(await screen.findByRole("alert")).toHaveTextContent("Appointments temporarily unavailable.");
  expect(screen.getByLabelText("Search appointments")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("No donation appointments yet.")).toBeInTheDocument();
});
