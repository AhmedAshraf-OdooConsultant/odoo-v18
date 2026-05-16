/** @odoo-module **/
/**
 * KS Dashboard Ninja - Odoo 18 Compatibility Layer
 * Bridges the gap between the original AMD-style modules and Odoo 18 ESM.
 */

import { Component, useState, useRef, onMounted, onWillStart, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";
import { session } from "@web/session";
import { loadBundle } from "@web/core/assets";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";

// ── Export for use in other modules ──────────────────────────
export { Component, useState, useRef, onMounted, onWillStart, onWillUnmount };
export { registry, useService, _t, rpc, user, session, loadBundle, FormViewDialog };

// ── Global compat: expose on window for legacy AMD code ───────
window.ks_owl = { Component, useState, useRef, onMounted, onWillStart, onWillUnmount };
window.ks_registry = registry;
window.ks_t = _t;
window.ks_rpc = rpc;
window.ks_user = user;
