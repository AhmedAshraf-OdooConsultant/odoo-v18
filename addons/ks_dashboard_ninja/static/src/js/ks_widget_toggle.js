/** @odoo-module **/
import { Component, useState, useRef, onMounted, onWillStart, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";


    

                
    var KsWidgetToggle = AbstractField.extend({

        supportedFieldTypes: ['char'],

        events: _.extend({}, AbstractField.prototype.events, {
            'change .ks_toggle_icon_input': 'ks_toggle_icon_input_click',
        }),

        _render: function () {
            var self = this;
            self.$el.empty();


            var $view = $(QWeb.render('ks_widget_toggle'));
            if (self.value) {
                $view.find("input[value='" + self.value + "']").prop("checked", true);
            }
            this.$el.append($view)

            if (this.mode === 'readonly') {
                this.$el.find('.ks_select_dashboard_item_toggle').addClass('ks_not_click');
            }
        },

        ks_toggle_icon_input_click: function (e) {
            var self = this;
            self._setValue(e.currentTarget.value);
        }
    });

    var KsWidgetToggleKPI = AbstractField.extend({

        supportedFieldTypes: ['char'],

        events: _.extend({}, AbstractField.prototype.events, {
            'change .ks_toggle_icon_input': 'ks_toggle_icon_input_click',
        }),

        _render: function () {
            var self = this;
            self.$el.empty();
            var $view = $(QWeb.render('ks_widget_toggle_kpi'));

            if (self.value) {
                $view.find("input[value='" + self.value + "']").prop("checked", true);
            }
            this.$el.append($view)

            if (this.mode === 'readonly') {
                this.$el.find('.ks_select_dashboard_item_toggle').addClass('ks_not_click');
            }
        },
        ks_toggle_icon_input_click: function (e) {
            var self = this;
            self._setValue(e.currentTarget.value);
        }
    });

    var KsWidgetToggleKpiTarget = AbstractField.extend({
        supportedFieldTypes: ['char'],

        events: _.extend({}, AbstractField.prototype.events, {
            'change .ks_toggle_icon_input': 'ks_toggle_icon_input_click',
        }),

        _render: function () {
            var self = this;
            self.$el.empty();


            var $view = $(QWeb.render('ks_widget_toggle_kpi_target_view'));
            if (self.value) {
                $view.find("input[value='" + self.value + "']").prop("checked", true);
            }
            this.$el.append($view)

            if (this.mode === 'readonly') {
                this.$el.find('.ks_select_dashboard_item_toggle').addClass('ks_not_click');
            }
        },

        ks_toggle_icon_input_click: function (e) {
            var self = this;
            self._setValue(e.currentTarget.value);
        }
    });

    registry.add('ks_widget_toggle', KsWidgetToggle);
    registry.add('ks_widget_toggle_kpi', KsWidgetToggleKPI);
    registry.add('ks_widget_toggle_kpi_target', KsWidgetToggleKpiTarget);
    return {
        KsWidgetToggle: KsWidgetToggle,
        KsWidgetToggleKPI: KsWidgetToggleKPI,
        KsWidgetToggleKpiTarget :KsWidgetToggleKpiTarget
    };


