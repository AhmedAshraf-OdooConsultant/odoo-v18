import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

patch(AccountReportFilters.prototype, {
    get hasUIFilter() {
            return super.hasUIFilter || this.controller.filters.show_hide_unknown_partner_lines !== "never" ;
    },
    get hasExtraOptionsFilter() {
        return super.hasExtraOptionsFilter || "hide_unknown_partner_lines" in this.controller.options;
    },
    async toggleHideUnknownPartnerLines() {

        // Avoid calling the database when this filter is toggled; as the exact same lines would be returned; just reassign visibility.
        await this.controller.toggleOption("hide_unknown_partner_lines", true);
        console.log("controller.options.show_hide_unknown_partner_lines--------", this.controller.options.hide_unknown_partner_lines)
        this.controller.saveSessionOptions(this.controller.options);
        this.controller.setLineVisibility(this.controller.lines);
    },
    async toggleHideZeroLines() {
        // Avoid calling the database when this filter is toggled; as the exact same lines would be returned; just reassign visibility.
        await this.controller.toggleOption("hide_0_lines", true);

        this.controller.saveSessionOptions(this.controller.options);
        this.controller.setLineVisibility(this.controller.lines);
    }
});
