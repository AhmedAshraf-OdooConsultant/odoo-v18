# -*- coding: utf-8 -*-
"""Shared xlsxwriter helpers (Akshab identity: RTL, dark green / gold) for all report workbooks."""
import io

try:
    import xlsxwriter
except ImportError:  # pragma: no cover
    from odoo.tools.misc import xlsxwriter  # noqa: F401

GREEN = '#1F3D2F'
GREEN_2 = '#2B5240'
GOLD = '#B99A5B'
GOLD_LIGHT = '#C4A46A'
BEIGE = '#F7F4EE'
BEIGE_2 = '#EFE9DC'
BEIGE_3 = '#EDE6D6'
RED = '#A94442'
AMBER = '#C08A2E'
BLUE = '#4A6FA5'
GREY = '#6C757D'
FONT = 'Tajawal'

STATUS_COLORS = {'active': '#2E7D4F', 'slow': AMBER, 'stagnant': RED, 'new': BLUE, 'out': GREY}
ACTION_COLORS = {
    'liquidate': '#8E2F2F', 'discount_high': RED, 'discount': AMBER, 'stop_buy': '#B8862B',
    'transfer': BLUE, 'reorder': '#2E7D4F', 'reorder_urgent': GREEN, 'watch': GREY, 'keep': '#7B8F84',
}


