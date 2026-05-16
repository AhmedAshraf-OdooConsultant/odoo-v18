/** @odoo-module **/
import { Component, useState, useRef, onMounted, onWillStart, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";


    

            
    
    //Widget for dashboard item theme using while creating dashboard item.
    var KsDashboardThemeold = AbstractField.extend({

        supportedFieldTypes: ['char'],

        events: _.extend({}, AbstractField.prototype.events, {
            'click .ks_dashboard_theme_input_container': 'ks_dashboard_theme_input_container_click',
        }),

        _render: function() {
            var self = this;
            self.$el.empty();
            var $view = $(QWeb.render('ks_dashboard_theme_view_old',{widget:this}));
            if (self.value) {
                $view.find("input[value='" + self.value + "']").prop("checked", true);
            }
            self.$el.append($view)

            if (this.mode === 'readonly') {
                this.$el.find('.ks_dashboard_theme_view_render').addClass('ks_not_click');
            }
        },

        ks_dashboard_theme_input_container_click: function(e) {
            var self = this;
            var $box = $(e.currentTarget).find(':input');
            if ($box.is(":checked")) {
                self.$el.find('.ks_dashboard_theme_input').prop('checked', false)
                $box.prop("checked", true);
            } else {
                $box.prop("checked", false);
            }
            self._setValue($box[0].value);
        },
    });

    registry.add('ks_dashboard_item_theme', KsDashboardThemeold);

    return {
        KsDashboardThemeold: KsDashboardThemeold
    };

