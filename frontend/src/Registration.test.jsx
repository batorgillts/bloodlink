import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";
import { birthDateToISO } from "./registration";

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState({}, "", "/register");
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
    ok: false, status: 409, json: () => Promise.resolve({email: ["Already registered."]}),
  })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function fillRegistration(confirm = "abc123456", birth = "05/12/1998") {
  render(<App />);
  fireEvent.change(screen.getByLabelText("Full name"), {target: {value: "Demo Donor"}});
  fireEvent.change(screen.getByLabelText("Email address"), {target: {value: "demo@example.com"}});
  fireEvent.change(screen.getByLabelText("Password", {exact: true}), {target: {value: "abc123456"}});
  fireEvent.change(screen.getByLabelText("Confirm password"), {target: {value: confirm}});
  fireEvent.change(screen.getByLabelText("Date of birth"), {target: {value: birth}});
  fireEvent.change(screen.getByLabelText("Phone number"), {target: {value: "2025550100"}});
}
function submit() {
  fireEvent.submit(screen.getByRole("button", {name: "Create account"}).closest("form"));
}

test("registration uses an explicit US format and sends ISO without the confirmation field", async () => {
  fillRegistration();
  expect(screen.getByLabelText("Date of birth")).toHaveAttribute("type", "text");
  expect(screen.getByLabelText("Date of birth")).toHaveAttribute("placeholder", "MM/DD/YYYY");
  submit();
  await screen.findByRole("alert");
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
    full_name: "Demo Donor", email: "demo@example.com", password: "abc123456",
    date_of_birth: "1998-05-12", blood_type: "A+", phone: "2025550100",
  });
});

test("mismatched passwords block submission and can be corrected", async () => {
  fillRegistration("different123");
  submit();
  expect(screen.getByRole("alert")).toHaveTextContent("Passwords do not match");
  expect(fetch).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Confirm password")).toHaveFocus();
  fireEvent.change(screen.getByLabelText("Confirm password"), {target: {value: "abc123456"}});
  submit();
  await screen.findByText("email: Already registered.");
  expect(fetch).toHaveBeenCalledTimes(1);
});

test("an impossible birthday is rejected without contacting the API", () => {
  fillRegistration("abc123456", "02/30/1998");
  submit();
  expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid date in MM/DD/YYYY format.");
  expect(fetch).not.toHaveBeenCalled();
});

test.each([
  ["02/29/2000", "2000-02-29"], ["02/29/1900", null], ["12/31/1998", "1998-12-31"],
  ["31/12/1998", null], ["1998-05-12", null], ["00/12/1998", null], ["01/00/1998", null],
])("birth date %s converts without locale ambiguity", (input, expected) => {
  expect(birthDateToISO(input)).toBe(expected);
});
