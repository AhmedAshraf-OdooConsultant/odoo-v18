/** @odoo-module **/
/**
 * KS Dashboard Ninja - Odoo 18 Compatible
 * Converted from OWL 1 / Odoo 16 to OWL 2 / Odoo 18
 *
 * Key changes:
 * - var class → export class extends Component
 * - init() → setup() with useState/useRef/onMounted/onWillStart
 * - willStart/start → onWillStart/onMounted hooks
 * - this._rpc() → rpc() imported from @web/core/network/rpc
 * - this.do_action() → this.action.doAction()
 * - QWeb.render() → owl templates (kept for compatibility via renderToString)
 * - jQuery $() → native DOM / useRef
 * - session → user service
 * - trigger_up → env.bus.trigger
 * - patch(WebClient) → removed (handled differently in v18)
 */

import { Component, useState, useRef, onMounted, onWillStart, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";
import { browser } from "@web/core/browser/browser";
import { renderToString } from "@web/core/utils/render";

// ─── Constants ────────────────────────────────────────────────────────────────

const KS_DATE_FILTER_SELECTIONS = {
    l_none:                     _t("Date Filter"),
    l_day:                      _t("Today"),
    t_week:                     _t("This Week"),
    td_week:                    _t("Week To Date"),
    t_month:                    _t("This Month"),
    td_month:                   _t("Month to Date"),
    t_quarter:                  _t("This Quarter"),
    td_quarter:                 _t("Quarter to Date"),
    t_year:                     _t("This Year"),
    td_year:                    _t("Year to Date"),
    n_day:                      _t("Next Day"),
    n_week:                     _t("Next Week"),
    n_month:                    _t("Next Month"),
    n_quarter:                  _t("Next Quarter"),
    n_year:                     _t("Next Year"),
    ls_day:                     _t("Last Day"),
    ls_week:                    _t("Last Week"),
    ls_month:                   _t("Last Month"),
    ls_quarter:                 _t("Last Quarter"),
    ls_year:                    _t("Last Year"),
    l_week:                     _t("Last 7 days"),
    l_month:                    _t("Last 30 days"),
    l_quarter:                  _t("Last 90 days"),
    l_year:                     _t("Last 365 days"),
    ls_past_until_now:          _t("Past Till Now"),
    ls_pastwithout_now:         _t("Past Excluding Today"),
    n_future_starting_now:      _t("Future Starting Now"),
    n_futurestarting_tomorrow:  _t("Future Starting Tomorrow"),
    l_custom:                   _t("Custom Filter"),
};

const KS_DATE_FILTER_ORDER = [
    "l_day","t_week","t_month","t_quarter","t_year",
    "td_week","td_month","td_quarter","td_year",
    "n_day","n_week","n_month","n_quarter","n_year",
    "ls_day","ls_week","ls_month","ls_quarter","ls_year",
    "l_week","l_month","l_quarter","l_year",
    "ls_past_until_now","ls_pastwithout_now",
    "n_future_starting_now","n_futurestarting_tomorrow","l_custom",
];

const FILE_TYPE_MAGIC_WORD = { "/": "jpg", R: "gif", i: "png", P: "svg+xml" };

// ─── Helpers ──────────────────────────────────────────────────────────────────

function ksRgbaFormat(val) {
    if (!val) return "rgba(0,0,0,0)";
    const parts = val.split(",");
    if (parts.length === 4) return `rgba(${parts.join(",")})`;
    if (parts.length === 3) return `rgba(${parts.join(",")},1)`;
    return val;
}

function ksDarkColor(color, opacity, percent) {
    if (!color) return color;
    const parts = color.split(",");
    const r = Math.max(0, parseInt(parts[0]) + percent);
    const g = Math.max(0, parseInt(parts[1]) + percent);
    const b = Math.max(0, parseInt(parts[2]) + percent);
    return `${r},${g},${b},${opacity}`;
}

function ksGetGcd(a, b) {
    return b === 0 ? a : ksGetGcd(b, a % b);
}

// ─── Main Component ───────────────────────────────────────────────────────────

export class KsDashboardNinja extends Component {
    static template = "ks_dashboard_ninja.KsDashboardNinja";
    static props = {
        action: Object,
        "*": true,
    };

    setup() {
        // Services
        this.action   = useService("action");
        this.dialog   = useService("dialog");
        this.notification = useService("notification");
        this.router   = useService("router");
        this.menu     = useService("menu");

        // Refs
        this.rootRef  = useRef("root");

        // State
        this.state = useState({
            dashboardData: {},
            isLoaded: false,
            editMode: false,
            dateFilterSelection: false,
            dateFilterStartDate: false,
            dateFilterEndDate: false,
            userContext: {},
        });

        // Internal vars
        this.ks_dashboard_id    = this.props.action?.params?.ks_dashboard_id;
        this.ksIsDashboardManager = false;
        this.ksDashboardEditMode  = false;
        this.ksNewDashboardName   = false;
        this.ksAllowItemClick     = true;
        this.ksUpdateDashboard    = {};
        this.gridstackConfig      = {};
        this.grid                 = false;
        this.chartMeasure         = {};
        this.chart_container      = {};
        this.list_container       = {};
        this.ksChartColorOptions  = ["default", "cool", "warm", "neon"];
        this.date_format          = "DD/MM/YYYY";
        this.datetime_format      = "DD/MM/YYYY HH:mm:ss";
        this.gridstack_options    = {
            staticGrid: true,
            float: false,
            cellHeight: 80,
            styleInHead: true,
        };

        const reloadCtx = this.props.action?.context;
        this.reload_menu_option = {
            reload:  reloadCtx?.ks_reload_menu,
            menu_id: reloadCtx?.ks_menu_id,
        };

        // Lifecycle
        onWillStart(async () => {
            await this._ksFetchData();
        });

        onMounted(() => {
            this._ksInitGridstack();
            this._ksRenderDashboard();
            this._ks_set_update_interval();
            if (this.reload_menu_option.reload && this.reload_menu_option.menu_id) {
                this.env.bus.trigger("reload_menu_data", { keep_open: true });
            }
        });

        onWillUnmount(() => {
            this._ks_remove_update_interval();
            if (this.ksDashboardEditMode) this._ksSaveCurrentLayout();
        });
    }

    // ── Data fetching ──────────────────────────────────────────────────────────

    _getContext() {
        const ctx = {
            ksDateFilterSelection:  this.state.dateFilterSelection,
            ksDateFilterStartDate:  this.state.dateFilterStartDate,
            ksDateFilterEndDate:    this.state.dateFilterEndDate,
        };
        if (
            this.state.userContext.ksDateFilterSelection !== undefined &&
            this.state.dateFilterSelection !== "l_none"
        ) {
            return Object.assign({}, this.state.userContext);
        }
        return ctx;
    }

    async _ksFetchData() {
        const result = await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.board",
            method: "ks_fetch_dashboard_data",
            args:   [this.ks_dashboard_id],
            kwargs: { context: this._getContext() },
        });
        this.state.dashboardData = result;
        this.state.dashboardData.ks_item_data = this.state.dashboardData.ks_item_data || {};
        this.state.isLoaded = true;
    }

    async _ksFetchItemsData() {
        const promises = this.state.dashboardData.ks_dashboard_items_ids.map(async (item_id) => {
            const result = await rpc("/web/dataset/call_kw", {
                model:  "ks_dashboard_ninja.board",
                method: "ks_fetch_item",
                args:   [[item_id], this.ks_dashboard_id, this._ksGetParamsForItemFetch(item_id)],
                kwargs: { context: this._getContext() },
            });
            this.state.dashboardData.ks_item_data[item_id] = result[item_id];
        });
        return Promise.all(promises);
    }

    _ksGetParamsForItemFetch() {
        return {};
    }

    async ksFetchUpdateItem(item_id) {
        const result = await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.board",
            method: "ks_fetch_item",
            args:   [[parseInt(item_id)], this.ks_dashboard_id, this._ksGetParamsForItemFetch(parseInt(item_id))],
            kwargs: { context: this._getContext() },
        });
        this.state.dashboardData.ks_item_data[item_id] = result[item_id];
        this.ksUpdateDashboardItem([item_id]);
    }

    // ── Update interval ────────────────────────────────────────────────────────

    _ks_set_update_interval() {
        const data = this.state.dashboardData;
        if (!data.ks_item_data) return;
        Object.keys(data.ks_item_data).forEach((item_id) => {
            const item_data   = data.ks_item_data[item_id];
            const updateValue = data.ks_set_interval;
            if (updateValue && !(item_id in this.ksUpdateDashboard)) {
                const fn = ["ks_tile", "ks_list_view", "ks_kpi", "ks_to_do"].includes(
                    item_data.ks_dashboard_item_type
                )
                    ? () => this.ksFetchUpdateItem(item_id)
                    : () => this.ksFetchChartItem(item_id);
                this.ksUpdateDashboard[item_id] = browser.setInterval(fn, updateValue);
            }
        });
    }

    _ks_remove_update_interval() {
        Object.values(this.ksUpdateDashboard).forEach((interval) =>
            browser.clearInterval(interval)
        );
        this.ksUpdateDashboard = {};
    }

    // ── Gridstack ──────────────────────────────────────────────────────────────

    _ksInitGridstack() {
        const el = this.rootRef.el?.querySelector(".grid-stack");
        if (!el || typeof GridStack === "undefined") return;
        this.grid = GridStack.init(this.gridstack_options, el);
        this.grid.setStatic(true);
    }

    ks_get_current_gridstack_config() {
        const el = document.querySelector(".grid-stack");
        if (!el || !el.gridstack) return {};
        const nodes = el.gridstack.engine.nodes;
        const config = {};
        for (const node of nodes) {
            config[node.id] = { x: node.x, y: node.y, w: node.w, h: node.h };
        }
        return config;
    }

    async _ksSaveCurrentLayout() {
        const grid_config = this.ks_get_current_gridstack_config();
        let rec_id = this.state.dashboardData.ks_gridstack_config_id;
        this.state.dashboardData.ks_gridstack_config = JSON.stringify(grid_config);
        if (
            this.state.dashboardData.ks_selected_board_id &&
            this.state.dashboardData.ks_child_boards
        ) {
            this.state.dashboardData.ks_child_boards[
                this.state.dashboardData.ks_selected_board_id
            ][1] = JSON.stringify(grid_config);
            if (this.state.dashboardData.ks_selected_board_id !== "ks_default") {
                rec_id = this.state.dashboardData.ks_selected_board_id;
            }
        }
        await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.child_board",
            method: "write",
            args:   [rec_id, { ks_gridstack_config: JSON.stringify(grid_config) }],
            kwargs: {},
        });
    }

    // ── Render helpers ─────────────────────────────────────────────────────────

    _ksRgbaFormat(val) { return ksRgbaFormat(val); }
    ks_get_dark_color(color, opacity, percent) { return ksDarkColor(color, opacity, percent); }

    _ksMainBodyStyle(bg, fg, tile) {
        const bgRgba   = ksRgbaFormat(bg);
        const darkBg   = ksRgbaFormat(ksDarkColor(
            tile.ks_background_color?.split(",")[0],
            tile.ks_background_color?.split(",")[1],
            -10
        ));
        return {
            background_style: `background-color:${bgRgba};color:${ksRgbaFormat(fg)};`,
            style_image_body_l2: `background-color:${darkBg};`,
        };
    }

    _ksRenderDashboard() {
        const root = this.rootRef.el;
        if (!root) return;
        root.classList.add("ks_dashboard_ninja", "d-flex", "flex-column");
        // Actual rendering is handled by the OWL template
        // This method triggers any post-render DOM work
        this._ksRenderDashboardItems();
    }

    _ksSortItems(ks_item_data) {
        const items = [];
        const item_data = Object.assign({}, ks_item_data);
        if (this.state.dashboardData.ks_gridstack_config) {
            this.gridstackConfig = JSON.parse(this.state.dashboardData.ks_gridstack_config);
            const entries = Object.entries(this.gridstackConfig).map(([id, v]) => ({
                ...v, id,
            }));
            entries.sort((a, b) => 35 * a.y + a.x - (35 * b.y + b.x));
            for (const entry of entries) {
                if (item_data[entry.id]) {
                    items.push(item_data[entry.id]);
                    delete item_data[entry.id];
                }
            }
        }
        return items.concat(Object.values(item_data));
    }

    _ksRenderDashboardItems() {
        if (!this.grid || !this.state.dashboardData.ks_item_data) return;
        if (this.state.dashboardData.ks_gridstack_config) {
            this.gridstackConfig = JSON.parse(this.state.dashboardData.ks_gridstack_config);
        }
        const items = this._ksSortItems(this.state.dashboardData.ks_item_data);
        for (const item of items) {
            this._ksAddItemToGrid(item);
        }
    }

    _ksAddItemToGrid(item) {
        if (!this.grid) return;
        const cfg    = this.gridstackConfig[item.id];
        const baseOpts = cfg
            ? { x: cfg.x, y: cfg.y, w: cfg.w, h: cfg.h, autoPosition: false }
            : { x: 0, y: 0, autoPosition: true };

        let el;
        if (item.ks_dashboard_item_type === "ks_tile") {
            el = this._ksRenderTileElement(item);
            this.grid.addWidget(el, { ...baseOpts, minW: 2, minH: 2, id: item.id });
        } else if (item.ks_dashboard_item_type === "ks_kpi") {
            el = this._ksRenderKpiElement(item);
            this.grid.addWidget(el, { ...baseOpts, w: cfg?.w || 3, h: cfg?.h || 2, minW: 2, minH: 2, id: item.id });
        } else if (item.ks_dashboard_item_type === "ks_list_view") {
            el = this._ksRenderListViewElement(item);
            this.grid.addWidget(el, { ...baseOpts, w: cfg?.w || 5, h: cfg?.h || 4, minW: 3, minH: 3, id: item.id });
        } else {
            el = this._ksRenderChartElement(item);
            if (el) this.grid.addWidget(el, { ...baseOpts, w: cfg?.w || 6, h: cfg?.h || 4, minW: 3, minH: 3, id: item.id });
        }
    }

    _ksRenderTileElement(tile) {
        const el = document.createElement("div");
        el.className = "grid-stack-item ks_dashboarditem_id";
        el.id = String(tile.id);
        const bgColor = ksRgbaFormat(tile.ks_background_color);
        const fgColor = ksRgbaFormat(tile.ks_font_color);
        el.innerHTML = `
            <div class="grid-stack-item-content ks_dashboard_tile_layout" style="background-color:${bgColor};color:${fgColor};">
                <div class="ks_tile_header">
                    <span class="ks_tile_name">${tile.name || ""}</span>
                </div>
                <div class="ks_tile_body">
                    <span class="ks_record_count">${tile.ks_record_count ?? 0}</span>
                </div>
            </div>`;
        return el;
    }

    _ksRenderKpiElement(item) {
        const el = document.createElement("div");
        el.className = "grid-stack-item ks_dashboarditem_id";
        el.id = String(item.id);
        el.innerHTML = `
            <div class="grid-stack-item-content">
                <div class="ks_kpi_card p-3">
                    <div class="ks_kpi_name fw-bold">${item.name || ""}</div>
                    <div class="ks_kpi_value display-6">${item.ks_record_count ?? 0}</div>
                </div>
            </div>`;
        return el;
    }

    _ksRenderListViewElement(item) {
        const listData = item.ks_list_view_data ? JSON.parse(item.ks_list_view_data) : {};
        const rows = listData.data_rows || [];
        const headers = listData.label || [];
        const el = document.createElement("div");
        el.className = "grid-stack-item ks_dashboarditem_id";
        el.id = String(item.id);
        const headerHtml = headers.map((h) => `<th>${h}</th>`).join("");
        const rowHtml = rows
            .map((r) => `<tr>${(r.data || []).map((d) => `<td>${d ?? ""}</td>`).join("")}</tr>`)
            .join("");
        el.innerHTML = `
            <div class="grid-stack-item-content">
                <div class="ks_list_card h-100 d-flex flex-column">
                    <div class="ks_list_header p-2 fw-bold">${item.name || ""}</div>
                    <div class="overflow-auto flex-grow-1">
                        <table class="table table-sm table-striped">
                            <thead><tr>${headerHtml}</tr></thead>
                            <tbody>${rowHtml}</tbody>
                        </table>
                    </div>
                </div>
            </div>`;
        this.list_container[item.id] = el;
        return el;
    }

    _ksRenderChartElement(item) {
        const el = document.createElement("div");
        el.className = "grid-stack-item ks_dashboarditem_id";
        el.id = String(item.id);
        const canvasId = `ks_chart_canvas_${item.id}`;
        el.innerHTML = `
            <div class="grid-stack-item-content">
                <div class="ks_chart_card h-100 d-flex flex-column">
                    <div class="ks_chart_header p-2">
                        <span class="ks_chart_title fw-bold">${item.name || ""}</span>
                    </div>
                    <div class="ks_chart_body flex-grow-1 p-2">
                        <canvas id="${canvasId}" class="ks_chart_canvas_id"></canvas>
                    </div>
                </div>
            </div>`;
        // Render chart after DOM insertion
        browser.setTimeout(() => {
            const canvas = document.getElementById(canvasId);
            if (canvas && typeof Chart !== "undefined") {
                this._ksRenderChart(el, item);
            }
        }, 0);
        return el;
    }

    // ── Chart rendering ────────────────────────────────────────────────────────

    async ksFetchChartItem(id) {
        const result = await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.board",
            method: "ks_fetch_item",
            args:   [[parseInt(id)], this.ks_dashboard_id, this._ksGetParamsForItemFetch(parseInt(id))],
            kwargs: { context: this._getContext() },
        });
        const item_data = result[id];
        this.state.dashboardData.ks_item_data[id] = item_data;
        this.ksUpdateDashboardItem([id]);
    }

    _ksRenderChart(container, item) {
        const chart_data = JSON.parse(item.ks_chart_data || "{}");
        const canvas = container.querySelector("canvas");
        if (!canvas || typeof Chart === "undefined") return;

        const type_map = {
            ks_bar_chart:            "bar",
            ks_horizontalBar_chart:  "horizontalBar",
            ks_line_chart:           "line",
            ks_area_chart:           "line",
            ks_pie_chart:            "pie",
            ks_doughnut_chart:       "doughnut",
            ks_polarArea_chart:      "polarArea",
            ks_radar_view:           "radar",
        };
        const chartType = type_map[item.ks_dashboard_item_type] || "bar";

        if (this.chart_container[item.id]) {
            this.chart_container[item.id].destroy();
        }

        try {
            this.chart_container[item.id] = new Chart(canvas, {
                type: chartType,
                data: {
                    labels:   chart_data.labels || [],
                    datasets: chart_data.datasets || [],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: !item.ks_hide_legend } },
                },
            });
        } catch (e) {
            console.warn("KS Dashboard: Chart render error", e);
        }
    }

    // ── Dashboard item update ──────────────────────────────────────────────────

    async ksUpdateDashboardItem(ids) {
        for (const id of ids) {
            const item = this.state.dashboardData.ks_item_data[id];
            if (!item) continue;
            const container = this.rootRef.el?.querySelector(
                `.grid-stack-item[gs-id="${id}"], .grid-stack-item[id="${id}"]`
            );
            if (!container) continue;

            if (item.ks_dashboard_item_type === "ks_tile") {
                const countEl = container.querySelector(".ks_record_count");
                if (countEl) countEl.textContent = item.ks_record_count ?? 0;
            } else if (item.ks_dashboard_item_type === "ks_kpi") {
                const valEl = container.querySelector(".ks_kpi_value");
                if (valEl) valEl.textContent = item.ks_record_count ?? 0;
            } else if (item.ks_dashboard_item_type === "ks_list_view") {
                const bodyEl = container.querySelector(".overflow-auto");
                if (bodyEl) {
                    const newEl = this._ksRenderListViewElement(item);
                    bodyEl.replaceWith(newEl.querySelector(".overflow-auto"));
                }
            } else {
                this._ksRenderChart(container, item);
            }
        }
    }

    // ── Event handlers ─────────────────────────────────────────────────────────

    async _onKsItemClick(ev) {
        if (!this.ksAllowItemClick) return;
        const target = ev.target.closest(".ks_dashboarditem_id");
        if (!target) return;
        const item_id = target.id;
        const item = this.state.dashboardData.ks_item_data[item_id];
        if (!item) return;

        if (item.action) {
            const action = Array.isArray(item.action) ? item.action[0] : item.action;
            await this.action.doAction(action);
        } else if (item.ks_model_name) {
            await this.action.doAction({
                type:       "ir.actions.act_window",
                name:       item.name,
                res_model:  item.ks_model_name,
                domain:     item.ks_domain || [],
                views:      [[false, "list"], [false, "form"]],
                target:     "current",
            });
        }
    }

    async ksOnDashboardDuplicateClick(ev) {
        ev.preventDefault();
        const result = await rpc("/web/dataset/call_kw", {
            model:  "ks.dashboard.duplicate.wizard",
            method: "DuplicateDashBoard",
            args:   [this.ks_dashboard_id],
            kwargs: {},
        });
        await this.action.doAction(result);
    }

    async ksOnDashboardImportClick(ev) {
        ev.preventDefault();
        const result = await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.board",
            method: "ks_open_import",
            args:   [this.ks_dashboard_id],
            kwargs: { dashboard_id: this.ks_dashboard_id },
        });
        await this.action.doAction(result);
    }

    async ksOnDashboardExportClick(ev) {
        ev.preventDefault();
        const result = await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.board",
            method: "ks_dashboard_export",
            args:   [JSON.stringify(this.ks_dashboard_id)],
            kwargs: { dashboard_id: JSON.stringify(this.ks_dashboard_id) },
        });
        // Trigger file download via fetch
        const blob = new Blob([JSON.stringify(result)], { type: "application/json" });
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement("a");
        a.href     = url;
        a.download = "dashboard_ninja.json";
        a.click();
        URL.revokeObjectURL(url);
    }

    ksOnDashboardSettingClick(ev) {
        this.action.doAction({
            type:      "ir.actions.act_window",
            name:      _t("ks_open_setting"),
            res_model: "ks_dashboard_ninja.board",
            res_id:    this.ks_dashboard_id,
            views:     [[false, "form"]],
            view_mode: "form",
            target:    "new",
            context:   { create: false },
        });
    }

    async ksOnDashboardDeleteClick(ev) {
        ev.preventDefault();
        const result = await rpc("/web/dataset/call_kw", {
            model:  "ks.dashboard.delete.wizard",
            method: "DeleteDashBoard",
            args:   [this.ks_dashboard_id],
            kwargs: {},
        });
        await this.action.doAction(result);
    }

    async ksOnDashboardCreateClick(ev) {
        ev.preventDefault();
        const action = await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.board",
            method: "ks_create_dashboard",
            args:   [this.ks_dashboard_id],
            kwargs: {},
        });
        action.target = "new";
        await this.action.doAction(action);
    }

    async onAddItemTypeClick(ev) {
        await this.action.doAction({
            type:      "ir.actions.act_window",
            name:      _t("Add Dashboard Item"),
            res_model: "ks_dashboard_ninja.item",
            views:     [[false, "form"]],
            view_mode: "form",
            target:    "new",
            context:   { ks_dashboard_ninja_board_id: this.ks_dashboard_id },
        });
    }

    _ksToggleEditMode() {
        this.ksDashboardEditMode = !this.ksDashboardEditMode;
        if (this.grid) {
            this.grid.setStatic(!this.ksDashboardEditMode);
        }
    }

    async _onKsDeleteItemClick(ev) {
        const item_id = ev.target.closest("[data-item_id]")?.dataset?.item_id;
        if (!item_id) return;
        await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.item",
            method: "unlink",
            args:   [[parseInt(item_id)]],
            kwargs: {},
        });
        this.notification.add(_t("Item deleted"), { type: "success" });
        await this._ksFetchData();
        this._ksRenderDashboard();
    }

    async _onKsItemCustomizeClick(ev) {
        const item_id = ev.target.closest("[data-item_id]")?.dataset?.item_id;
        if (!item_id) return;
        await this.action.doAction({
            type:      "ir.actions.act_window",
            res_model: "ks_dashboard_ninja.item",
            res_id:    parseInt(item_id),
            views:     [[false, "form"]],
            target:    "new",
        });
    }

    async onKsDuplicateItemClick(ev) {
        const item_id  = ev.target.closest("[data-item_id]")?.dataset?.item_id;
        const dash_id  = ev.target.closest("[data-dashboard_id]")?.dataset?.dashboard_id || this.ks_dashboard_id;
        if (!item_id) return;
        await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.item",
            method: "copy",
            args:   [parseInt(item_id), { ks_dashboard_ninja_board_id: parseInt(dash_id) }],
            kwargs: {},
        });
        this.notification.add(_t("Item duplicated"), { type: "success" });
        await this._ksFetchData();
        await this._ksFetchItemsData();
        this._ksRenderDashboard();
    }

    async onKsMoveItemClick(ev) {
        const item_id = ev.target.closest("[data-item_id]")?.dataset?.item_id;
        const dash_id = ev.target.closest("[data-dashboard_id]")?.dataset?.dashboard_id;
        if (!item_id || !dash_id) return;
        await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.item",
            method: "write",
            args:   [parseInt(item_id), { ks_dashboard_ninja_board_id: parseInt(dash_id) }],
            kwargs: {},
        });
        this.notification.add(_t("Item moved"), { type: "success" });
        await this._ksFetchData();
        await this._ksFetchItemsData();
        this._ks_remove_update_interval();
        this._ksRenderDashboard();
        this._ks_set_update_interval();
    }

    // ── Date filter ────────────────────────────────────────────────────────────

    async _ksOnDateFilterMenuSelect(ev) {
        if (ev.target.id === "ks_date_selector_container") return;
        const sel = ev.target.parentElement.id;
        this.rootRef.el?.querySelectorAll(".ks_date_filter_selected").forEach((el) =>
            el.classList.remove("ks_date_filter_selected")
        );
        ev.target.parentElement.classList.add("ks_date_filter_selected");
        const selLabel = this.rootRef.el?.querySelector("#ks_date_filter_selection");
        if (selLabel) selLabel.textContent = KS_DATE_FILTER_SELECTIONS[sel] || "";

        if (sel !== "l_custom") {
            if (sel === "l_none") {
                await this._onKsClearDateValues(true);
            } else {
                await this._onKsApplyDateFilter();
            }
            this.rootRef.el?.querySelector(".ks_date_input_fields")?.classList.add("ks_hide");
        } else {
            this.rootRef.el?.querySelector(".ks_date_input_fields")?.classList.remove("ks_hide");
            this.rootRef.el?.querySelector(".apply-dashboard-date-filter")?.classList.remove("ks_hide");
            this.rootRef.el?.querySelector(".clear-dashboard-date-filter")?.classList.remove("ks_hide");
        }
    }

    async _onKsApplyDateFilter(ev) {
        const selected = this.rootRef.el?.querySelector(".ks_date_filter_selected")?.id;
        if (!selected) return;

        if (selected !== "l_custom") {
            this.state.dateFilterSelection = selected;
        } else {
            const startInput = this.rootRef.el?.querySelector("#ks_start_date_picker")?.value;
            const endInput   = this.rootRef.el?.querySelector("#ks_end_date_picker")?.value;
            if (!startInput || !endInput) {
                alert(_t("Please enter start date and end date"));
                return;
            }
            this.state.dateFilterSelection  = "l_custom";
            this.state.dateFilterStartDate  = startInput;
            this.state.dateFilterEndDate    = endInput;
        }

        this.state.userContext = {
            ksDateFilterSelection: this.state.dateFilterSelection,
            ksDateFilterStartDate: this.state.dateFilterStartDate,
            ksDateFilterEndDate:   this.state.dateFilterEndDate,
        };

        await this._ksFetchItemsData();
        const ids = Object.keys(this.state.dashboardData.ks_item_data).filter(
            (id) => this.state.dashboardData.ks_item_data[id].ks_dashboard_item_type !== "ks_to_do"
        );
        await this.ksUpdateDashboardItem(ids);
        this.rootRef.el?.querySelector(".apply-dashboard-date-filter")?.classList.add("ks_hide");
        this.rootRef.el?.querySelector(".clear-dashboard-date-filter")?.classList.add("ks_hide");
    }

    async _onKsClearDateValues(ks_l_none = false) {
        this.state.dateFilterSelection = "l_none";
        this.state.dateFilterStartDate = false;
        this.state.dateFilterEndDate   = false;
        this.state.userContext = {
            ksDateFilterSelection: "l_none",
            ksDateFilterStartDate: false,
            ksDateFilterEndDate:   false,
        };

        await this._ksFetchItemsData();
        this.rootRef.el?.querySelector(".ks_date_input_fields")?.classList.add("ks_hide");
        const ids = Object.keys(this.state.dashboardData.ks_item_data).filter(
            (id) => this.state.dashboardData.ks_item_data[id].ks_dashboard_item_type !== "ks_to_do"
        );
        await this.ksUpdateDashboardItem(ids);
    }

    // ── Layout management ──────────────────────────────────────────────────────

    async _onKsSaveLayoutClick() {
        await this._ksSaveCurrentLayout();
        this._ksToggleEditMode();
        this.notification.add(_t("Layout saved"), { type: "success" });
    }

    async _onKsCreateLayoutClick() {
        const name = this.ksNewDashboardName || this.state.dashboardData.name;
        const grid_config = this.ks_get_current_gridstack_config();
        const result = await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.child_board",
            method: "create",
            args:   [{
                name:                   name,
                ks_dashboard_ninja_id:  this.ks_dashboard_id,
                ks_gridstack_config:    JSON.stringify(grid_config),
                company_id:             false,
            }],
            kwargs: {},
        });
        this.notification.add(_t("Layout created"), { type: "success" });
        await this._ksFetchData();
    }

    async ks_update_child_board_value(title, res_id, grid_config) {
        await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.board",
            method: "update_child_board",
            args:   ["update", this.ks_dashboard_id, {
                ks_selected_board_id: res_id,
            }],
            kwargs: {},
        });
    }

    // ── AI Dashboard ───────────────────────────────────────────────────────────

    createaidash(ev) {
        this.action.doAction({
            type:      "ir.actions.act_window",
            name:      _t("Generate items with AI"),
            res_model: "ks_dashboard_ninja.arti_int",
            views:     [[false, "form"]],
            view_mode: "form",
            target:    "new",
            context:   { ks_dashboard_id: this.ks_dashboard_id },
        });
    }

    createaidashboard(ev) {
        this.action.doAction({
            type:      "ir.actions.act_window",
            name:      _t("Generate Dashboard with AI"),
            res_model: "ks_dashboard_ninja.ai_dashboard",
            views:     [[false, "form"]],
            view_mode: "form",
            target:    "new",
            context:   { ks_dashboard_id: this.ks_dashboard_id },
        });
    }

    // ── List view pagination ───────────────────────────────────────────────────

    async ksLoadMoreRecords(ev) {
        const itemId        = ev.currentTarget.dataset.itemId;
        const ks_offset     = ev.currentTarget.parentElement.dataset.next_offset;
        const ks_int_count  = ev.currentTarget.parentElement.dataset.prevOffset;
        const params        = this._ksGetParamsForItemFetch(parseInt(itemId));
        const result = await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.board",
            method: "ks_get_list_view_data_offset",
            args:   [parseInt(itemId), { ks_intial_count: ks_int_count, offset: ks_offset },
                     parseInt(this.ks_dashboard_id), params],
            kwargs: { context: this._getContext() },
        });
        this.state.dashboardData.ks_item_data[itemId].ks_list_view_data = result.ks_list_view_data;
        await this.ksUpdateDashboardItem([itemId]);
    }

    async ksLoadPreviousRecords(ev) {
        const itemId    = ev.currentTarget.dataset.itemId;
        const offset    = this.state.dashboardData.ks_item_data[itemId].ks_pagination_limit;
        const ks_offset = parseInt(ev.currentTarget.parentElement.dataset.prevOffset) - (offset + 1);
        const ks_int    = ev.currentTarget.parentElement.dataset.next_offset;
        const params    = this._ksGetParamsForItemFetch(parseInt(itemId));
        const result = await rpc("/web/dataset/call_kw", {
            model:  "ks_dashboard_ninja.board",
            method: "ks_get_list_view_data_offset",
            args:   [parseInt(itemId), { ks_intial_count: ks_int, offset: ks_offset },
                     parseInt(this.ks_dashboard_id), params],
            kwargs: { context: this._getContext() },
        });
        this.state.dashboardData.ks_item_data[itemId].ks_list_view_data = result.ks_list_view_data;
        await this.ksUpdateDashboardItem([itemId]);
    }

    // ── Utility ────────────────────────────────────────────────────────────────

    ks_get_gcd(a, b) { return ksGetGcd(a, b); }

    _ks_get_rgba_format(val) { return ksRgbaFormat(val); }

    ksChartColors(palette, chart, chartType, chartFamily, stacked, semi, showData, data, item) {
        // Color palette application — delegated to KsGlobalFunction if available
        if (typeof KsGlobalFunction !== "undefined" && KsGlobalFunction.ksChartColors) {
            KsGlobalFunction.ksChartColors(palette, chart, chartType, chartFamily, stacked, semi, showData, data, item);
        }
    }
}

// ─── Registration ─────────────────────────────────────────────────────────────

registry.category("actions").add("ks_dashboard_ninja", KsDashboardNinja);
