/*
 * Chatter Workspace: resize, collapse and float the form chatter.
 * Copyright 2026 Parameter (https://parameterllc.com/)
 * License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
 *
 * Form view DOM (Odoo 19.0 and 20.0, chatter beside the form):
 *   .o_form_renderer (flex row)
 *       .o_form_sheet_bg                 <- form region; max-width 1400px
 *       .o-mail-Form-chatter.o-aside     <- chatter PANEL, sized/collapsed/floated here
 *           .o-mail-Chatter              <- Owl chatter (w-100 flex-grow-1, scrolls)
 * Below the XXL breakpoint the same panel sits under the form (no o-aside).
 * With a document preview, Odoo renders the panel inside .o_form_sheet_bg
 * (o-isInFormSheetBg).
 *
 * Design rules carried over from the original resize script:
 * - Size the outer panel, lift the form region's max-width, and write inline
 *   styles with !important only where Bootstrap utilities would win.
 * - Only touch the panel, the inner chatter and the form region; remember any
 *   inline value we overwrite and restore it when the layout no longer needs it.
 * - Never move, clone or re-mount Owl nodes: collapsing hides the chatter and
 *   floating makes its own panel position:fixed, so the one Owl chatter and its
 *   composer (with any draft and pending attachments) stay mounted.
 * - Controls are added idempotently; listeners live on our own elements, so
 *   re-renders never stack them. One MutationObserver, coalesced per frame,
 *   watches child lists and the panel's class/identity attributes (inline
 *   style changes are not observed, so our own writes cannot loop).
 */
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";
import { session } from "@web/session";

import {
    DOCK_STRIP_WIDTH,
    KEY_STEP,
    KEY_STEP_LARGE,
    MIN_FLOAT_VIEWPORT,
    activePreset,
    clamp,
    defaultFloatRect,
    dragBounds,
    fitFloatRect,
    preferredWidth,
    presentation,
    renderedSideWidth,
    transition,
} from "./layout_math";

const PREF_MODEL = "parameter.chatter.preference";
const CACHE_KEY = `parameter_chatter_workspace:v1:${session.db || ""}:${user.userId || 0}`;
const SAVE_DELAY = 600;
const FLOAT_Z_INDEX = "1040"; // below Odoo overlays/dialogs (1055), above sticky bars

// ---------------------------------------------------------------------------
// Server state
// ---------------------------------------------------------------------------

/** @type {Map<string, object>} model -> entry */
const entries = new Map();

function callKw(method, args, kwargs = {}) {
    return rpc(
        `/web/dataset/call_kw/${PREF_MODEL}/${method}`,
        { model: PREF_MODEL, method, args, kwargs },
        { silent: true }
    );
}

function readCache() {
    try {
        return JSON.parse(window.localStorage.getItem(CACHE_KEY) || "{}") || {};
    } catch {
        return {};
    }
}

function writeCache(model, config) {
    try {
        const cache = readCache();
        cache[model] = config;
        window.localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
    } catch {
        // Storage unavailable (private mode, quota): the server copy still applies.
    }
}

function getEntry(model) {
    let entry = entries.get(model);
    if (!entry) {
        const cached = readCache()[model];
        entry = {
            model,
            config: cached || null,
            loaded: false,
            loading: null,
            status: "idle", // idle | saving | saved | error
            error: "",
        };
        entries.set(model, entry);
    }
    if (!entry.loaded && !entry.loading) {
        load(entry);
    }
    return entry;
}

// ---------------------------------------------------------------------------
// Ordered preference writes
// ---------------------------------------------------------------------------
//
// Every write of this tab (saves and resets) goes through one queue and is
// sent only after the previous one has answered. Each request also carries
// this tab's id and an increasing number; the server ignores a write that is
// older than the one it already stored for the same row. That second guard
// covers what a queue cannot: the request sent with fetch(keepalive) when the
// page is left, which may overtake a request still in transit.
//
// Pending changes are merged per real target: the form type's own row
// ("model:<name>") or the user's single default row ("global"), whichever
// form the change came from.

const TAB_ID = makeTabId();
let writeSeq = 0;
/** @type {Map<string, {kind: "save", model: string, scope: string, values: object}>} */
const pendingWrites = new Map();
/** Requests waiting for their turn, in order. */
const outbox = [];
let inflightItem = null;
let pumping = false;
let pumpDone = Promise.resolve();
let saveTimer = null;

