/** @odoo-module **/

import { Component, onMounted, onWillStart, onPatched, onWillUnmount, useState, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { browser } from "@web/core/browser/browser";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { serializeDateTime, deserializeDateTime } from "@web/core/l10n/dates";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const STORAGE_KEY = "akshab_stock_dashboard_filters_v1";

const COLORS = {
    green: "#1F3D2F",
    green2: "#2E7D4F",
    green3: "#7B8F84",
    gold: "#B99A5B",
    goldLight: "#D9C9A0",
    amber: "#C08A2E",
    red: "#A94442",
    redLight: "#E3B4B2",
    blue: "#4A6FA5",
    grey: "#9A9A9A",
    beige: "#E9E3D4",
};

// metrics where a decrease is an improvement
const LOWER_IS_BETTER = new Set([
    "stagnant_value", "stagnant_pct", "stagnant_count", "slow_value", "slow_pct", "slow_count", "last_value",
    "last_pct", "last_qty", "dsi", "out_count", "no_turnover_count", "no_turnover_value", "no_turnover_pct",
    "max_age", "avg_age", "reorder_count", "transfer_count", "transfer_value",
]);
const NEUTRAL = new Set(["total_value", "total_qty", "product_count", "opening_value", "avg_inventory", "cogs",
    "sales_qty", "total_sale_value", "coverage", "expected_cash", "stagnant_cash"]);

function fmtNumber(v, digits = 0) {
    if (v === null || v === undefined || Number.isNaN(v)) {
        return "-";
    }
    return Number(v).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export class AkshabStockDashboard extends Component {
    static template = "akshab_stock_report.Dashboard";
    static components = { MultiRecordSelector, DateTimeInput };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.rootRef = useRef("root");
        this.charts = {};
        this.chartsDirty = false;
        this.state = useState({
            ready: false,
            loading: false,
            error: null,
            filters: null,
            defaults: null,
            companies: [],
            warehouses: [],
            labels: {},
            data: null,
            advanced: false,
            tab: "stagnant",
            reportKind: "full",
            trend: null,
            trendLoading: false,
            trendPoints: 6,
            trendStep: 30,
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            if (window.Chart) {
                window.Chart.defaults.font.family = "Tajawal, 'Segoe UI', Arial, sans-serif";
                window.Chart.defaults.font.size = 12;
                window.Chart.defaults.color = "#444";
            }
            const res = await this.orm.call("akshab.stock.dashboard", "get_filter_defaults", []);
            this.state.defaults = res.filters;
            this.state.companies = res.companies;
            this.state.warehouses = res.warehouses;
            this.state.labels = res.labels;
            this.state.filters = this._restoreFilters(res.filters);
            this.state.ready = true;
            // not awaited: the page mounts at once and shows its own progress indicator
            this.load();
        });
        const drawIfDirty = () => {
            if (this.chartsDirty) {
                this.chartsDirty = false;
                this.renderCharts();
            }
        };
        onMounted(drawIfDirty);
        onPatched(drawIfDirty);
        onWillUnmount(() => this.destroyCharts());
    }

    // ------------------------------------------------------------------
    // Filters
    // ------------------------------------------------------------------
    _restoreFilters(defaults) {
        let saved = null;
        try {
            saved = JSON.parse(browser.localStorage.getItem(STORAGE_KEY) || "null");
        } catch {
            saved = null;
        }
        const filters = { ...defaults };
        if (saved && typeof saved === "object") {
            for (const key of Object.keys(defaults)) {
                if (key in saved && key !== "date_to" && key !== "date_from") {
                    filters[key] = saved[key];
                }
            }
            if (!this.state.companies.some((c) => c.id === filters.company_id)) {
                filters.company_id = defaults.company_id;
            }
        }
        return filters;
    }

    _saveFilters() {
        try {
            browser.localStorage.setItem(STORAGE_KEY, JSON.stringify(this.state.filters));
        } catch {
            // storage unavailable: ignore
        }
    }

    get f() {
        return this.state.filters;
    }

    get companyWarehouses() {
        return this.state.warehouses.filter((w) => w.company_id === this.f.company_id);
    }

    get dateFrom() {
        return this.f.date_from ? deserializeDateTime(this.f.date_from) : false;
    }

    get dateTo() {
        return this.f.date_to ? deserializeDateTime(this.f.date_to) : false;
    }

    onDateFrom(value) {
        if (value) {
            this.f.date_from = serializeDateTime(value);
        }
    }

    onDateTo(value) {
        if (value) {
            this.f.date_to = serializeDateTime(value);
        }
    }

    setPeriod(days) {
        const to = this.dateTo || luxon.DateTime.now();
        this.f.date_from = serializeDateTime(to.minus({ days }));
        this.load();
    }

    onCompanyChange(ev) {
        this.f.company_id = parseInt(ev.target.value, 10);
        this.f.warehouse_ids = [];
        this.f.location_ids = [];
    }

    toggleWarehouse(id) {
        const ids = new Set(this.f.warehouse_ids);
        if (ids.has(id)) {
            ids.delete(id);
        } else {
            ids.add(id);
        }
        this.f.warehouse_ids = [...ids];
        this.load();
    }

    allWarehouses() {
        this.f.warehouse_ids = [];
        this.load();
    }

    isWarehouseSelected(id) {
        return this.f.warehouse_ids.length === 0 || this.f.warehouse_ids.includes(id);
    }

    updateIds(key, resIds) {
        this.f[key] = resIds;
    }

    get locationDomain() {
        return [["usage", "=", "internal"], ["company_id", "=", this.f.company_id]];
    }

    get productDomain() {
        return [["is_storable", "=", true]];
    }

    onNumber(key, ev) {
        const v = parseFloat(ev.target.value);
        if (!Number.isNaN(v)) {
            this.f[key] = v;
        }
    }

    onSelect(key, ev) {
        this.f[key] = ev.target.value;
    }

    toggleAdvanced() {
        this.state.advanced = !this.state.advanced;
    }

    resetFilters() {
        this.state.filters = { ...this.state.defaults };
        this.load();
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------
    async load() {
        this.state.loading = true;
        this.state.error = null;
        this.state.trend = null;
        try {
            const data = await this.orm.call("akshab.stock.dashboard", "get_dashboard_data", [this.f]);
            this.state.data = data;
            this._saveFilters();
            this.chartsDirty = true;
        } catch (e) {
            this.state.error = (e && e.data && e.data.message) || (e && e.message) || String(e);
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async loadTrend() {
        this.state.trendLoading = true;
        try {
            const res = await this.orm.call("akshab.stock.dashboard", "get_trend",
                [this.f, this.state.trendPoints, this.state.trendStep]);
            this.state.trend = res;
            this.chartsDirty = true;
        } catch (e) {
            this.notification.add((e && e.data && e.data.message) || String(e), { type: "danger" });
        } finally {
            this.state.trendLoading = false;
        }
    }

    onTrendPoints(ev) {
        this.state.trendPoints = parseInt(ev.target.value, 10);
    }

    onTrendStep(ev) {
        this.state.trendStep = parseInt(ev.target.value, 10);
    }

    async openReport(fmt) {
        try {
            const action = await this.orm.call("akshab.stock.dashboard", "action_open_report",
                [this.state.reportKind, fmt, this.f]);
            await this.action.doAction(action);
        } catch (e) {
            this.notification.add((e && e.data && e.data.message) || String(e), { type: "danger" });
        }
    }

    onReportKind(ev) {
        this.state.reportKind = ev.target.value;
    }

    setTab(tab) {
        this.state.tab = tab;
    }

    filterCategory(categId) {
        if (!categId) {
            return;
        }
        const ids = new Set(this.f.categ_ids);
        if (ids.has(categId)) {
            ids.delete(categId);
        } else {
            ids.add(categId);
        }
        this.f.categ_ids = [...ids];
        this.load();
    }

    clearCategories() {
        this.f.categ_ids = [];
        this.load();
    }

    // ------------------------------------------------------------------
    // Formatting helpers used by the template
    // ------------------------------------------------------------------
    money(v) {
        return fmtNumber(v, 2);
    }

    qty(v) {
        if (v === null || v === undefined) {
            return "-";
        }
        return Math.abs(v - Math.round(v)) < 0.005 ? fmtNumber(Math.round(v), 0) : fmtNumber(v, 2);
    }

    num(v) {
        return fmtNumber(v, 0);
    }

    ratio(v) {
        return fmtNumber(v, 2);
    }

    pct(v, digits = 1) {
        if (v === null || v === undefined || Number.isNaN(v)) {
            return "-";
        }
        return fmtNumber(v, digits) + "%";
    }

    days(v) {
        return v === null || v === undefined ? "-" : fmtNumber(v, 0) + " يوم";
    }

    get cur() {
        return this.state.data ? this.state.data.meta.currency : "";
    }

    get k() {
        return this.state.data ? this.state.data.kpi : {};
    }

    /** {text, cls} describing the change of a KPI versus the previous period */
    delta(key, kind = "pct") {
        const d = this.state.data && this.state.data.compare[key];
        if (!d || d.previous === null || d.previous === undefined || d.delta === null) {
            return { text: "—", cls: "flat", title: "لا توجد بيانات للفترة السابقة" };
        }
        const up = d.delta > 0.0001;
        const down = d.delta < -0.0001;
        let good = null;
        if (!NEUTRAL.has(key) && (up || down)) {
            good = LOWER_IS_BETTER.has(key) ? down : up;
        }
        let text;
        if (kind === "pts") {
            text = (up ? "+" : "") + fmtNumber(d.delta, 1) + " نقطة";
        } else if (kind === "abs") {
            text = (up ? "+" : "") + fmtNumber(d.delta, 0);
        } else if (kind === "ratio") {
            text = (up ? "+" : "") + fmtNumber(d.delta, 2);
        } else if (d.previous) {
            text = (up ? "+" : "") + fmtNumber(d.delta_pct, 1) + "%";
        } else {
            text = (up ? "+" : "") + fmtNumber(d.delta, 0);
        }
        const arrow = up ? "▲ " : down ? "▼ " : "";
        const cls = good === null ? "flat" : good ? "good" : "bad";
        const title = "الفترة السابقة: " + fmtNumber(d.previous, kind === "pct" ? 2 : 1);
        return { text: arrow + text, cls, title };
    }

    healthClass(score) {
        if (score >= 75) {
            return "good";
        }
        if (score >= 50) {
            return "warn";
        }
        return "bad";
    }

    get tabs() {
        const d = this.state.data;
        if (!d) {
            return [];
        }
        return [
            { key: "stagnant", label: "الأصناف الراكدة", count: d.lists.stagnant_count },
            { key: "oldest", label: "أقدم مخزون", count: d.lists.oldest.length },
            { key: "slow", label: "بطيء الحركة (فائض)", count: d.lists.slow_count },
            { key: "top", label: "الأكثر دوراناً", count: d.turnover.top.length },
            { key: "bottom", label: "الأقل دوراناً", count: d.turnover.bottom.length },
            { key: "none", label: "بلا دوران", count: d.turnover.none_count },
            { key: "out", label: "نافد وله طلب", count: d.lists.out_count },
            { key: "reorder", label: "إعادة طلب", count: d.lists.reorder_count },
            { key: "transfers", label: "إعادة التوزيع بين المستودعات", count: d.lists.transfers_count },
            { key: "plan", label: "خطة التصفية", count: d.plan.rows.length },
            { key: "insights", label: "أبرز النتائج", count: d.insights.length },
        ];
    }

    // ------------------------------------------------------------------
    // Charts (Chart.js, loaded from Odoo's bundle)
    // ------------------------------------------------------------------
    destroyCharts() {
        for (const key of Object.keys(this.charts)) {
            try {
                this.charts[key].destroy();
            } catch {
                // ignore
            }
            delete this.charts[key];
        }
    }

    _chart(key, config) {
        const root = this.rootRef.el;
        if (!root || !window.Chart) {
            return;
        }
        const canvas = root.querySelector(`canvas[data-chart="${key}"]`);
        if (!canvas) {
            return;
        }
        if (this.charts[key]) {
            this.charts[key].destroy();
        }
        const base = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { rtl: true, textDirection: "rtl", labels: { boxWidth: 12, padding: 14 } },
                tooltip: { rtl: true, textDirection: "rtl" },
            },
        };
        config.options = Object.assign({}, base, config.options || {});
        config.options.plugins = Object.assign({}, base.plugins, (config.options && config.options.plugins) || {});
        this.charts[key] = new window.Chart(canvas, config);
    }

    renderCharts() {
        const d = this.state.data;
        if (!d) {
            return;
        }
        const money = (v) => fmtNumber(v, 0);
        const cur = d.meta.currency;

        // 1) aging distribution, current vs previous period
        this._chart("aging", {
            type: "bar",
            data: {
                labels: d.aging.buckets.map((b) => b.label),
                datasets: [
                    {
                        label: "القيمة الحالية (" + cur + ")",
                        data: d.aging.buckets.map((b) => b.value),
                        backgroundColor: d.aging.buckets.map((b) => (b.is_old ? COLORS.red : COLORS.green)),
                        borderRadius: 3,
                    },
                    {
                        label: "بداية الفترة (" + d.meta.date_from_date + ")",
                        data: d.aging.prev_buckets.map((b) => b.value),
                        backgroundColor: COLORS.goldLight,
                        borderRadius: 3,
                    },
                ],
            },
            options: {
                scales: {
                    x: { reverse: true, grid: { display: false } },
                    y: { position: "right", ticks: { callback: (v) => money(v) }, grid: { color: "#EFEBE0" } },
                },
                plugins: {
                    tooltip: { rtl: true, textDirection: "rtl", callbacks: { label: (c) => `${c.dataset.label}: ${fmtNumber(c.parsed.y, 2)} ${cur}` } },
                },
            },
        });

        // 2) status doughnut
        const statuses = d.status_summary.filter((s) => s.value > 0);
        const statusColor = { active: COLORS.green2, slow: COLORS.amber, stagnant: COLORS.red, new: COLORS.blue };
        this._chart("status", {
            type: "doughnut",
            data: {
                labels: statuses.map((s) => s.label),
                datasets: [{ data: statuses.map((s) => s.value), backgroundColor: statuses.map((s) => statusColor[s.key] || COLORS.grey), borderWidth: 1 }],
            },
            options: {
                cutout: "58%",
                plugins: {
                    legend: { position: "bottom", rtl: true, textDirection: "rtl", labels: { boxWidth: 12 } },
                    tooltip: { rtl: true, textDirection: "rtl", callbacks: { label: (c) => `${c.label}: ${fmtNumber(c.parsed, 2)} ${cur}` } },
                },
            },
        });

        // 3) categories: value by status (stacked horizontal)
        const cats = d.categories.slice(0, 12);
        this._chart("categories", {
            type: "bar",
            data: {
                labels: cats.map((c) => c.name),
                datasets: [
                    { label: "نشط", data: cats.map((c) => c.active_value), backgroundColor: COLORS.green2, stack: "s" },
                    { label: "بطيء الحركة", data: cats.map((c) => c.slow_value), backgroundColor: COLORS.amber, stack: "s" },
                    { label: "راكد", data: cats.map((c) => c.stagnant_value), backgroundColor: COLORS.red, stack: "s" },
                ],
            },
            options: {
                indexAxis: "y",
                scales: {
                    x: { stacked: true, reverse: true, ticks: { callback: (v) => money(v) }, grid: { color: "#EFEBE0" } },
                    y: { stacked: true, position: "right", grid: { display: false } },
                },
                plugins: { tooltip: { rtl: true, textDirection: "rtl", callbacks: { label: (c) => `${c.dataset.label}: ${fmtNumber(c.parsed.x, 2)} ${cur}` } } },
            },
        });

        // 4) branches: value now vs previous, stagnant and old
        const whs = d.warehouses;
        this._chart("branches", {
            type: "bar",
            data: {
                labels: whs.map((w) => w.name),
                datasets: [
                    { label: "قيمة المخزون الآن", data: whs.map((w) => w.value), backgroundColor: COLORS.green, borderRadius: 3 },
                    { label: "بداية الفترة", data: whs.map((w) => w.prev_value || 0), backgroundColor: COLORS.goldLight, borderRadius: 3 },
                    { label: "الراكد", data: whs.map((w) => w.stagnant_value), backgroundColor: COLORS.red, borderRadius: 3 },
                    { label: d.meta.last_label, data: whs.map((w) => w.bucket_value[w.bucket_value.length - 1]), backgroundColor: COLORS.amber, borderRadius: 3 },
                ],
            },
            options: {
                scales: {
                    x: { reverse: true, grid: { display: false } },
                    y: { position: "right", ticks: { callback: (v) => money(v) }, grid: { color: "#EFEBE0" } },
                },
                plugins: { tooltip: { rtl: true, textDirection: "rtl", callbacks: { label: (c) => `${c.dataset.label}: ${fmtNumber(c.parsed.y, 2)} ${cur}` } } },
            },
        });

        // 5) turnover by category, current vs previous period
        const tcats = d.categories.filter((c) => c.count_all > 0).slice(0, 12);
        this._chart("turnover", {
            type: "bar",
            data: {
                labels: tcats.map((c) => c.name),
                datasets: [
                    { label: "معدل الدوران السنوي — الفترة الحالية", data: tcats.map((c) => c.turnover_annual || 0), backgroundColor: COLORS.green, borderRadius: 3 },
                    { label: "الفترة السابقة", data: tcats.map((c) => c.prev_turnover_annual || 0), backgroundColor: COLORS.goldLight, borderRadius: 3 },
                ],
            },
            options: {
                scales: {
                    x: { reverse: true, grid: { display: false } },
                    y: { position: "right", grid: { color: "#EFEBE0" }, ticks: { callback: (v) => fmtNumber(v, 1) } },
                },
                plugins: { tooltip: { rtl: true, textDirection: "rtl", callbacks: { label: (c) => `${c.dataset.label}: ${fmtNumber(c.parsed.y, 2)} مرة/سنة` } } },
            },
        });

        // 6) trend
        const t = this.state.trend;
        if (t) {
            const labels = t.points.map((p) => p.label);
            this._chart("trend_value", {
                type: "line",
                data: {
                    labels,
                    datasets: [
                        { label: "قيمة المخزون", data: t.points.map((p) => p.total_value), borderColor: COLORS.green, backgroundColor: COLORS.green, tension: 0.3 },
                        { label: "الراكد", data: t.points.map((p) => p.stagnant_value), borderColor: COLORS.red, backgroundColor: COLORS.red, tension: 0.3 },
                        { label: d.meta.last_label, data: t.points.map((p) => p.last_value), borderColor: COLORS.amber, backgroundColor: COLORS.amber, tension: 0.3 },
                    ],
                },
                options: {
                    scales: { y: { ticks: { callback: (v) => money(v) }, grid: { color: "#EFEBE0" } }, x: { grid: { display: false } } },
                    plugins: { tooltip: { rtl: true, textDirection: "rtl", callbacks: { label: (c) => `${c.dataset.label}: ${fmtNumber(c.parsed.y, 2)} ${cur}` } } },
                },
            });
            this._chart("trend_ratio", {
                type: "line",
                data: {
                    labels,
                    datasets: [
                        { label: "معدل الدوران السنوي", data: t.points.map((p) => p.turnover_annual), borderColor: COLORS.green2, backgroundColor: COLORS.green2, tension: 0.3, yAxisID: "y" },
                        { label: "نسبة الراكد %", data: t.points.map((p) => p.stagnant_pct), borderColor: COLORS.red, backgroundColor: COLORS.red, tension: 0.3, yAxisID: "y1" },
                        { label: "مؤشر الصحة", data: t.points.map((p) => p.health_score), borderColor: COLORS.gold, backgroundColor: COLORS.gold, tension: 0.3, yAxisID: "y1" },
                    ],
                },
                options: {
                    scales: {
                        y: { position: "right", title: { display: true, text: "مرة/سنة" }, grid: { color: "#EFEBE0" } },
                        y1: { position: "left", min: 0, max: 100, title: { display: true, text: "%" }, grid: { display: false } },
                        x: { grid: { display: false } },
                    },
                },
            });
        }
    }
}

registry.category("actions").add("akshab_stock_dashboard", AkshabStockDashboard);