class AkshabXlsxBase:
    """Common formats and writers; subclasses implement ``build_sheets``."""

    subtitle = 'INVENTORY REPORT'

    def __init__(self, wizard, data):
        self.w = wizard
        self.d = data
        self.m = data['meta']
        self.k = data['kpi']
        self.cur = data['meta']['currency']

    def build(self):
        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        self.wb = wb
        self._formats()
        self.build_sheets()
        wb.close()
        return output.getvalue()

    def build_sheets(self):
        raise NotImplementedError()

    # ------------------------------------------------------------------
    def _fmt(self, **kw):
        base = {'font_name': FONT, 'font_size': 10, 'valign': 'vcenter'}
        base.update(kw)
        return self.wb.add_format(base)

    def _formats(self):
        f = self._fmt
        self.f_title = f(bold=True, font_size=18, font_color=GREEN)
        self.f_subtitle = f(bold=True, font_size=10, font_color='#B8973F')
        self.f_meta_lbl = f(bold=True, font_color=GREEN, bg_color=BEIGE_3, border=1, border_color='#E5E0D3', align='right')
        self.f_meta_val = f(border=1, border_color='#E5E0D3', align='right')
        self.f_kpi_val = f(bold=True, font_size=14, font_color=GREEN, bg_color=BEIGE, top=2, top_color=GOLD, align='center')
        self.f_kpi_val_red = f(bold=True, font_size=14, font_color=RED, bg_color=BEIGE, top=2, top_color=GOLD, align='center')
        self.f_kpi_lbl = f(font_size=9, font_color='#6F6F6F', bg_color=BEIGE, align='center', bottom=1, bottom_color='#E5E0D3')
        self.f_section = f(bold=True, font_size=12, font_color='white', bg_color=GREEN)
        self.f_section_idx = f(bold=True, font_size=12, font_color='#D9B96B', bg_color=GREEN_2, align='center')
        self.f_hint = f(font_size=9, font_color='#6F6F6F', italic=True)
        self.f_head = f(bold=True, font_color='white', bg_color=GREEN, border=1, border_color=GREEN_2, align='center', text_wrap=True)
        self.f_head_txt = f(bold=True, font_color='white', bg_color=GREEN, border=1, border_color=GREEN_2, align='right', text_wrap=True)
        self.f_txt = f(border=1, border_color='#ECE7DB', align='right', text_wrap=True)
        self.f_txt_z = f(border=1, border_color='#ECE7DB', align='right', bg_color=BEIGE, text_wrap=True)
        self.f_txt_b = f(border=1, border_color='#ECE7DB', align='right', bold=True, text_wrap=True)
        self.f_txt_b_z = f(border=1, border_color='#ECE7DB', align='right', bold=True, bg_color=BEIGE, text_wrap=True)
        self.f_c = f(border=1, border_color='#ECE7DB', align='center')
        self.f_c_z = f(border=1, border_color='#ECE7DB', align='center', bg_color=BEIGE)
        self.f_money = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.00')
        self.f_money_z = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.00', bg_color=BEIGE)
        self.f_money_b = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.00', bold=True)
        self.f_money_b_z = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.00', bold=True, bg_color=BEIGE)
        self.f_money_red = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.00', bold=True, font_color=RED)
        self.f_money_red_z = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.00', bold=True, font_color=RED, bg_color=BEIGE)
        self.f_money_green = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.00', bold=True, font_color=GREEN)
        self.f_money_green_z = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.00', bold=True, font_color=GREEN, bg_color=BEIGE)
        self.f_qty = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.##')
        self.f_qty_z = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.##', bg_color=BEIGE)
        self.f_int = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0')
        self.f_int_z = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0', bg_color=BEIGE)
        self.f_pct = f(border=1, border_color='#ECE7DB', align='center', num_format='0.0%')
        self.f_pct_z = f(border=1, border_color='#ECE7DB', align='center', num_format='0.0%', bg_color=BEIGE)
        self.f_dec = f(border=1, border_color='#ECE7DB', align='center', num_format='0.00')
        self.f_dec_z = f(border=1, border_color='#ECE7DB', align='center', num_format='0.00', bg_color=BEIGE)
        self.f_tot_txt = f(bold=True, font_color=GREEN, bg_color=BEIGE_2, top=2, top_color='#C9B27C', border=1, border_color='#E5E0D3', align='right')
        self.f_tot_money = f(bold=True, font_color=GREEN, bg_color=BEIGE_2, top=2, top_color='#C9B27C', border=1, border_color='#E5E0D3', align='center', num_format='#,##0.00')
        self.f_tot_qty = f(bold=True, font_color=GREEN, bg_color=BEIGE_2, top=2, top_color='#C9B27C', border=1, border_color='#E5E0D3', align='center', num_format='#,##0.##')
        self.f_tot_int = f(bold=True, font_color=GREEN, bg_color=BEIGE_2, top=2, top_color='#C9B27C', border=1, border_color='#E5E0D3', align='center', num_format='#,##0')
        self.f_tot_pct = f(bold=True, font_color=GREEN, bg_color=BEIGE_2, top=2, top_color='#C9B27C', border=1, border_color='#E5E0D3', align='center', num_format='0.0%')
        self.f_tot_blank = f(bg_color=BEIGE_2, top=2, top_color='#C9B27C', border=1, border_color='#E5E0D3')
        self.f_sub = f(bold=True, font_color=GREEN, bg_color=GOLD_LIGHT, border=1, border_color='#E5E0D3', align='right')
        self.f_note = f(font_size=9, font_color='#555555', text_wrap=True, valign='top')
        self.f_insight = f(font_size=10, text_wrap=True, valign='top', border=1, border_color='#ECE7DB', align='right')
        self.f_badge = {}
        for key, color in list(STATUS_COLORS.items()) + list(ACTION_COLORS.items()):
            self.f_badge[key] = f(bold=True, font_color='white', bg_color=color, align='center', border=1, border_color='#ECE7DB')

    # ------------------------------------------------------------------
    def _new_sheet(self, name, widths):
        ws = self.wb.add_worksheet(name[:31])
        ws.right_to_left()
        ws.hide_gridlines(2)
        ws.set_landscape()
        ws.set_paper(9)  # A4
        ws.fit_to_pages(1, 0)
        ws.set_margins(left=0.3, right=0.3, top=0.5, bottom=0.5)
        for i, wdt in enumerate(widths):
            ws.set_column(i, i, wdt)
        return ws

    def _section(self, ws, row, idx, title, hint=None, span=8):
        ws.set_row(row, 22)
        ws.write(row, 0, idx, self.f_section_idx)
        ws.merge_range(row, 1, row, span, title, self.f_section)
        if hint:
            ws.write(row + 1, 0, hint, self.f_hint)
            return row + 2
        return row + 1

    def _title_block(self, ws, title, meta_rows, span=8):
        """Title + subtitle + a label/value/label/value info block. ``meta_rows`` = [(a, b, c, d), ...]."""
        ws.set_row(0, 30)
        ws.merge_range(0, 0, 0, span, title, self.f_title)
        ws.merge_range(1, 0, 1, span, '%s — %s' % (self.subtitle, self.m['company_name']), self.f_subtitle)
        r = 3
        for a, b, c, dd in meta_rows:
            ws.write(r, 0, a, self.f_meta_lbl)
            ws.merge_range(r, 1, r, 3, b, self.f_meta_val)
            ws.write(r, 4, c, self.f_meta_lbl)
            ws.merge_range(r, 5, r, span, dd, self.f_meta_val)
            r += 1
        return r + 1

    def _kpi_row(self, ws, row, kpis):
        """kpis = [(value, label, kind)] with kind in money / money_red / int / dec / pct."""
        ws.set_row(row, 24)
        for i, (val, label, kind) in enumerate(kpis):
            base = {'font_name': FONT, 'bold': True, 'font_size': 14,
                    'font_color': RED if kind == 'money_red' else GREEN,
                    'bg_color': BEIGE, 'top': 2, 'top_color': GOLD, 'align': 'center'}
            if kind in ('money', 'money_red'):
                base['num_format'] = '#,##0.00'
            elif kind == 'dec':
                base['num_format'] = '0.00'
            elif kind == 'pct':
                base['num_format'] = '0.0%'
                val = (val or 0.0) / 100.0
            else:
                base['num_format'] = '#,##0'
            fmt = self.wb.add_format(base)
            if val is None:
                ws.write(row, i, '-', fmt)
            else:
                ws.write_number(row, i, float(val), fmt)
            ws.write(row + 1, i, label, self.f_kpi_lbl)
        return row + 3

    def _method_sheet(self, lines):
        ws = self._new_sheet('المنهجية', [22, 120])
        ws.set_row(0, 26)
        ws.merge_range(0, 0, 0, 1, 'منهجية الاحتساب', self.f_title)
        r = 2
        for kk, v in lines:
            ws.set_row(r, 45)
            ws.write(r, 0, kk, self.f_meta_lbl)
            ws.write(r, 1, v, self.f_insight)
            r += 1
        return ws

    def _write_header(self, ws, row, headers):
        ws.set_row(row, 30)
        for i, (label, kind) in enumerate(headers):
            ws.write(row, i, label, self.f_head_txt if kind == 'txt' else self.f_head)
        return row + 1

    def _cell_formats(self, kind, zebra):
        table = {
            'txt': (self.f_txt, self.f_txt_z),
            'txtb': (self.f_txt_b, self.f_txt_b_z),
            'c': (self.f_c, self.f_c_z),
            'money': (self.f_money, self.f_money_z),
            'moneyb': (self.f_money_b, self.f_money_b_z),
            'moneyr': (self.f_money_red, self.f_money_red_z),
            'moneyg': (self.f_money_green, self.f_money_green_z),
            'qty': (self.f_qty, self.f_qty_z),
            'int': (self.f_int, self.f_int_z),
            'pct': (self.f_pct, self.f_pct_z),
            'dec': (self.f_dec, self.f_dec_z),
        }
        pair = table.get(kind, table['txt'])
        return pair[1] if zebra else pair[0]

    def _write_row(self, ws, row, values, zebra):
        """values: list of (value, kind); kind 'badge:<key>' writes a coloured status cell."""
        for i, (val, kind) in enumerate(values):
            if kind.startswith('badge:'):
                key = kind.split(':', 1)[1]
                ws.write(row, i, val, self.f_badge.get(key, self.f_c))
                continue
            fmt = self._cell_formats(kind, zebra)
            if val is None:
                ws.write(row, i, '-', self.f_c_z if zebra else self.f_c)
            elif kind == 'pct':
                ws.write_number(row, i, float(val) / 100.0, fmt)
            elif kind in ('money', 'moneyb', 'moneyr', 'moneyg', 'qty', 'int', 'dec'):
                ws.write_number(row, i, float(val), fmt)
            else:
                ws.write(row, i, val, fmt)

    def _write_total(self, ws, row, values):
        for i, (val, kind) in enumerate(values):
            if kind == 'txt':
                ws.write(row, i, val, self.f_tot_txt)
            elif kind == 'money':
                ws.write_number(row, i, float(val), self.f_tot_money)
            elif kind == 'qty':
                ws.write_number(row, i, float(val), self.f_tot_qty)
            elif kind == 'int':
                ws.write_number(row, i, float(val), self.f_tot_int)
            elif kind == 'pct':
                ws.write_number(row, i, float(val) / 100.0, self.f_tot_pct)
            else:
                ws.write(row, i, val if val is not None else '', self.f_tot_blank)

    # ------------------------------------------------------------------
    # Standard product columns (all product sheets): quantity, UoM, unit cost, cost value,
    # sale price, sale value — in this order
    # ------------------------------------------------------------------
    def _std_headers(self):
        cur = self.cur
        return [('الكمية', 'c'), ('الوحدة', 'c'), ('تكلفة الوحدة (%s)' % cur, 'c'), ('القيمة بالتكلفة (%s)' % cur, 'c'),
                ('سعر البيع (%s)' % cur, 'c'), ('القيمة البيعية (%s)' % cur, 'c')]

    def _std_values(self, rw):
        return [(rw['qty'], 'qty'), (rw['uom'], 'c'), (rw['unit_cost'], 'money'), (rw['value'], 'moneyb'),
                (rw['price'], 'money'), (rw['sale_value'], 'money')]

    def _std_totals(self, qty, value, sale_value):
        return [(qty, 'qty'), ('', 'blank'), ('', 'blank'), (value, 'money'), ('', 'blank'), (sale_value, 'money')]

    # ------------------------------------------------------------------
    def _sheet_transfers(self):
        cur = self.cur
        headers = [('الصنف', 'txt'), ('الفئة', 'txt'), ('من مستودع', 'txt'), ('الكمية فيه', 'c'), ('أيام بلا بيع فيه', 'c'),
                   ('إلى مستودع', 'txt'), ('الكمية هناك', 'c'), ('متوسط البيع اليومي هناك', 'c'), ('تغطيته هناك (يوم)', 'c'),
                   ('الكمية المقترح نقلها', 'c'), ('قيمتها بالتكلفة (%s)' % cur, 'c')]
        ws = self._new_sheet('إعادة التوزيع', [38, 22, 20, 12, 14, 20, 12, 16, 14, 16, 18])
        ws.set_row(0, 26)
        ws.merge_range(0, 0, 0, 8, 'إعادة التوزيع بين المستودعات', self.f_title)
        ws.merge_range(1, 0, 1, 8, 'مخزون بلا حركة في مستودع بينما يُباع في مستودع آخر — النقل بديل عن التخفيض', self.f_hint)
        r = self._write_header(ws, 3, headers)
        first = r
        for i, t in enumerate(self.d['transfers']):
            self._write_row(ws, r, [(t['product'], 'txtb'), (t['category'], 'txt'), (t['from_name'], 'txtb'), (t['from_qty'], 'qty'),
                                    (t['from_days_no_sale'], 'int'), (t['to_name'], 'txtb'), (t['to_qty'], 'qty'),
                                    (t['to_avg_daily'], 'dec'), (t['to_cover'], 'int'), (t['qty'], 'qty'), (t['value'], 'moneyb')], i % 2 == 1)
            r += 1
        ws.autofilter(first - 1, 0, r - 1, len(headers) - 1)
        self._write_total(ws, r, [('الإجمالي: %d اقتراح' % len(self.d['transfers']), 'txt')] + [('', 'blank')] * 8 +
                          [(self.d['totals']['transfer_qty'], 'qty'), (self.d['totals']['transfer_value'], 'money')])
        ws.freeze_panes(first, 1)
