import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useResource } from "./viewHelpers";

afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();});

test("eligibility refreshes automatically and on focus while retaining visible data",async()=>{
  vi.useFakeTimers();
  vi.spyOn(document,"visibilityState","get").mockReturnValue("visible");
  let data={donations:[],eligibility:[{eligible:true}]};
  const fetch=vi.fn(async()=>({ok:true,status:200,json:async()=>data}));
  vi.stubGlobal("fetch",fetch);
  const {result,unmount}=renderHook(()=>useResource("/api/donors/me/eligibility/",{refreshInterval:10000}));
  await act(async()=>{});
  expect(result.current.data.eligibility[0].eligible).toBe(true);
  data={donations:[{donation_id:1}],eligibility:[{eligible:false}]};
  await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});
  expect(result.current.data.eligibility[0].eligible).toBe(false);
  expect(result.current.data.donations).toHaveLength(1);
  expect(result.current.loading).toBe(false);
  data={...data,eligibility:[{eligible:true}]};
  await act(async()=>{window.dispatchEvent(new Event("focus"));});
  expect(result.current.data.eligibility[0].eligible).toBe(true);
  const calls=fetch.mock.calls.length;
  unmount();
  await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});
  expect(fetch).toHaveBeenCalledTimes(calls);
});
