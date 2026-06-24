/*
 * UFS: on-the-fly chatter resizing.
 *
 * Odoo 19 has no native way to resize the form chatter. This adds a thin
 * drag handle on the chatter's left edge: drag to set its width, the choice
 * is remembered per browser (localStorage), and double-clicking the handle
 * resets to Odoo's default.
 *
 * Plain (non-module) script: it runs once when the backend bundle loads and
 * uses a MutationObserver to (re)attach the handle whenever a chatter is
 * rendered, so it survives OWL re-renders and navigation between records.
 *
 * Targets ".o-mail-Chatter" (the Odoo 19 chatter root). Degrades to a no-op
 * if no chatter is present, and only attaches when the chatter is laid out
 * on the SIDE (skipped when it's stacked at the bottom on narrow screens).
 */
(function () {
    "use strict";

    var KEY = "ufs_chatter_width";
    var MIN = 280;
    var MAX = 900;

    function savedWidth() {
        var v = parseInt(localStorage.getItem(KEY), 10);
        if (isNaN(v)) {
            return null;
        }
        return Math.min(MAX, Math.max(MIN, v));
    }

    function applyWidth(chatter, w) {
        chatter.style.flex = "0 0 " + w + "px";
        chatter.style.width = w + "px";
        chatter.style.minWidth = w + "px";
        chatter.style.maxWidth = w + "px";
    }

    function clearWidth(chatter) {
        chatter.style.flex = "";
        chatter.style.width = "";
        chatter.style.minWidth = "";
        chatter.style.maxWidth = "";
    }

    function isSideLayout(chatter) {
        // When the chatter is stacked at the bottom (narrow screens) the
        // parent lays its children out in a column; only add the handle for
        // the side-by-side layout.
        var parent = chatter.parentElement;
        if (!parent) {
            return false;
        }
        var dir = getComputedStyle(parent).flexDirection || "";
        if (dir.indexOf("column") === 0) {
            return false;
        }
        // Sanity: side chatter is taller than it is wide.
        var r = chatter.getBoundingClientRect();
        return r.height >= r.width;
    }

    function enhance(chatter) {
        if (chatter.dataset.ufsResizable === "1") {
            return;
        }
        if (!isSideLayout(chatter)) {
            return;
        }
        chatter.dataset.ufsResizable = "1";
        if (getComputedStyle(chatter).position === "static") {
            chatter.style.position = "relative";
        }

        var w = savedWidth();
        if (w) {
            applyWidth(chatter, w);
        }

        var handle = document.createElement("div");
        handle.className = "ufs-chatter-resizer";
        handle.title = "Drag to resize the chatter · double-click to reset";
        chatter.appendChild(handle);

        var dragging = false;
        var startX = 0;
        var startW = 0;

        handle.addEventListener("mousedown", function (e) {
            dragging = true;
            startX = e.clientX;
            startW = chatter.getBoundingClientRect().width;
            document.body.style.userSelect = "none";
            e.preventDefault();
            e.stopPropagation();
        });

        window.addEventListener("mousemove", function (e) {
            if (!dragging) {
                return;
            }
            // The chatter sits to the RIGHT of the form, so dragging the
            // handle leftward should widen it.
            var nw = startW + (startX - e.clientX);
            nw = Math.min(MAX, Math.max(MIN, nw));
            applyWidth(chatter, nw);
        });

        window.addEventListener("mouseup", function () {
            if (!dragging) {
                return;
            }
            dragging = false;
            document.body.style.userSelect = "";
            localStorage.setItem(
                KEY,
                String(Math.round(chatter.getBoundingClientRect().width))
            );
        });

        handle.addEventListener("dblclick", function (e) {
            e.preventDefault();
            e.stopPropagation();
            localStorage.removeItem(KEY);
            clearWidth(chatter);
        });
    }

    function scan() {
        var chatters = document.querySelectorAll(".o-mail-Chatter");
        for (var i = 0; i < chatters.length; i++) {
            enhance(chatters[i]);
        }
    }

    function start() {
        try {
            var obs = new MutationObserver(function () {
                scan();
            });
            obs.observe(document.body, { childList: true, subtree: true });
        } catch (err) {
            // MutationObserver unavailable — fall back to a periodic scan.
            setInterval(scan, 1500);
        }
        scan();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
