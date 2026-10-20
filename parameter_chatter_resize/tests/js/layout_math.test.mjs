// Copyright 2026 Parameter (https://parameterllc.com/)
// License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
// Run with: node --test parameter_chatter_resize/tests/js/layout_math.test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const source = readFileSync(new URL("../../static/src/layout_math.js", import.meta.url), "utf8");
const m = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));

const bounds = { min: 280, max: 1000 };
const features = { resize: true, dock: true, float: true, presets: true };
const base = { layout: "standard", dock_state: "open", width: 0, conversation_width: 0, review_width: 0 };

test("standard layout keeps Odoo's width until the user resizes", () => {
    assert.deepEqual(m.renderedSideWidth(base, 1920, bounds), { width: null, fallback: false });
    assert.deepEqual(m.renderedSideWidth({ ...base, width: 420 }, 1920, bounds), { width: 420, fallback: false });
});

test("rendered width protects a usable form without changing the preference", () => {
    const state = { ...base, width: 1000 };
    const res = m.renderedSideWidth(state, 1534, bounds);
    assert.equal(res.width, 1534 - m.MIN_FORM_WIDTH);
    assert.equal(res.fallback, true);
    assert.equal(state.width, 1000);
});

test("falls back to Odoo's layout when both areas cannot fit", () => {
    assert.deepEqual(m.renderedSideWidth({ ...base, width: 500 }, 700, bounds), { width: null, fallback: true });
});

test("task layouts compute automatic widths", () => {
    assert.equal(m.renderedSideWidth({ ...base, layout: "conversation" }, 1920, bounds).width, 1000);
    assert.equal(m.renderedSideWidth({ ...base, layout: "conversation" }, 1500, bounds).width, 1500 - m.MIN_FORM_WIDTH);
    assert.equal(m.renderedSideWidth({ ...base, layout: "review" }, 1920, bounds).width, Math.round(1920 * 0.45));
    assert.equal(m.renderedSideWidth({ ...base, layout: "review", review_width: 610 }, 1920, bounds).width, 610);
});

test("drag bounds follow the row", () => {
    assert.deepEqual(m.dragBounds(1920, bounds), { min: 280, max: 1000 });
    assert.deepEqual(m.dragBounds(1534, bounds), { min: 280, max: 1534 - m.MIN_FORM_WIDTH });
    assert.deepEqual(m.dragBounds(600, bounds), { min: 280, max: 280 });
});

test("presentation respects features and viewport", () => {
    const ctx = { odooLayout: "side", viewportWidth: 1920, features };
    assert.equal(m.presentation(base, ctx), "side");
    assert.equal(m.presentation({ ...base, dock_state: "docked" }, ctx), "docked");
    assert.equal(m.presentation({ ...base, layout: "floating" }, ctx), "floating");
    assert.equal(m.presentation({ ...base, layout: "floating" }, { ...ctx, viewportWidth: 900 }), "side");
    assert.equal(m.presentation({ ...base, layout: "floating" }, { ...ctx, features: { ...features, float: false } }), "side");
    assert.equal(m.presentation({ ...base, dock_state: "docked" }, { ...ctx, features: { ...features, dock: false } }), "side");
    assert.equal(m.presentation(base, { ...ctx, odooLayout: "bottom" }), "plain");
    assert.equal(m.presentation({ ...base, dock_state: "docked" }, { ...ctx, odooLayout: "sheet" }), "docked");
    assert.equal(m.presentation({ ...base, layout: "floating" }, { ...ctx, viewportWidth: 600 }), "none");
});

test("transitions only change what the action is about", () => {
    const state = { ...base, layout: "conversation", width: 500, conversation_width: 700 };
    assert.deepEqual(m.transition(state, "dock"), { dock_state: "docked" });
    assert.deepEqual(m.transition(state, "undock"), { dock_state: "open" });
    assert.deepEqual(m.transition(state, "preset", "data_entry"), { dock_state: "docked" });
    assert.deepEqual(m.transition(state, "preset", "review"), { layout: "review", dock_state: "open" });
    assert.deepEqual(m.transition(state, "float"), { layout: "floating", dock_state: "open" });
    assert.deepEqual(m.transition({ ...state, layout: "floating" }, "unfloat"), { layout: "standard" });
    assert.deepEqual(m.transition(state, "resize", 812.4), { conversation_width: 812 });
    assert.deepEqual(m.transition(state, "reset_width"), { conversation_width: 0 });
    assert.deepEqual(m.transition(base, "reset_width"), { width: 0 });
    assert.throws(() => m.transition(base, "explode"));
});

test("dock then undock restores the previous layout and width", () => {
    let state = { ...base, layout: "conversation", conversation_width: 720 };
    state = { ...state, ...m.transition(state, "preset", "data_entry") };
    assert.equal(m.activePreset(state), "data_entry");
    state = { ...state, ...m.transition(state, "undock") };
    assert.equal(m.activePreset(state), "conversation");
    assert.equal(m.renderedSideWidth(state, 1920, bounds).width, 720);
});

test("floating rectangles stay inside the viewport", () => {
    const vp = { width: 1280, height: 800 };
    const fitted = m.fitFloatRect({ left: 5000, top: -300, width: 3000, height: 50 }, vp);
    assert.ok(fitted.left >= m.FLOAT_MARGIN && fitted.left + fitted.width <= vp.width - m.FLOAT_MARGIN + 0.5);
    assert.ok(fitted.top >= m.FLOAT_MARGIN && fitted.top + fitted.height <= vp.height);
    assert.equal(fitted.height, m.FLOAT_MIN_HEIGHT);
    const def = m.defaultFloatRect(vp);
    assert.deepEqual(m.fitFloatRect(def, vp), def);
    const below = m.defaultFloatRect(vp, 140); // below a taller control panel
    assert.equal(below.top, 140);
    assert.ok(below.top + below.height <= vp.height);
});