function makeTabId() {
    try {
        if (window.crypto?.randomUUID) {
            return window.crypto.randomUUID();
        }
    } catch {
        // Not a secure context: fall through.
    }
    return `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
}

function targetKey(model, scope) {
    return scope === "global" ? "global" : `model:${model}`;
}

/** Changes not yet confirmed by the server that affect this form type. */
function hasPending(entry) {
    const mine = (item) => item.kind === "reset" || item.scope === "global" || item.model === entry.model;
    return (
        pendingWrites.has("global") ||
        pendingWrites.has(targetKey(entry.model, "model")) ||
        outbox.some(mine)
    );
}

function load(entry) {
    entry.loading = callKw("get_workspace_config", [entry.model])
        .then((config) => {
            if (!hasPending(entry)) {
                entry.config = config;
            }
            writeCache(entry.model, config);
        })
        .catch((error) => {
            console.warn("Chatter Workspace: could not load the layout", error);
            entry.status = "error";
            entry.error = _t("Layout settings could not be loaded. Odoo's standard chatter is used.");
        })
        .finally(() => {
            entry.loaded = true;
            entry.loading = null;
            scheduleScan();
        });
}

function errorMessage(error) {
    return error?.data?.message || error?.message || String(error);
}

function isConnectionError(error) {
    return !error?.data; // RPC errors raised by the server carry `data`
}

function queueSave(entry, changes, scope) {
    scope = scope || (entry.config.remember_per_model ? "model" : "global");
    const key = targetKey(entry.model, scope);
    const item = pendingWrites.get(key) || { kind: "save", model: entry.model, scope, values: {} };
    item.model = entry.model; // the form that receives the new configuration
    Object.assign(item.values, changes);
    pendingWrites.set(key, item);
    if (scope === "model") {
        entry.config.has_model_override = true;
    }
    entry.status = "saving";
    clearTimeout(saveTimer);
    saveTimer = setTimeout(flushAll, SAVE_DELAY);
}

/** Queue every pending change and resolve once everything queued is answered. */
function flushAll() {
    clearTimeout(saveTimer);
    saveTimer = null;
    outbox.push(...pendingWrites.values());
    pendingWrites.clear();
    return pump();
}

function pump() {
    if (!pumping) {
        pumping = true;
        pumpDone = (async () => {
            try {
                while (outbox.length) {
                    await send(outbox.shift());
                }
            } finally {
                pumping = false;
            }
        })();
    }
    return pumpDone;
}

function stamp() {
    writeSeq += 1;
    return { client_session: TAB_ID, client_seq: writeSeq };
}

async function send(item) {
    const entry = entries.get(item.model);
    const isSave = item.kind === "save";
    inflightItem = item;
    try {
        const config = await callKw(
            isSave ? "save_preference" : item.method,
            isSave ? [item.model, item.values, item.scope] : item.args,
            stamp()
        );
        writeCache(item.model, config);
        if (entry) {
            if (config.stale) {
                entry.loaded = false; // the server holds a newer write: reload it
            } else if (!hasPending(entry)) {
                entry.config = config;
            }
            entry.status = "saved";
            entry.error = "";
        }
        if (!isSave || item.scope === "global") {
            invalidateOthers(item.model);
        }
    } catch (error) {
        if (entry) {
            entry.status = "error";
        }
        if (isSave && isConnectionError(error)) {
            // Keep the change for the next save; newer edits of the same target win.
            const key = targetKey(item.model, item.scope);
            const newer = pendingWrites.get(key);
            pendingWrites.set(key, { ...item, values: { ...item.values, ...(newer ? newer.values : {}) } });
            if (entry) {
                entry.error = _t("Not saved (connection problem). Your layout applies in this tab and is saved with your next change.");
            }
        } else if (entry) {
            entry.error = errorMessage(error);
            entry.loaded = false; // re-sync with what the server accepts
        }
        console.warn("Chatter Workspace: could not save the layout", error);
    } finally {
        inflightItem = null;
    }
    scheduleScan();
    refreshMenu();
}

/** A change to the personal default affects every form type. */
function invalidateOthers(model) {
    for (const [name, other] of entries) {
        if (name !== model && !hasPending(other)) {
            other.loaded = false;
        }
    }
}

/**
 * Queue a reset after everything already queued. Pending changes to the
 * targets it clears are dropped: the reset supersedes them.
 */
function runReset(entry, method, args) {
    const scope = args[1];
    if (scope === "all") {
        pendingWrites.clear();
    } else if (scope === "personal") {
        pendingWrites.delete("global");
    } else {
        pendingWrites.delete(targetKey(entry.model, "model"));
    }
    clearTimeout(saveTimer);
    saveTimer = null;
    outbox.push(...pendingWrites.values(), { kind: "reset", model: entry.model, method, args });
    pendingWrites.clear();
    entry.status = "saving";
    refreshMenu();
    return pump();
}

/**
 * Requests to send when the page is left: the one in transit (it may never
 * arrive), the queued ones and the pending ones, merged per target in order
 * and numbered after everything already sent. A reset starts new merges so
 * changes made after it stay after it.
 */
function unloadBatch() {
    const items = [];
    if (inflightItem) {
        items.push(inflightItem);
    }
    items.push(...outbox.splice(0), ...pendingWrites.values());
    pendingWrites.clear();
    const batch = [];
    let merged = new Map();
    for (const item of items) {
        if (item.kind !== "save") {
            batch.push(item);
            merged = new Map();
            continue;
        }
        const key = targetKey(item.model, item.scope);
        const existing = merged.get(key);
        if (existing) {
            Object.assign(existing.values, item.values);
        } else {
            const copy = { ...item, values: { ...item.values } };
            batch.push(copy);
            merged.set(key, copy);
        }
    }
    return batch;
}

window.addEventListener("pagehide", () => {
    clearTimeout(saveTimer);
    for (const item of unloadBatch()) {
        const isSave = item.kind === "save";
        const method = isSave ? "save_preference" : item.method;
        try {
            fetch(`/web/dataset/call_kw/${PREF_MODEL}/${method}`, {
                method: "POST",
                keepalive: true,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    id: Date.now(),
                    params: {
                        model: PREF_MODEL,
                        method,
                        args: isSave ? [item.model, item.values, item.scope] : item.args,
                        kwargs: stamp(),
                    },
                }),
            });
        } catch {
            // Best effort only.
        }
    }
});

// ---------------------------------------------------------------------------
// Owned inline styles
// ---------------------------------------------------------------------------

/** @type {WeakMap<HTMLElement, Map<string, {value: string, priority: string}>>} */
const owned = new WeakMap();

function setOwned(el, prop, value) {
    let props = owned.get(el);
    if (!props) {
        props = new Map();
        owned.set(el, props);
    }
    if (!props.has(prop)) {
        props.set(prop, {
            value: el.style.getPropertyValue(prop),
            priority: el.style.getPropertyPriority(prop),
        });
    }
    if (el.style.getPropertyValue(prop) !== value || el.style.getPropertyPriority(prop) !== "important") {
        el.style.setProperty(prop, value, "important");
    }
}

function releaseOwned(el, keep = {}) {
    const props = el && owned.get(el);
    if (!props) {
        return;
    }
    for (const [prop, original] of [...props]) {
        if (prop in keep) {
            continue;
        }
        if (original.value) {
            el.style.setProperty(prop, original.value, original.priority);
        } else {
            el.style.removeProperty(prop);
        }
        props.delete(prop);
    }
    if (!props.size) {
        owned.delete(el);
    }
}

/** Apply exactly `styles` (owned) on `el`, restoring anything we no longer need. */
function syncStyles(el, styles) {
    if (!el) {
        return;
    }
    releaseOwned(el, styles);
    for (const [prop, value] of Object.entries(styles)) {
        setOwned(el, prop, value);
    }
}

// ---------------------------------------------------------------------------
// Small DOM helpers
// ---------------------------------------------------------------------------

const ICONS = {
    layout: '<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" focusable="false"><path fill="currentColor" d="M1.5 2h13a.5.5 0 0 1 .5.5v11a.5.5 0 0 1-.5.5h-13a.5.5 0 0 1-.5-.5v-11a.5.5 0 0 1 .5-.5Zm.5 1v10h7V3H2Zm8 0v10h4V3h-4Z"/></svg>',
    expand: '<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" focusable="false"><path fill="currentColor" d="M10.35 3.15a.5.5 0 0 1 0 .7L6.21 8l4.14 4.15a.5.5 0 0 1-.7.7l-4.5-4.5a.5.5 0 0 1 0-.7l4.5-4.5a.5.5 0 0 1 .7 0Z"/></svg>',
    expandUp: '<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" focusable="false"><path fill="currentColor" d="M3.15 10.35a.5.5 0 0 0 .7 0L8 6.21l4.15 4.14a.5.5 0 0 0 .7-.7l-4.5-4.5a.5.5 0 0 0-.7 0l-4.5 4.5a.5.5 0 0 0 0 .7Z"/></svg>',
    close: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false"><path fill="currentColor" d="M3.65 3.65a.5.5 0 0 1 .7 0L8 7.29l3.65-3.64a.5.5 0 0 1 .7.7L8.71 8l3.64 3.65a.5.5 0 0 1-.7.7L8 8.71l-3.65 3.64a.5.5 0 0 1-.7-.7L7.29 8 3.65 4.35a.5.5 0 0 1 0-.7Z"/></svg>',
    move: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false"><path fill="currentColor" d="M8 1 5.5 3.5h2v4h-4v-2L1 8l2.5 2.5v-2h4v4h-2L8 15l2.5-2.5h-2v-4h4v2L15 8l-2.5-2.5v2h-4v-4h2L8 1Z"/></svg>',
    grip: '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false"><path fill="currentColor" d="M14 6v1L7 14H6l8-8Zm0 4v1l-3 3h-1l4-4Z"/></svg>',
};

function el(tag, className, attrs = {}) {
    const node = document.createElement(tag);
    if (className) {
        node.className = className;
    }
    for (const [name, value] of Object.entries(attrs)) {
        if (name === "html") {
            node.innerHTML = value;
        } else if (name === "text") {
            node.textContent = value;
        } else {
            node.setAttribute(name, value);
        }
    }
    return node;
}

/**
 * Activate our buttons on Enter/Space ourselves. Odoo 20's global hotkey
 * handler may claim Enter and cancel the browser's native activation of the
 * focused button, which would make our controls unusable from the keyboard.
 */
function pressable(button) {
    button.addEventListener("keydown", (ev) => {
        if ((ev.key === "Enter" || ev.key === " ") && !ev.repeat && !ev.altKey && !ev.ctrlKey && !ev.metaKey) {
            ev.preventDefault();
            ev.stopPropagation();
            if (!button.disabled && button.getAttribute("aria-disabled") !== "true") {
                button.click();
            }
        }
    });
    return button;
}

function child(parent, className) {
    return parent.querySelector(`:scope > .${className}`);
}

function removeChild(parent, className) {
    child(parent, className)?.remove();
}

function viewport() {
    return { width: window.innerWidth, height: window.innerHeight };
}

// ---------------------------------------------------------------------------
// Panels
// ---------------------------------------------------------------------------

/** @type {Map<HTMLElement, object>} enhanced panel -> panel state */
const panels = new Map();
let pendingFocus = null; // {panel, target}
let drag = null;

function odooLayout(panel) {
    if (panel.classList.contains("o-aside")) {
        return "side";
    }
    if (panel.classList.contains("o-isInFormSheetBg")) {
        return "sheet";
    }
    return "bottom";
}

function formRegion(panel) {
    if (panel.classList.contains("o-isInFormSheetBg")) {
        return null; // the panel lives inside the form region itself
    }
    return panel.parentElement?.querySelector(":scope > .o_form_sheet_bg") || null;
}

function innerChatter(panel) {
    return child(panel, "o-mail-Chatter");
}

function rowWidth(panel) {
    return panel.parentElement?.getBoundingClientRect().width || window.innerWidth;
}

function identity(panel) {
    const data = panel.dataset;
    return {
        model: data.pcwModel || "",
        resId: data.pcwResId || "",
        isNew: data.pcwNew === "1" || !data.pcwResId,
        name: data.pcwName || "",
    };
}

function floatRect(entry) {
    if (entry.config.float_rect) {
        return fitFloatRect(entry.config.float_rect, viewport());
    }
    // Not placed by the user yet: start below the control panel (breadcrumbs,
    // pager, action buttons), whose height differs between editions.
    const controlPanel = document.querySelector(".o_action_manager .o_control_panel");
    const top = controlPanel ? Math.round(controlPanel.getBoundingClientRect().bottom) + 8 : 96;
    return defaultFloatRect(viewport(), top);
}

function scan() {
    const found = new Set();
    for (const panel of document.querySelectorAll(".o-mail-Form-chatter")) {
        if (panel.closest(".modal")) {
            continue;
        }
        found.add(panel);
    }
    for (const panel of [...panels.keys()]) {
        if (!found.has(panel) || !panel.isConnected) {
            teardown(panel);
        }
    }
    for (const panel of found) {
        enhance(panel);
    }
    if (pendingFocus) {
        const { panel, target } = pendingFocus;
        pendingFocus = null;
        focusTarget(panel, target);
    }
}

let scanQueued = false;
function scheduleScan() {
    if (scanQueued) {
        return;
    }
    scanQueued = true;
    window.requestAnimationFrame(() => {
        scanQueued = false;
        try {
            scan();
        } catch (error) {
            console.error("Chatter Workspace: layout update failed", error);
        }
    });
}

function teardown(panel) {
    const state = panels.get(panel);
    if (drag?.panel === panel) {
        endDrag(false);
    }
    syncStyles(panel, {});
    if (state) {
        syncStyles(state.inner, {});
        syncStyles(state.region, {});
    }
    for (const className of ["pcw-resizer", "pcw-dockstrip", "pcw-float-header", "pcw-float-resize"]) {
        removeChild(panel, className);
    }
    panel.querySelector(".pcw-layout-btn")?.remove();
    delete panel.dataset.pcwPresentation;
    if (menuState?.panel === panel) {
        closeMenu(false);
    }
    panels.delete(panel);
}

function enhance(panel) {
    const ident = identity(panel);
    if (!ident.model) {
        teardown(panel);
        return;
    }
    const entry = getEntry(ident.model);
    if (!entry.config) {
        return; // applied once the configuration arrives
    }
    const config = entry.config;
    const layout = odooLayout(panel);
    const pres = presentation(config.effective, {
        odooLayout: layout,
        viewportWidth: window.innerWidth,
        features: config.features,
    });
    let state = panels.get(panel);
    if (!state) {
        state = { entry, identityKey: "" };
        panels.set(panel, state);
    }
    state.entry = entry;
    const inner = innerChatter(panel);
    const region = formRegion(panel);
    if (state.region && state.region !== region) {
        syncStyles(state.region, {});
    }
    if (state.inner && state.inner !== inner) {
        syncStyles(state.inner, {});
    }
    state.inner = inner;
    state.region = region;
    state.pres = pres;
    state.layout = layout;
    panel.dataset.pcwPresentation = pres;

    const panelStyles = {};
    const innerStyles = {};
    let regionStyles = {};
    const lift = { flex: "1 1 auto", "min-width": "0", "max-width": "none" };

    if (pres === "side" && !(drag && drag.panel === panel)) {
        const { width } = renderedSideWidth(config.effective, rowWidth(panel), config.bounds);
        state.renderedWidth = width;
        if (width) {
            Object.assign(panelStyles, {
                flex: `0 0 ${width}px`,
                width: `${width}px`,
                "min-width": `${width}px`,
                "max-width": `${width}px`,
            });
            innerStyles["max-width"] = "none";
            regionStyles = lift;
        }
    } else if (pres === "side" && drag?.panel === panel) {
        return; // live drag owns the width until it ends
    } else if (pres === "docked") {
        innerStyles.display = "none";
        if (layout === "side") {
            const strip = `${DOCK_STRIP_WIDTH}px`;
            Object.assign(panelStyles, {
                flex: `0 0 ${strip}`,
                width: strip,
                "min-width": strip,
                "max-width": strip,
                padding: "0",
            });
            regionStyles = lift;
        } else {
            Object.assign(panelStyles, { "padding-bottom": "0" });
        }
    } else if (pres === "floating") {
        const rect = floatRect(entry);
        Object.assign(panelStyles, {
            position: "fixed",
            left: `${rect.left}px`,
            top: `${rect.top}px`,
            width: `${rect.width}px`,
            height: `${rect.height}px`,
            "min-width": "0",
            "max-width": "none",
            flex: "none",
            margin: "0",
            padding: "0",
            display: "flex",
            "flex-direction": "column",
            "z-index": FLOAT_Z_INDEX,
        });
        Object.assign(innerStyles, {
            overflow: "auto",
            flex: "1 1 auto",
            "min-height": "0",
            height: "auto",
            "max-width": "none",
        });
        if (layout !== "sheet") {
            regionStyles = lift;
        }
    }
    if (pres === "side" || (pres === "docked" && layout === "side")) {
        if (getComputedStyle(panel).position === "static" || owned.get(panel)?.has("position")) {
            panelStyles.position = "relative";
        }
    }
    syncStyles(panel, panelStyles);
    syncStyles(inner, innerStyles);
    syncStyles(region, regionStyles);

    syncControls(panel, state, entry, pres, layout, ident);
}

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------

function canChangeLayout(config) {
    return !config.locks.layout;
}

function canResize(config) {
    return config.features.resize && !config.locks.width;
}

function syncControls(panel, state, entry, pres, layout, ident) {
    const config = entry.config;
    // Layout menu button in the chatter's own top bar.
    const topbar = panel.querySelector(".o-mail-Chatter-topbar");
    let button = panel.querySelector(".pcw-layout-btn");
    if (pres === "none") {
        button?.remove();
    } else if (topbar && (!button || button.parentElement !== topbar)) {
        button?.remove();
        button = el("button", "pcw-layout-btn btn btn-link text-action px-1", {
            type: "button",
            "aria-haspopup": "menu",
            "aria-expanded": "false",
            "aria-label": _t("Chatter layout"),
            title: _t("Chatter layout"),
            html: ICONS.layout,
        });
        button.addEventListener("click", (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            if (menuState?.button === button) {
                closeMenu(true);
            } else {
                openMenu(panel, button);
            }
        });
        // First in the bar: Odoo's top bar scrolls horizontally when the
        // chatter is narrow, which would hide a button placed at the end.
        topbar.prepend(pressable(button));
    }
    if (button) {
        button.classList.toggle("pcw-has-error", entry.status === "error");
        button.title = entry.status === "error" ? entry.error : _t("Chatter layout");
    }

    // Resize handle (side layout only).
    if (pres === "side" && canResize(config)) {
        let handle = child(panel, "pcw-resizer");
        if (!handle) {
            handle = createResizer(panel);
            panel.appendChild(handle);
        }
        const bounds = dragBounds(rowWidth(panel), config.bounds);
        const now = Math.round(panel.getBoundingClientRect().width);
        handle.setAttribute("aria-valuemin", String(bounds.min));
        handle.setAttribute("aria-valuemax", String(bounds.max));
        handle.setAttribute("aria-valuenow", String(now));
        handle.setAttribute("aria-valuetext", _t("%s pixels", now));
    } else {
        removeChild(panel, "pcw-resizer");
    }

    // Collapsed strip.
    if (pres === "docked") {
        let strip = child(panel, "pcw-dockstrip");
        if (!strip || strip.dataset.layout !== layout) {
            strip?.remove();
            strip = createDockStrip(panel, layout);
            panel.appendChild(strip);
        }
        strip.querySelector("button:not(.pcw-strip-menu)").disabled = !canChangeLayout(config);
    } else {
        removeChild(panel, "pcw-dockstrip");
    }

    // Floating header and resize grip.
    if (pres === "floating") {
        let header = child(panel, "pcw-float-header");
        if (!header) {
            header = createFloatHeader(panel);
            panel.appendChild(header);
            panel.appendChild(createFloatGrip(panel));
        }
        const title = header.querySelector(".pcw-float-title");
        const subtitle = header.querySelector(".pcw-float-subtitle");
        const name = ident.name || (ident.isNew ? _t("New record (not saved yet)") : _t("Untitled record"));
        const sub = ident.resId ? `${config.model_label} · #${ident.resId}` : config.model_label;
        const key = `${ident.model}:${ident.resId}:${ident.isNew}:${ident.name}`;
        if (title.textContent !== name) {
            title.textContent = name;
        }
        if (subtitle.textContent !== sub) {
            subtitle.textContent = sub;
        }
        header.title = `${name} — ${sub}`;
        header.setAttribute("aria-label", _t("Floating chatter for %s", name));
        if (state.identityKey && state.identityKey !== key) {
            header.classList.remove("pcw-flash");
            void header.offsetWidth; // restart the highlight animation
            header.classList.add("pcw-flash");
        }
        state.identityKey = key;
        header.querySelector(".pcw-float-close").disabled = !canChangeLayout(config);
    } else {
        removeChild(panel, "pcw-float-header");
        removeChild(panel, "pcw-float-resize");
        state.identityKey = "";
    }
}

