import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";

afterEach(() => vi.unstubAllGlobals());

test("shows that the API is connected", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ status: "ok" }) })),
  );
  render(<App />);
  expect(await screen.findByText("API is connected")).toBeInTheDocument();
});

test("tells the user when the API is down", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  render(<App />);
  expect(await screen.findByText(/not reachable/)).toBeInTheDocument();
});