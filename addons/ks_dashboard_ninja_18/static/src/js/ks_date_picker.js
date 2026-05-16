/** @odoo-module **/
import { Component, useState, useRef, onMounted, onWillStart, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";


    
    
    datepicker.DateWidget.include({

        _onDateTimePickerShow: function() {
            this._super.apply(this, arguments);

            if (this.name === "ks_dashboard") {
                window.removeEventListener('scroll', this._onScroll, true);
            }
        },
    });