function focusTarget(panel, target) {
    if (!panel.isConnected) {
        return;
    }
    const selectors = {
        strip: ".pcw-dockstrip button:not(.pcw-strip-menu)",
        header: ".pcw-float-header .pcw-float-move",
        layout: ".pcw-layout-btn",
    };
    const node = panel.querySelector(selectors[target]);
    if (node) {
        node.focus();
    }
}

function act(panel, action, value, focus) {
    const state = panels.get(panel);
    if (!state) {
        return;
    }
    const entry = state.entry;
    const changes = transition(entry.config.effective, action, value);
    Object.assign(entry.config.effective, changes);
    queueSave(entry, changes);
    if (focus) {
        pendingFocus = { panel, target: focus };
    }
    scheduleScan();
    refreshMenu();
}

// --- resize handle --------------------------------------------------------

function liveWidth(panel, width) {
    const state = panels.get(panel);
    syncStyles(panel, {
        flex: `0 0 ${width}px`,
        width: `${width}px`,
        "min-width": `${width}px`,
        "max-width": `${width}px`,
        position: owned.get(panel)?.has("position") ? "relative" : panel.style.position || "relative",
    });
    syncStyles(state?.inner, { "max-width": "none" });
    syncStyles(state?.region, { flex: "1 1 auto", "min-width": "0", "max-width": "none" });
    const handle = child(panel, "pcw-resizer");
    if (handle) {
        handle.setAttribute("aria-valuenow", String(Math.round(width)));
        handle.setAttribute("aria-valuetext", _t("%s pixels", Math.round(width)));
    }
}

