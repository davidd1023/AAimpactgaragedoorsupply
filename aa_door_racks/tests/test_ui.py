import os

from odoo.tests import HttpCase, tagged

JS = r"""
const wait = async (sel, ms = 15000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
        const el = document.querySelector(sel);
        if (el) return el;
        await new Promise(r => setTimeout(r, 100));
    }
    throw new Error("timeout " + sel);
};
const type = (el, v) => { el.value = v; el.dispatchEvent(new Event("input", {bubbles: true})); };
(async () => {
    await wait(".o_rack_side");
    if (document.querySelectorAll(".o_rack_side").length !== 5) throw new Error("expected 5 sides");
    if (!document.querySelector(".o_rack_bundle")) throw new Error("no bundle drawn");
    [...document.querySelectorAll(".o_rack_top button")].find(b => b.textContent.includes("Receive")).click();
    (await wait(".o_rack_size")).click();
    const look = await wait(".o_rack_scan input");
    type(look, "UI-55");
    [...document.querySelectorAll(".o_rack_panel button")].find(b => b.textContent.trim() === "Add").click();
    await wait(".o_rack_door_input input");
    const inputs = document.querySelectorAll(".o_rack_door_input input");
    type(inputs[0], "9"); type(inputs[1], "0"); type(inputs[2], "4");
    await new Promise(r => setTimeout(r, 200));
    [...document.querySelectorAll(".o_rack_panel button")].find(b => b.textContent.includes("Find a spot")).click();
    await wait(".o_rack_spot.o_chosen");
    [...document.querySelectorAll(".o_rack_panel button")].find(b => b.textContent.includes("Save here")).click();
    await new Promise(r => setTimeout(r, 1500));
    const s = document.querySelector(".o_rack_search input");
    s.value = "UI-55"; s.dispatchEvent(new KeyboardEvent("keyup", {key: "Enter", bubbles: true}));
    await wait(".o_rack_bundle.o_hit");
    await wait(".o_rack_result");
    const btn = (txt) => [...document.querySelectorAll(".o_rack_panel button")].find(b => b.textContent.includes(txt));
    if (!btn("Remove bundle")) document.querySelector(".o_rack_bundle.o_hit").click();
    (await (async () => { for (let i = 0; i < 50 && !btn("Remove bundle"); i++) await new Promise(r => setTimeout(r, 100)); return btn("Remove bundle"); })()).click();
    await wait(".o_rack_remove");
    btn("Picked up").click();
    const t0 = Date.now();
    while (document.querySelector(".o_rack_bundle.o_hit") && Date.now() - t0 < 10000) await new Promise(r => setTimeout(r, 100));
    if (document.querySelector(".o_rack_bundle.o_hit")) throw new Error("bundle still on the rack after Remove");
    // a double bundle scanned off two big labels: the spots come up by themselves
    [...document.querySelectorAll(".o_rack_top button")].find(b => b.textContent.includes("Receive")).click();
    await wait(".o_rack_size");
    document.querySelectorAll(".o_rack_size")[1].click();
    let sc = await wait(".o_rack_scan input");
    type(sc, "AAD|7001|1|96|84|4"); sc.dispatchEvent(new KeyboardEvent("keyup", {key: "Enter", bubbles: true}));
    await new Promise(r => setTimeout(r, 800));
    sc = await wait(".o_rack_scan input");
    type(sc, "AAD|7002|1|108|84|4"); sc.dispatchEvent(new KeyboardEvent("keyup", {key: "Enter", bubbles: true}));
    await wait(".o_rack_option .badge.text-bg-success");
    __SHOT__
    btn("Save here").click();
    await new Promise(r => setTimeout(r, 1500));
    console.log("test successful");
})().catch(e => console.error(e.message));
"""


@tagged("post_install", "-at_install")
class TestBoardUi(HttpCase):

    def test_board_receive_and_find(self):
        B = self.env["aa.door.bundle"]
        for doors in ([{"order_ref": "1234", "width": 96, "panels": 4}, {"order_ref": "1250", "width": 108, "panels": 4}],
                      [{"order_ref": "2001", "width": 192, "panels": 4}],
                      [{"order_ref": "2002", "width": 132, "panels": 5}]):
            B.board_receive(doors, B.board_suggest(doors)["spots"][0])
        shot = "throw new Error('screenshot please');" if os.environ.get("AA_RACK_SHOT") else ""
        self.browser_js("/odoo/action-aa_door_racks.action_rack_board", JS.replace("__SHOT__", shot),
                        login="admin", timeout=90)
