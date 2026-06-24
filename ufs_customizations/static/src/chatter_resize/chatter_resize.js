/*
 * UFS: on-the-fly chatter resizing (Odoo 19 backend).
 *
 * Odoo 19 has no native chatter resize. This adds a thin drag handle on the
 * chatter panel's left edge: drag to set the width, the choice is remembered
 * per browser (localStorage), double-click resets to Odoo's default.
 *
 * Odoo 19 form-view DOM (chatter on the side):
 *   .o_form_view > .o_form_renderer (flex row)
 *       .o_form_sheet_bg            <- form region; flex:1 1 auto, max-width:1400px
 *         .o_form_sheet             <- fills the region
 *       .o-mail-Form-chatter.o-aside <- chatter PANEL; flex:1 0 auto  ← size THIS
 *         .o-mail-Chatter           <- inner (w-100 flex-grow-1, scrolls)
 *
 * So we size the .o-mail-Form-chatter panel (not the inner chatter), and lift
 * the .o_form_sheet_bg max-width so the form actually widens into the freed
 * space. Writes use setProperty(..., 'important') to beat Bootstrap's
 * flex-grow-1 / w-100 utility classes (they carry !important). The handle is
 * appended to the panel (which doesn't scroll), and the drag listeners are
 * bound once globally so re-renders don't stack them.
 */
(function () {
    "use strict";

    var KEY = "ufs_chatter_width";
    var MIN = 280;
    var MAX = 1000;

    var drag = null; // { chatter, startX, startW } while dragging

    function clamp(w) {
        return Math.min(MAX, Math.max(MIN, w));
    }

    function savedWidth() {
        var v = parseInt(localStorage.getItem(KEY), 10);
        return isNaN(v) ? null : clamp(v);
    }

    function setImp(el, prop, val) {
        if (el) {
            el.style.setProperty(prop, val, "important");
        }
    }

    function clearImp(el, prop) {
        if (el) {
            el.style.removeProperty(prop);
        }
    }

    function formRoot(chatter) {
        return chatter.closest(".o_form_view") ||
            chatter.closest(".o_form_renderer") ||
            chatter.parentElement;
    }

    function asidePanel(chatter) {
        return chatter.closest(".o-mail-Form-chatter") ||
            chatter.closest(".o-mail-ChatterContainer") ||
            chatter;
    }

    function sheetRegion(chatter) {
        var root = formRoot(chatter);
        return root ? root.querySelector(".o_form_sheet_bg") : null;
    }

    function isSideLayout(chatter) {
        return !!chatter.closest(".o-aside");
    }

    function applyWidth(chatter, w) {
        var panel = asidePanel(chatter);
        setImp(panel, "flex", "0 0 " + w + "px");
        setImp(panel, "width", w + "px");
        setImp(panel, "min-width", w + "px");
        setImp(panel, "max-width", w + "px");
        // Inner chatter just fills the panel; clear any caps and uncap.
        clearImp(chatter, "flex");
        clearImp(chatter, "width");
        clearImp(chatter, "min-width");
        setImp(chatter, "max-width", "none");
        var region = sheetRegion(chatter);
        if (region) {
            setImp(region, "flex", "1 1 auto");
            setImp(region, "min-width", "0");
            setImp(region, "max-width", "none");
        }
    }

    function clearWidth(chatter) {
        var panel = asidePanel(chatter);
        ["flex", "width", "min-width", "max-width"].forEach(function (p) {
            clearImp(panel, p);
            clearImp(chatter, p);
        });
        var region = sheetRegion(chatter);
        if (region) {
            ["flex", "min-width", "max-width"].forEach(function (p) {
                clearImp(region, p);
            });
        }
    }

    // Global drag handlers (bound once).
    window.addEventListener("mousemove", function (e) {
        if (!drag) {
            return;
        }
        applyWidth(drag.chatter, clamp(drag.startW + (drag.startX - e.clientX)));
    });
    window.addEventListener("mouseup", function () {
        if (!drag) {
            return;
        }
        document.body.style.userSelect = "";
        localStorage.setItem(
            KEY,
            String(Math.round(asidePanel(drag.chatter).getBoundingClientRect().width))
        );
        drag = null;
    });

    function enhance(chatter) {
        if (!isSideLayout(chatter)) {
            return;
        }
        var panel = asidePanel(chatter);
        if (panel.querySelector(":scope > .ufs-chatter-resizer")) {
            return; // already enhanced (and not wiped by a re-render)
        }
        if (getComputedStyle(panel).position === "static") {
            panel.style.position = "relative";
        }

        // Restore the saved width (also re-applies after an OWL re-render),
        // unless the user is mid-drag.
        var w = savedWidth();
        if (w && !drag) {
            applyWidth(chatter, w);
        }

        var handle = document.createElement("div");
        handle.className = "ufs-chatter-resizer";
        handle.title = "Drag to resize the chatter · double-click to reset";
        handle.addEventListener("mousedown", function (e) {
            drag = {
                chatter: chatter,
                startX: e.clientX,
                startW: asidePanel(chatter).getBoundingClientRect().width,
            };
            document.body.style.userSelect = "none";
            e.preventDefault();
            e.stopPropagation();
        });
        handle.addEventListener("dblclick", function (e) {
            e.preventDefault();
            e.stopPropagation();
            localStorage.removeItem(KEY);
            clearWidth(chatter);
        });
        panel.appendChild(handle);
    }

    function scan() {
        document.querySelectorAll(".o-mail-Chatter").forEach(enhance);
    }

    function start() {
        try {
            new MutationObserver(scan).observe(document.body, {
                childList: true,
                subtree: true,
            });
        } catch (err) {
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