function onDragKeydown(ev) {
    if (ev.key === "Escape" && drag) {
        ev.preventDefault();
        ev.stopPropagation();
        endDrag(false);
    }
}

function endDrag(commit) {
    if (!drag) {
        return;
    }
    window.removeEventListener("keydown", onDragKeydown, true);
    const { panel, width, startWidth } = drag;
    drag = null;
    document.body.classList.remove("pcw-dragging");
    if (commit && width && Math.round(width) !== Math.round(startWidth)) {
        act(panel, "resize", width);
    } else {
        scheduleScan(); // restore the stored layout
    }
}

function createResizer(panel) {
    const handle = el("div", "pcw-resizer", {
        role: "separator",
        tabindex: "0",
        "aria-orientation": "vertical",
        "aria-label": _t("Resize chatter"),
        title: _t("Drag to resize the chatter · double-click to restore the default width"),
    });
    handle.addEventListener("pointerdown", (ev) => {
        if (ev.button !== 0 || drag) {
            return;
        }
        const state = panels.get(panel);
        ev.preventDefault();
        ev.stopPropagation();
        handle.setPointerCapture(ev.pointerId);
        const startWidth = panel.getBoundingClientRect().width;
        drag = {
            panel,
            pointerId: ev.pointerId,
            startX: ev.clientX,
            startWidth,
            width: 0,
            bounds: dragBounds(rowWidth(panel), state.entry.config.bounds),
        };
        document.body.classList.add("pcw-dragging");
        window.addEventListener("keydown", onDragKeydown, true);
    });
    handle.addEventListener("pointermove", (ev) => {
        if (!drag || drag.pointerId !== ev.pointerId) {
            return;
        }
        drag.width = clamp(drag.startWidth + (drag.startX - ev.clientX), drag.bounds.min, drag.bounds.max);
        liveWidth(panel, drag.width);
    });
    handle.addEventListener("pointerup", (ev) => {
        if (drag?.pointerId === ev.pointerId) {
            endDrag(true);
        }
    });
    handle.addEventListener("pointercancel", () => endDrag(false));
    handle.addEventListener("lostpointercapture", () => endDrag(true));
    handle.addEventListener("dblclick", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        act(panel, "reset_width");
    });
    handle.addEventListener("keydown", (ev) => {
        const state = panels.get(panel);
        if (!state) {
            return;
        }
        const config = state.entry.config;
        const bounds = dragBounds(rowWidth(panel), config.bounds);
        const current = panel.getBoundingClientRect().width;
        const step = ev.shiftKey ? KEY_STEP_LARGE : KEY_STEP;
        let next = null;
        if (ev.key === "ArrowLeft") {
            next = current + step; // the handle is on the left edge: left = wider
        } else if (ev.key === "ArrowRight") {
            next = current - step;
        } else if (ev.key === "Home") {
            next = bounds.min;
        } else if (ev.key === "End") {
            next = bounds.max;
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            act(panel, "reset_width");
            return;
        }
        if (next !== null) {
            ev.preventDefault();
            act(panel, "resize", clamp(next, bounds.min, bounds.max));
        }
    });
    return handle;
}

