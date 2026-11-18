import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { EditBloodUnit, RecordBloodUnit } from "./RecordBloodUnit";

const donor = {
  id: 5, full_name: "Example Donor", email: "example@example.com", blood_type: "A+",
  donations: [{donation_id: 9, donation_date: "2026-11-17", donation_type: "whole_blood", blood_type: "A+", volume_ml: 450}],
  eligibility: [
    {donation_type: "whole_blood", label: "Whole blood", allowed_components:["RBC","PLASMA","PLATELETS"]},
    {donation_type: "plasma", label: "Plasma", allowed_components:["PLASMA"]},
  ],
};
const response = (data, status=200) => Promise.resolve({ok:status<400,status,json:()=>Promise.resolve(data)});
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.open=true; };
  HTMLDialogElement.prototype.close = function () { this.open=false; };
});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});
function setup({initial = false, fail = false, empty = false} = {}) {
  const onCreated=vi.fn();
  const fetch=vi.fn((url, options) => {
    if (options.method === "POST") return fail
      ? response({donation_date:["The donor is not eligible yet."]}, 400)
      : response({id:1,donation_id:9});
    return response(url.includes("/donors/?") ? [donor, {...donor,id:6,full_name:"Other Donor"}]
      : {...donor, donations: empty || url.endsWith("/6/") ? [] : donor.donations});
  });
  vi.stubGlobal("fetch",fetch);
  render(<RecordBloodUnit donor={initial ? donor : undefined} donation={initial ? donor.donations[0] : undefined} onClose={()=>{}} onCreated={onCreated} />);
  return {fetch,onCreated};
}
async function chooseDonor() {
  fireEvent.change(screen.getByRole("combobox",{name:"Find donor"}),{target:{value:"Example"}});
  fireEvent.click(await screen.findByRole("option", {name:/Example Donor/}));
  await screen.findByLabelText("Donation record");
}
function fillUnit() {
  fireEvent.change(screen.getByLabelText("Unique unit code"),{target:{value:"UNIT-NEW"}});
  fireEvent.change(screen.getByLabelText("Collection date and time (your local time)"),{target:{value:"11/17/2026 10:00"}});
}

test("new donation and unit are submitted together with the chosen donor",async()=>{
  const {fetch,onCreated}=setup({empty:true});
  await chooseDonor();
  expect(screen.getByRole("button",{name:"Record unit"})).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Donation record"),{target:{value:"new"}});
  fireEvent.change(screen.getByLabelText("Donation volume (mL)"),{target:{value:"450"}});
  fillUnit();
  fireEvent.click(screen.getByRole("button",{name:"Record unit"}));
  await waitFor(()=>expect(onCreated).toHaveBeenCalled());
  const posts=fetch.mock.calls.filter(([,o])=>o.method==="POST");
  expect(posts).toHaveLength(1);
  expect(posts[0][0]).toMatch(/\/api\/units\/$/);
  expect(JSON.parse(posts[0][1].body)).toMatchObject({donor_id:5,donation_type:"whole_blood",volume_ml:450,blood_type:"A+",unit_code:"UNIT-NEW"});
  expect(JSON.parse(posts[0][1].body)).not.toHaveProperty("donation_id");
});

test("donor record shortcut links an existing donation without recording it again",async()=>{
  const {fetch,onCreated}=setup({initial:true});
  await screen.findByLabelText("Source donation");
  expect(screen.getByLabelText("Source donation")).toHaveValue("9");
  fillUnit();
  fireEvent.click(screen.getByRole("button",{name:"Record unit"}));
  await waitFor(()=>expect(onCreated).toHaveBeenCalled());
  const body=JSON.parse(fetch.mock.calls.find(([,o])=>o.method==="POST")[1].body);
  expect(body).toMatchObject({donor_id:5,donation_id:9,blood_type:"A+"});
  expect(body).not.toHaveProperty("donation_type");
  expect(body).not.toHaveProperty("volume_ml");
});

test("switching donor clears the previous source donation",async()=>{
  setup({initial:true});
  await screen.findByLabelText("Source donation");
  fireEvent.change(screen.getByRole("combobox",{name:"Find donor"}),{target:{value:"Other"}});
  expect(screen.queryByLabelText("Source donation")).not.toBeInTheDocument();
  fireEvent.click(await screen.findByRole("option",{name:/Other Donor/}));
  await screen.findByLabelText("Source donation");
  expect(screen.getByLabelText("Source donation")).toHaveValue("");
  expect(screen.getByRole("button",{name:"Record unit"})).toBeDisabled();
});

test("eligibility failure keeps the form open with an English error",async()=>{
  const {onCreated}=setup({fail:true});
  await chooseDonor();
  fireEvent.change(screen.getByLabelText("Donation record"),{target:{value:"new"}});
  fireEvent.change(screen.getByLabelText("Donation volume (mL)"),{target:{value:"450"}});
  fillUnit();
  fireEvent.click(screen.getByRole("button",{name:"Record unit"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("not eligible yet");
  expect(onCreated).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Unique unit code")).toHaveValue("UNIT-NEW");
});

test("donation type restricts components and both fields are sent", async()=>{
  const {fetch,onCreated}=setup();
  await chooseDonor();
  fireEvent.change(screen.getByLabelText("Donation record"),{target:{value:"new"}});
  expect(screen.getByLabelText("Collection date and time (your local time)").value).toMatch(/^\d{2}\/\d{2}\/\d{4} /);
  fireEvent.change(screen.getByLabelText("Donation type"),{target:{value:"plasma"}});
  expect(screen.getByLabelText("Component")).toHaveValue("PLASMA");
  expect(screen.getByLabelText("Component").options).toHaveLength(1);
  fireEvent.change(screen.getByLabelText("Donation volume (mL)"),{target:{value:"600"}});
  fillUnit();
  fireEvent.click(screen.getByRole("button",{name:"Record unit"}));
  await waitFor(()=>expect(onCreated).toHaveBeenCalled());
  expect(JSON.parse(fetch.mock.calls.find(([,o])=>o.method==="POST")[1].body))
    .toMatchObject({donation_type:"plasma",component:"PLASMA"});
});

test("editing a unit patches corrections without creating another donation", async()=>{
  const onSaved=vi.fn();
  const fetch=vi.fn((url,options)=>response(options.method==="PATCH"?{id:1}:donor));
  vi.stubGlobal("fetch",fetch);
  render(<EditBloodUnit unit={{id:1,unit_code:"UNIT-1",donation_id:9,component:"RBC",blood_type:"A+",
    collected_at:"2026-11-10T15:00:23Z",source_donation:{donor_id:5,donation_type:"whole_blood"}}}
    onClose={()=>{}} onSaved={onSaved}/>);
  await screen.findByLabelText("Source donation type");
  expect(screen.getByRole("button",{name:"Save corrections"})).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Source donation type"),{target:{value:"plasma"}});
  expect(screen.getByLabelText("Component")).toHaveValue("PLASMA");
  fireEvent.click(screen.getByRole("button",{name:"Save corrections"}));
  await waitFor(()=>expect(onSaved).toHaveBeenCalled());
  const call=fetch.mock.calls.find(([,o])=>o.method==="PATCH");
  expect(call[0]).toMatch(/\/api\/units\/1\/$/);
  expect(JSON.parse(call[1].body)).toEqual({donation_type:"plasma",component:"PLASMA"});
  expect(fetch.mock.calls.some(([,o])=>o.method==="POST")).toBe(false);
});
