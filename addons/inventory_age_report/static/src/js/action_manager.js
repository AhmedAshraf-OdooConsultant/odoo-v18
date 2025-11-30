/** @odoo-module **/

import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { services } from "@web/core/ui/ui_service"; // Import the services object

function downloadXlsxReport(action) {
    const ui = services.ui; // Access the UI service directly from the services object
    ui.block();
    return new Promise((resolve, reject) => {
        session.get_file({
            url: '/xlsx_reports',
            data: action.params.data,
            success: resolve,
            error: (error) => {
                console.error("Error during XLSX report download:", error);
                reject(error);
            },
            complete: ui.unblock,
        });
    });
}

registry.category("actions").add("inventory_age_report.report_inventory_breakdown_xlsx", downloadXlsxReport);