// --- collapsed strip ----------------------------------------------------------

function createDockStrip(panel, layout) {
    const vertical = layout === "side";
    const strip = el("div", `pcw-dockstrip ${vertical ? "pcw-dockstrip-side" : "pcw-dockstrip-bottom"}`);
    strip.dataset.layout = layout;
    const button = el("button", "btn btn-link", {
        type: "button",
        "aria-expanded": "false",
        "aria-label": _t("Show chatter"),
        title: _t("Show chatter"),
        html: `${vertical ? ICONS.expand : ICONS.expandUp}<span class="pcw-dockstrip-label"></span>`,
    });
    button.querySelector(".pcw-dockstrip-label").textContent = _t("Chatter");
    button.addEventListener("click", () => act(panel, "undock", null, "layout"));
    pressable(button);
    const menuButton = el("button", "pcw-strip-menu btn btn-link", {
        type: "button",
        "aria-haspopup": "menu",
        "aria-expanded": "false",
        "aria-label": _t("Chatter layout"),
        title: _t("Chatter layout"),
        html: ICONS.layout,
    });
    menuButton.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        if (menuState?.button === menuButton) {
            closeMenu(true);
        } else {
            openMenu(panel, menuButton);
        }
    });
    strip.append(button, pressable(menuButton));
    return strip;
}

