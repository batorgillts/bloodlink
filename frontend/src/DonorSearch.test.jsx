import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { DonorSearch } from "./DonorSearch";

const donor = {id: 5, full_name: "Ana Lopez", email: "ana+donor@example.com", blood_type: "A+"};
const response = data => ({ok: true, status: 200, json: async () => data});
function Picker() {
  const [value, setValue] = useState(null);
  return <DonorSearch value={value} onChange={setValue} />;
}
afterEach(() => {cleanup(); vi.unstubAllGlobals();});

test("does not fetch all donors; debounces partial input and supports keyboard selection", async () => {
  const fetch = vi.fn(async () => response([donor])); vi.stubGlobal("fetch", fetch);
  render(<Picker />);
  expect(fetch).not.toHaveBeenCalled();
  const input = screen.getByRole("combobox", {name: "Find donor"});
  fireEvent.change(input, {target: {value: "an"}});
  fireEvent.change(input, {target: {value: "ana+donor@"}});
  await screen.findByRole("option", {name: /Ana Lopez/});
  expect(fetch).toHaveBeenCalledTimes(1);
  const query = new URL(fetch.mock.calls[0][0]).searchParams;
  expect(query.get("search")).toBe("ana+donor@");
  expect(query.get("limit")).toBe("20");
  fireEvent.keyDown(input, {key: "ArrowDown"});
  expect(screen.getByRole("option")).toHaveAttribute("aria-selected", "true");
  fireEvent.keyDown(input, {key: "Enter"});
  expect(screen.getByText("ana+donor@example.com")).toBeInTheDocument();
  expect(input).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});

test("ignores late responses from a previous search", async () => {
  let resolveOld;
  const fetch = vi.fn(url => url.includes("search=old")
    ? new Promise(resolve => {resolveOld=resolve;})
    : Promise.resolve(response([donor])));
  vi.stubGlobal("fetch", fetch); render(<Picker />);
  const input = screen.getByRole("combobox");
  fireEvent.change(input, {target: {value: "old"}});
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  const oldSignal = fetch.mock.calls[0][1].signal;
  fireEvent.change(input, {target: {value: "Lopez"}});
  await screen.findByRole("option", {name: /Ana Lopez/});
  expect(oldSignal.aborted).toBe(true);
  resolveOld(response([{...donor, id: 7, full_name: "Old Result"}]));
  await waitFor(() => expect(screen.queryByRole("option", {name: /Old Result/})).not.toBeInTheDocument());
  expect(screen.getByRole("option", {name: /Ana Lopez/})).toBeInTheDocument();
});

test("empty results and network errors are actionable and Escape dismisses results", async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(response([]));
  vi.stubGlobal("fetch", fetch); render(<Picker />);
  const input = screen.getByRole("combobox");
  fireEvent.change(input, {target: {value: "missing"}});
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", {name: "Try again"}));
  expect(await screen.findByRole("status")).toHaveTextContent("Searching donors");
  await screen.findByText("No matching donors. Try another name or email.");
  fireEvent.keyDown(input, {key: "Escape"});
  expect(input).toHaveAttribute("aria-expanded", "false");
});
