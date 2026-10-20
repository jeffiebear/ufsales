/*
 * Chatter Workspace: pure layout rules (no DOM, no Odoo imports).
 * Copyright 2026 Parameter (https://parameterllc.com/)
 * License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
 *
 * Kept free of imports so the same file runs in the browser bundle and under
 * `node --test` (tests/js/layout_math.test.mjs).
 */

/** Narrowest form area kept next to a side chatter (px). Chosen by rendering
 * the Contact form at 440/500/560/640px in a browser:
 * at 440px the record name truncates and the notebook tabs overflow; at 560px
 * name, tabs and main fields fit, only city/ZIP compress. */
export const MIN_FORM_WIDTH = 560;
/** Width of the collapsed (docked) side strip (px). */
export const DOCK_STRIP_WIDTH = 40;
/** Below this viewport width only Odoo's standard chatter is used. */
export const MIN_ENHANCED_VIEWPORT = 768;
/** Below this viewport width the floating panel falls back to the form. */
export const MIN_FLOAT_VIEWPORT = 992;
export const FLOAT_MIN_WIDTH = 320;
export const FLOAT_MIN_HEIGHT = 240;
/** Keep this much of the floating panel's header reachable inside the viewport. */
export const FLOAT_MARGIN = 8;
export const KEY_STEP = 16;
export const KEY_STEP_LARGE = 64;

export function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}

/**
 * Largest side-chatter width that still leaves MIN_FORM_WIDTH to the form.
 * @param {number} rowWidth width of the form row (form + chatter)
 */
export function maxFitWidth(rowWidth, minForm = MIN_FORM_WIDTH) {
    return Math.floor(rowWidth - minForm);
}

/**
 * Preferred width (0 = automatic/Odoo default) of the current layout.
 * @param {object} state effective layout state
 */
export function preferredWidth(state) {
    if (state.layout === "conversation") {
        return state.conversation_width || 0;
    }
    if (state.layout === "review") {
        return state.review_width || 0;
    }
    return state.width || 0;
}

/** Name of the stored width field for the current layout. */
export function widthField(layout) {
    if (layout === "conversation") {
        return "conversation_width";
    }
    if (layout === "review") {
        return "review_width";
    }
    return "width";
}

/**
 * Automatic width for the task layouts when the user has not customized them.
 * Conversation: as wide as allowed while keeping a usable form.
 * Review: an even split between form and chatter.
 */
export function autoWidth(layout, rowWidth, bounds) {
    if (layout === "conversation") {
        return clamp(maxFitWidth(rowWidth), bounds.min, bounds.max);
    }
    if (layout === "review") {
        return clamp(Math.round(rowWidth * 0.45), bounds.min, bounds.max);
    }
    return 0;
}

/**
 * Width to render for a side chatter. Never writes back to the preference.
 *
 * @returns {{width: number|null, fallback: boolean}} width null means "leave
 *   Odoo's own width"; fallback is true when the preferred width had to be
 *   reduced (or dropped) to keep the form usable.
 */
export function renderedSideWidth(state, rowWidth, bounds) {
    let wanted = preferredWidth(state);
    if (!wanted) {
        wanted = autoWidth(state.layout, rowWidth, bounds);
    }
    if (!wanted) {
        return { width: null, fallback: false };
    }
    wanted = clamp(wanted, bounds.min, bounds.max);
    const fit = maxFitWidth(rowWidth);
    if (fit < bounds.min) {
        // The row cannot hold both a usable form and the narrowest chatter:
        // do not force the saved width, keep Odoo's own layout.
        return { width: null, fallback: true };
    }
    if (wanted > fit) {
        return { width: fit, fallback: true };
    }
    return { width: wanted, fallback: false };
}

/** Bounds of the resize handle in the current row (for aria-valuemin/max). */
export function dragBounds(rowWidth, bounds) {
    const max = Math.min(bounds.max, Math.max(bounds.min, maxFitWidth(rowWidth)));
    return { min: bounds.min, max };
}

/**
 * Keep a floating panel inside the viewport with its header reachable.
 * The stored rectangle is untouched; this returns the rectangle to render.
 */
export function fitFloatRect(rect, viewport) {
    const maxWidth = Math.max(FLOAT_MIN_WIDTH, viewport.width - 2 * FLOAT_MARGIN);
    const maxHeight = Math.max(FLOAT_MIN_HEIGHT, viewport.height - 2 * FLOAT_MARGIN);
    const width = clamp(Math.round(rect.width), FLOAT_MIN_WIDTH, maxWidth);
    const height = clamp(Math.round(rect.height), FLOAT_MIN_HEIGHT, maxHeight);
    const left = clamp(Math.round(rect.left), FLOAT_MARGIN, Math.max(FLOAT_MARGIN, viewport.width - width - FLOAT_MARGIN));
    const top = clamp(Math.round(rect.top), FLOAT_MARGIN, Math.max(FLOAT_MARGIN, viewport.height - height - FLOAT_MARGIN));
    return { left, top, width, height };
}

/**
 * Default floating geometry: right-hand side, starting at `top` (the caller
 * passes the bottom of Odoo's control panel so the pager and action buttons
 * stay reachable; their height differs between Community and Enterprise).
 */
export function defaultFloatRect(viewport, top = 96) {
    const width = clamp(Math.round(viewport.width * 0.32), 360, 560);
    const height = clamp(viewport.height - top - 24, FLOAT_MIN_HEIGHT, 900);
    return fitFloatRect({ left: viewport.width - width - 24, top, width, height }, viewport);
}

/**
 * How the chatter is presented, given the effective state and what Odoo
 * rendered. Odoo's own layout ("side", "bottom" or "sheet" with a document
 * preview) is never changed; we only size, collapse or float its panel.
 *
 * @param {object} state effective layout state (layout, dock_state, ...)
 * @param {object} ctx {odooLayout, viewportWidth, features}
 * @returns {"none"|"side"|"plain"|"docked"|"floating"}
 */
export function presentation(state, ctx) {
    if (ctx.viewportWidth < MIN_ENHANCED_VIEWPORT) {
        return "none";
    }
    const features = ctx.features;
    if (state.layout === "floating" && features.float && ctx.viewportWidth >= MIN_FLOAT_VIEWPORT) {
        return "floating";
    }
    if (state.dock_state === "docked" && features.dock) {
        return "docked";
    }
    return ctx.odooLayout === "side" ? "side" : "plain";
}

/** The task layout button that should show as selected. */
export function activePreset(state) {
    if (state.dock_state === "docked") {
        return "data_entry";
    }
    return state.layout || "standard";
}

/**
 * Changes produced by a user action. Returns only the fields that change so
 * the caller can save them; never touches unrelated preferences.
 *
 * Actions: preset:<standard|data_entry|conversation|review>, float, unfloat,
 * dock, undock, resize:<px>, reset_width.
 */
export function transition(state, action, value) {
    switch (action) {
        case "preset":
            if (value === "data_entry") {
                return { dock_state: "docked" };
            }
            return { layout: value, dock_state: "open" };
        case "float":
            return { layout: "floating", dock_state: "open" };
        case "unfloat":
            // Closing the panel returns the chatter to the form in the
            // standard arrangement; the panel geometry is kept for next time.
            return { layout: "standard" };
        case "dock":
            return { dock_state: "docked" };
        case "undock":
            return { dock_state: "open" };
        case "resize":
            return { [widthField(state.layout)]: Math.round(value) };
        case "reset_width":
            return { [widthField(state.layout)]: 0 };
        default:
            throw new Error(`Unknown chatter action ${action}`);
    }
}