// --- floating panel -------------------------------------------------------------

function saveFloatRect(panel, rect) {
    const state = panels.get(panel);
    if (!state) {
        return;
    }
    const entry = state.entry;
    entry.config.float_rect = rect;
    queueSave(entry, { float_rect: rect }, "global");
    // The geometry is shared by all forms: update loaded configs right away.
    for (const other of entries.values()) {
        if (other.config) {
            other.config.float_rect = rect;
        }
    }
}

function currentRect(panel) {
    const r = panel.getBoundingClientRect();
    return { left: r.left, top: r.top, width: r.width, height: r.height };
}

function applyRect(panel, rect) {
    const fitted = fitFloatRect(rect, viewport());
    setOwned(panel, "left", `${fitted.left}px`);
    setOwned(panel, "top", `${fitted.top}px`);
    setOwned(panel, "width", `${fitted.width}px`);
    setOwned(panel, "height", `${fitted.height}px`);
    return fitted;
}

function pointerTrack(target, onMove, onEnd) {
    return (ev) => {
        if (ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        target.setPointerCapture(ev.pointerId);
        const start = { x: ev.clientX, y: ev.clientY };
        let moved = false;
        document.body.classList.add("pcw-dragging");
        const move = (e) => {
            moved = moved || Math.abs(e.clientX - start.x) + Math.abs(e.clientY - start.y) > 2;
            if (moved) {
                onMove(e.clientX - start.x, e.clientY - start.y);
            }
        };
        const finish = (e) => {
            target.removeEventListener("pointermove", move);
            target.removeEventListener("pointerup", finish);
            target.removeEventListener("pointercancel", finish);
            document.body.classList.remove("pcw-dragging");
            onEnd(moved && e.type !== "pointercancel");
        };
        target.addEventListener("pointermove", move);
        target.addEventListener("pointerup", finish);
        target.addEventListener("pointercancel", finish);
    };
}

function createFloatHeader(panel) {
    const header = el("div", "pcw-float-header", { role: "group" });
    const titles = el("div", "pcw-float-titles");
    titles.append(
        el("div", "pcw-float-title", { "aria-live": "polite" }),
        el("div", "pcw-float-subtitle")
    );
    const move = el("button", "pcw-float-move btn btn-link", {
        type: "button",
        "aria-label": _t("Move panel (arrow keys)"),
        title: _t("Drag the header to move · arrow keys move the panel"),
        html: ICONS.move,
    });
    const close = el("button", "pcw-float-close btn btn-link", {
        type: "button",
        "aria-label": _t("Return chatter to the form"),
        title: _t("Return chatter to the form"),
        html: ICONS.close,
    });
    header.append(move, titles, close);
    close.addEventListener("click", () => act(panel, "unfloat", null, "layout"));
    pressable(close);

    let startRect = null;
    const onDown = pointerTrack(
        header,
        (dx, dy) => {
            applyRect(panel, { ...startRect, left: startRect.left + dx, top: startRect.top + dy });
        },
        (commit) => {
            if (commit) {
                saveFloatRect(panel, currentRect(panel));
            } else {
                scheduleScan();
            }
        }
    );
    header.addEventListener("pointerdown", (ev) => {
        if (ev.target.closest(".pcw-float-close")) {
            return;
        }
        startRect = currentRect(panel);
        onDown(ev);
    });
    move.addEventListener("keydown", (ev) => {
        const step = ev.shiftKey ? KEY_STEP_LARGE : KEY_STEP;
        const delta = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[ev.key];
        if (!delta) {
            return;
        }
        ev.preventDefault();
        const rect = currentRect(panel);
        saveFloatRect(panel, applyRect(panel, { ...rect, left: rect.left + delta[0], top: rect.top + delta[1] }));
    });
    return header;
}

function createFloatGrip(panel) {
    const grip = el("button", "pcw-float-resize btn btn-link", {
        type: "button",
        "aria-label": _t("Resize panel (arrow keys)"),
        title: _t("Drag to resize the panel · arrow keys resize"),
        html: ICONS.grip,
    });
    let startRect = null;
    const onDown = pointerTrack(
        grip,
        (dx, dy) => {
            applyRect(panel, { ...startRect, width: startRect.width + dx, height: startRect.height + dy });
        },
        (commit) => {
            if (commit) {
                saveFloatRect(panel, currentRect(panel));
            } else {
                scheduleScan();
            }
        }
    );
    grip.addEventListener("pointerdown", (ev) => {
        startRect = currentRect(panel);
        onDown(ev);
    });
    grip.addEventListener("keydown", (ev) => {
        const step = ev.shiftKey ? KEY_STEP_LARGE : KEY_STEP;
        const delta = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[ev.key];
        if (!delta) {
            return;
        }
        ev.preventDefault();
        const rect = currentRect(panel);
        saveFloatRect(panel, applyRect(panel, { ...rect, width: rect.width + delta[0], height: rect.height + delta[1] }));
    });
    return grip;
}

// ---------------------------------------------------------------------------
// Layout menu
// ---------------------------------------------------------------------------

let menuState = null; // {panel, button, menu, confirming}

function presetItems(config) {
    const items = [
        { key: "standard", label: _t("Standard"), hint: _t("Odoo's arrangement, at your width") },
    ];
    if (config.features.dock) {
        items.push({ key: "data_entry", label: _t("Data Entry"), hint: _t("Collapse the chatter, maximise the form") });
    }
    if (config.features.presets) {
        items.push(
            { key: "conversation", label: _t("Conversation"), hint: _t("Wider chatter, form stays usable") },
            { key: "review", label: _t("Review"), hint: _t("Balance form, chatter and document preview") }
        );
    }
    if (config.features.float) {
        items.push({ key: "floating", label: _t("Floating panel"), hint: _t("Move the chatter into a panel on this page") });
    }
    return items;
}

function menuItem(menu, label, { role = "menuitem", checked, disabled, hint, onSelect, className = "" } = {}) {
    const item = el("button", `dropdown-item pcw-menu-item ${className}`, { type: "button", role, tabindex: "-1" });
    if (checked !== undefined) {
        item.setAttribute("aria-checked", checked ? "true" : "false");
        item.classList.toggle("active", Boolean(checked));
    }
    if (disabled) {
        item.setAttribute("aria-disabled", "true");
        item.classList.add("disabled");
    }
    const text = el("span", "pcw-menu-label", { text: label });
    item.appendChild(text);
    if (hint) {
        item.appendChild(el("span", "pcw-menu-hint", { text: hint }));
    }
    item.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        if (!disabled) {
            onSelect?.();
        }
    });
    pressable(item);
    menu.appendChild(item);
    return item;
}

