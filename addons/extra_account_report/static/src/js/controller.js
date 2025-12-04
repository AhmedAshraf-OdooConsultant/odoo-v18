import { patch } from "@web/core/utils/patch";
import { AccountReportController } from "@account_reports/components/account_report/controller";


patch(AccountReportController.prototype, {
    setLineVisibility(linesToAssign) {
        super.setLineVisibility(...arguments);
                if(this.options.hide_unknown_partner_lines){
            linesToAssign.forEach((line) => {
//             console.log("inherited LINE ===========================", line)
//             console.log("inherited LINE ===========================", line.expand_function)

    //                if(!line.trust && line.expand_function){
    //                    line.visible= false
    //                }
            });
        }
    }
});
