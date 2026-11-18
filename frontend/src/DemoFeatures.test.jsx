import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";

const response = (data, status=200) => Promise.resolve({ok:status<400,status,json:()=>Promise.resolve(data)});
function login(path, role="coordinator") {
  localStorage.setItem("access","test-access");
  localStorage.setItem("bloodlink-user",JSON.stringify({email:"demo@example.com",role}));
  window.history.replaceState({},"",path);
}
beforeEach(()=>{
  localStorage.clear();
  HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  HTMLDialogElement.prototype.close=function(){this.open=false;};
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

test("donor registry encodes blood-type filters and never sends blank filters",async()=>{
  login("/donors");
  const fetch=vi.fn(()=>response([]));vi.stubGlobal("fetch",fetch);
  render(<App/>);
  await screen.findByText("No active donors found.");
  fireEvent.change(screen.getByLabelText("Blood type"),{target:{value:"A+"}});
  fireEvent.click(screen.getByRole("button",{name:"Search donors"}));
  await waitFor(()=>expect(fetch.mock.calls.at(-1)[0]).toMatch(/\/api\/donors\/\?blood_type=A%2B$/));
});

test("inventory text search combines with dropdown filters and can be cleared",async()=>{
  login("/inventory");
  const fetch=vi.fn(()=>response([])); vi.stubGlobal("fetch",fetch); render(<App/>);
  await screen.findByText("No units found. Record a blood unit or change your filters.");
  fireEvent.change(screen.getByLabelText("Search inventory"),{target:{value:" ana+donor@ "}});
  fireEvent.change(screen.getByLabelText("Blood type"),{target:{value:"A+"}});
  fireEvent.change(screen.getByLabelText("Component"),{target:{value:"RBC"}});
  fireEvent.change(screen.getByLabelText("Status"),{target:{value:"available"}});
  fireEvent.click(screen.getByRole("button",{name:"Apply filters"}));
  await waitFor(()=>{
    const params=new URL(fetch.mock.calls.at(-1)[0]).searchParams;
    expect(Object.fromEntries(params)).toEqual({search:"ana+donor@",blood_type:"A+",component:"RBC",status:"available"});
  });
  fireEvent.change(screen.getByLabelText("Search inventory"),{target:{value:""}});
  fireEvent.click(screen.getByRole("button",{name:"Apply filters"}));
  await waitFor(()=>expect(new URL(fetch.mock.calls.at(-1)[0]).searchParams.has("search")).toBe(false));
  expect(new URL(fetch.mock.calls.at(-1)[0]).searchParams.get("component")).toBe("RBC");
});

test("reserved unit discard requires a second confirmation after the server warning",async()=>{
  login("/inventory");
  let discarded=false;
  const fetch=vi.fn((url,options)=>{
    if(url.endsWith("/discard/")) {
      const body=JSON.parse(options.body);
      if(!body.confirm) return response({confirm_required:true,request_id:42,detail:"Reserved unit"},409);
      expect(body.reason).toBe("damaged");discarded=true;return response({});
    }
    return response([{id:7,unit_code:"UNIT-7",blood_type:"A+",component:"RBC",status:discarded?"discarded":"reserved",can_discard:!discarded}]);
  });vi.stubGlobal("fetch",fetch);render(<App/>);
  fireEvent.click(await screen.findByRole("button",{name:"Discard UNIT-7"}));
  fireEvent.change(screen.getByLabelText("Discard reason"),{target:{value:"damaged"}});
  fireEvent.click(screen.getByRole("button",{name:"Discard unit",exact:true}));
  expect(await screen.findByRole("alert")).toHaveTextContent("REQ-42");
  expect(discarded).toBe(false);
  fireEvent.click(screen.getByRole("button",{name:"Confirm discard of reserved unit"}));
  await screen.findByText("Unit discarded. Any affected request has been updated.");
  expect(discarded).toBe(true);
});

test("donation deletion is confirmed and reloads recalculated eligibility",async()=>{
  login("/donors/5");let deleted=false;
  const fetch=vi.fn((url,options)=>{
    if(options.method==="DELETE") {expect(JSON.parse(options.body)).toEqual({confirm:true});deleted=true;return response({});}
    return response({id:5,full_name:"Demo Donor",status:"active",blood_type:"A+",donations:deleted?[]:[{donation_id:9,donation_date:"2026-11-01",donation_type:"plasma",volume_ml:600,blood_type:"A+"}],eligibility:[{donation_type:"plasma",label:"Plasma",eligible:deleted}]});
  });vi.stubGlobal("fetch",fetch);render(<App/>);
  fireEvent.click(await screen.findByRole("button",{name:"Delete donation 9"}));
  expect(deleted).toBe(false);
  fireEvent.click(screen.getByRole("button",{name:"Confirm",exact:true}));
  await screen.findByText("No previous donations are recorded.");
  expect(screen.getByText("Eligible",{exact:true})).toBeInTheDocument();
});

test("withdrawal clears the session and reports retained history",async()=>{
  login("/me/contact","donor");
  const fetch=vi.fn(url=>response(url.endsWith("/eligibility/")?{eligibility:[],donations:[]}:url.endsWith("/profile/")?{email:"demo@example.com",phone:"2025550100"}:{}));
  vi.stubGlobal("fetch",fetch);render(<App/>);
  fireEvent.click(await screen.findByRole("button",{name:"Withdraw registration"}));
  expect(fetch.mock.calls.some(([url])=>url.endsWith("/withdraw/"))).toBe(false);
  fireEvent.click(screen.getByRole("button",{name:"Confirm",exact:true}));
  await screen.findByRole("heading",{name:"Sign in to BloodLink"});
  expect(localStorage.getItem("access")).toBeNull();
  expect(screen.getByText(/Registration withdrawn/)).toBeInTheDocument();
});

test("donors cannot load the new registry route",()=>{
  login("/donors","donor");const fetch=vi.fn();vi.stubGlobal("fetch",fetch);
  render(<App/>);expect(screen.getByText("You do not have access")).toBeInTheDocument();expect(fetch).not.toHaveBeenCalled();
});