function buildMenu() {
    const { panel, menu } = menuState;
    const state = panels.get(panel);
    if (!state) {
        closeMenu(false);
        return;
    }
    const entry = state.entry;
    const config = entry.config;
    const eff = config.effective;
    menu.replaceChildren();
    menu.appendChild(el("div", "dropdown-header pcw-menu-title", {
        text: config.model_label ? _t("Chatter layout · %s", config.model_label) : _t("Chatter layout"),
    }));

    if (menuState.confirming) {
        menu.appendChild(el("div", "pcw-menu-note", {
            text: _t("Remove all your saved chatter layouts on every form? Team defaults will apply again."),
        }));
        menuItem(menu, _t("Reset all my layouts"), {
            className: "text-danger",
            onSelect: () => {
                menuState.confirming = false;
                runReset(entry, "reset_preferences", [entry.model, "all"]);
            },
        });
        menuItem(menu, _t("Cancel"), {
            onSelect: () => {
                menuState.confirming = false;
                buildMenu();
                focusFirst();
            },
        });
        menuState.signature = menuSignature();
        return;
    }

    const locked = !canChangeLayout(config);
    const active = activePreset(eff);
    const floatBlocked = window.innerWidth < MIN_FLOAT_VIEWPORT;
    for (const preset of presetItems(config)) {
        const disabled = locked || (preset.key === "floating" && floatBlocked);
        menuItem(menu, preset.label, {
            role: "menuitemradio",
            checked: active === preset.key,
            disabled,
            hint: preset.key === "floating" && floatBlocked ? _t("Needs a wider window") : preset.hint,
            onSelect: () => {
                closeMenu(false);
                if (preset.key === "floating") {
                    act(panel, "float", null, "header");
                } else if (preset.key === "data_entry") {
                    act(panel, "preset", "data_entry", "strip");
                } else {
                    act(panel, "preset", preset.key, "layout");
                }
            },
        });
    }
    if (locked) {
        menu.appendChild(el("div", "pcw-menu-note", { text: _t("Your administrator has set the layout for this form.") }));
    }

    menu.appendChild(el("div", "dropdown-divider"));
    if (state.pres === "side" && canResize(config) && preferredWidth(eff)) {
        menuItem(menu, _t("Restore default width"), { onSelect: () => act(panel, "reset_width", null, "layout") });
    }
    if (config.allow_personal && config.remember_per_model && config.has_model_override) {
        menuItem(menu, _t("Use this layout on all forms"), {
            onSelect: () => {
                closeMenu(true);
                const values = {};
                if (!config.locks.layout) {
                    values.layout = eff.layout;
                    values.dock_state = eff.dock_state;
                }
                if (!config.locks.width && config.features.resize) {
                    values.width = eff.width || false;
                    values.conversation_width = eff.conversation_width || false;
                    values.review_width = eff.review_width || false;
                }
                // Queued in order: the new default first, then this form's reset.
                queueSave(entry, values, "global");
                runReset(entry, "reset_preferences", [entry.model, "model"]);
            },
        });
        menuItem(menu, _t("Reset this form to my defaults"), {
            onSelect: () => {
                closeMenu(true);
                runReset(entry, "reset_preferences", [entry.model, "model"]);
            },
        });
    }
    if (config.allow_personal) {
        menuItem(menu, _t("Reset all my layouts…"), {
            onSelect: () => {
                menuState.confirming = true;
                buildMenu();
                focusFirst();
            },
        });
    }

    const notes = [];
    notes.push(config.rule ? _t("Team default: %s", config.rule.name) : _t("Team default: global settings"));
    if (config.locks.width && config.features.resize) {
        notes.push(_t("Width set by your administrator."));
    }
    if (!config.allow_personal) {
        notes.push(_t("Personal layouts are turned off by your administrator."));
    }
    menu.appendChild(el("div", "pcw-menu-note text-muted", { text: notes.join(" ") }));
    const status = el("div", "pcw-menu-note pcw-menu-status", { "aria-live": "polite" });
    status.textContent = menuStatusText();
    menu.appendChild(status);
    menuState.signature = menuSignature();
}

