import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Field, Form } from "./ui";
import { fieldError, isoToUS, localDateTimeToISO } from "./formValidation";

afterEach(cleanup);

test("empty required fields use accessible English errors without native validation tooltips", () => {
  const submit = vi.fn(e => e.preventDefault());
  render(<Form onSubmit={submit}><Field label="Email" name="email" type="email" required /><button>Save</button></Form>);
  const input = screen.getByLabelText("Email");
  expect(input.validationMessage).toBe("");
  expect(input).toHaveAttribute("aria-required", "true");
  fireEvent.click(screen.getByText("Save"));
  expect(submit).not.toHaveBeenCalled();
  expect(input).toHaveFocus();
  expect(input).toHaveAccessibleDescription("This field is required.");
  fireEvent.change(input, {target: {value: "invalid"}});
  fireEvent.click(screen.getByText("Save"));
  expect(input.validationMessage).toBe("");
  expect(input).toHaveAccessibleDescription("Enter a valid email address, such as name@example.com.");
  fireEvent.change(input, {target: {value: "donor@example.com"}});
  fireEvent.click(screen.getByText("Save"));
  expect(submit).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("numeric, phone and calendar constraints remain enforced in English", () => {
  const submit = vi.fn(e => e.preventDefault());
  render(<Form onSubmit={submit}>
    <Field label="Volume" name="volume" type="number" min="1" step="1" defaultValue="0" />
    <Field label="Phone" name="phone" pattern="[0-9]{10}" defaultValue="bad" />
    <Field label="Date" name="date" type="date" defaultValue="02/30/2000" />
    <Field label="Collection" name="collection" type="datetime-local" defaultValue="02/29/2000 25:00" />
    <button>Save</button>
  </Form>);
  fireEvent.click(screen.getByText("Save"));
  expect(submit).not.toHaveBeenCalled();
  expect(screen.getByText("Enter a value of 1 or greater.")).toBeInTheDocument();
  expect(screen.getByText("Enter exactly 10 digits.")).toBeInTheDocument();
  expect(screen.getByText("Enter a valid date in MM/DD/YYYY format.")).toBeInTheDocument();
  expect(screen.getByText(/Enter a valid date and time/)).toBeInTheDocument();
  for (const input of screen.getAllByRole("textbox")) expect(input.validationMessage).toBe("");
});

test("ISO dates are displayed in US order and local collection times preserve their meaning", () => {
  render(<Field label="Date" name="date" type="date" defaultValue="1998-05-12" />);
  expect(screen.getByLabelText("Date")).toHaveValue("05/12/1998");
  expect(isoToUS("2000-02-29")).toBe("02/29/2000");
  expect(localDateTimeToISO("02/29/2000 13:45")).toBe(new Date(2000, 1, 29, 13, 45).toISOString());
  expect(localDateTimeToISO("02/29/1900 13:45")).toBeNull();
  expect(localDateTimeToISO("12/31/2000 24:00")).toBeNull();
});

test.each([
  [{fieldType: "number", step: "1"}, "1.5", "Enter a whole number."],
  [{fieldType: "number"}, "abc", "Enter a valid number."],
  [{minLength: "8"}, "short", "Use at least 8 characters."],
  [{maxLength: "10"}, "12345678901", "Use no more than 10 characters."],
])("constraints %j return English feedback", (dataset, value, expected) => {
  expect(fieldError({dataset, value})).toBe(expected);
});
