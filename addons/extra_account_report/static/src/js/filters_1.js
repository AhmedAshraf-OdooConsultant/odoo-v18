/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { WarningDialog } from "@web/core/errors/error_dialogs";
import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

export class HideUnknownPartnerLinesFilters extends AccountReportFilters {
    static template = "extra_account_report.HideUnknownPartnerLinesFilters";

}

AccountReport.registerCustomComponent(HideUnknownPartnerLinesFilters);