function menuStatusText() {
    const state = menuState && panels.get(menuState.panel);
    const entry = state?.entry;
    if (!entry) {
        return "";
    }
    if (entry.status === "saving") {
        return _t("Saving…");
    }
    if (entry.status === "error") {
        return entry.error;
    }
    return "";
}

function menuItems() {
    return menuState ? [...menuState.menu.querySelectorAll(".pcw-menu-item:not(.disabled)")] : [];
}

function focusFirst() {
    const items = menuItems();
    (items.find((i) => i.getAttribute("aria-checked") === "true") || items[0])?.focus();
}

function positionMenu() {
    const { button, menu } = menuState;
    const rect = button.getBoundingClientRect();
    const width = menu.offsetWidth;
    const height = menu.offsetHeight;
    const left = clamp(rect.right - width, 8, window.innerWidth - width - 8);
    let top = rect.bottom + 4;
    if (top + height > window.innerHeight - 8) {
        top = Math.max(8, rect.top - height - 4);
    }
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
}

function onMenuKeydown(ev) {
    const items = menuItems();
    const index = items.indexOf(document.activeElement);
    let next = null;
    if (ev.key === "ArrowDown") {
        next = items[(index + 1) % items.length];
    } else if (ev.key === "ArrowUp") {
        next = items[(index - 1 + items.length) % items.length];
    } else if (ev.key === "Home") {
        next = items[0];
    } else if (ev.key === "End") {
        next = items[items.length - 1];
    } else if (ev.key === "Escape") {
        ev.preventDefault();
        ev.stopPropagation();
        closeMenu(true);
        return;
    } else if (ev.key === "Tab") {
        closeMenu(false);
        return;
    }
    if (next) {
        ev.preventDefault();
        ev.stopPropagation();
        next.focus();
    }
}

function onOutsidePointer(ev) {
    if (menuState && !menuState.menu.contains(ev.target) && !menuState.button.contains(ev.target)) {
        closeMenu(false);
    }
}

function openMenu(panel, button) {
    closeMenu(false);
    // Not a Bootstrap .dropdown-menu: Bootstrap's document-level keyboard
    // handler would try to attach a Dropdown to it and throw without a toggle.
    const menu = el("div", "pcw-menu", { role: "menu", "aria-label": _t("Chatter layout") });
    menuState = { panel, button, menu, confirming: false };
    buildMenu();
    menu.addEventListener("keydown", onMenuKeydown);
    document.body.appendChild(menu);
    positionMenu();
    button.setAttribute("aria-expanded", "true");
    document.addEventListener("pointerdown", onOutsidePointer, true);
    focusFirst();
}

function closeMenu(restoreFocus) {
    if (!menuState) {
        return;
    }
    const { button, menu } = menuState;
    menuState = null;
    document.removeEventListener("pointerdown", onOutsidePointer, true);
    menu.remove();
    button.setAttribute("aria-expanded", "false");
    if (restoreFocus && button.isConnected) {
        button.focus();
    }
}

function menuSignature() {
    const state = menuState && panels.get(menuState.panel);
    if (!state) {
        return "";
    }
    const config = state.entry.config;
    return JSON.stringify([
        config.effective, config.locks, config.features, config.rule, config.has_model_override,
        config.allow_personal, config.remember_per_model, state.pres, menuState.confirming,
        window.innerWidth >= MIN_FLOAT_VIEWPORT,
    ]);
}

function refreshMenu() {
    if (!menuState) {
        return;
    }
    if (menuSignature() === menuState.signature) {
        // Only the save status changed: update the note, keep focus and items.
        const note = menuState.menu.querySelector(".pcw-menu-status");
        if (note) {
            note.textContent = menuStatusText();
        }
        return;
    }
    const focusedIndex = menuItems().indexOf(document.activeElement);
    buildMenu();
    positionMenu();
    if (focusedIndex >= 0) {
        menuItems()[Math.min(focusedIndex, menuItems().length - 1)]?.focus();
    }
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

const OBSERVED_ATTRIBUTES = ["class", "data-pcw-model", "data-pcw-res-id", "data-pcw-name", "data-pcw-new"];

function isRelevantAttribute(target) {
    return (
        target.classList?.contains("o-mail-Form-chatter") ||
        target.classList?.contains("o_form_view") ||
        target.classList?.contains("o-mail-Chatter")
    );
}

function start() {
    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            if (mutation.type === "childList" || isRelevantAttribute(mutation.target)) {
                scheduleScan();
                return;
            }
        }
    });
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: OBSERVED_ATTRIBUTES,
    });
    window.addEventListener("resize", () => {
        scheduleScan();
        if (menuState) {
            closeMenu(false);
        }
    });
    scheduleScan();
}

if (document.body) {
    start();
} else {
    document.addEventListener("DOMContentLoaded", start, { once: true });
}

/** Read-only diagnostics for support and automated checks. */
window.parameterChatterWorkspace = {
    get panels() {
        return panels.size;
    },
    entry(model) {
        const entry = entries.get(model);
        return entry && { config: entry.config, status: entry.status, error: entry.error, pending: hasPending(entry) };
    },
    flush() {
        return flushAll();
    },
    get writes() {
        return { tab: TAB_ID, seq: writeSeq, queued: outbox.length, pending: [...pendingWrites.keys()], inflight: Boolean(inflightItem) };
    },
};
