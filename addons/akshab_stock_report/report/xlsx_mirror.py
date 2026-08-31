# -*- coding: utf-8 -*-
"""Workbook layout engine shared by the four Excel exports.

Design goals (same identity as the PDF, but built for a spreadsheet):

* one sheet per section family — summary sheets keep the narrow tables, every product-level
  table gets its own sheet so its column widths can be optimal;
* two-row headers: related columns sit under one merged green group header
  (e.g. «0 – 30 يوم» over «الكمية» / «القيمة»), which is what keeps wide tables readable;
* every column is auto-sized from the widest value actually written in it;
* frozen header rows, auto-filter and repeat-rows on print for every product table;
* group (category) rows carry their figures in the matching columns instead of one long
  run-on sentence.
"""
import base64
import io
import logging

from .xlsx_base import AkshabXlsxBase, GREEN, GREEN_2, GOLD, BEIGE, BEIGE_2, RED, AMBER, BLUE, FONT

_logger = logging.getLogger(__name__)

ARABIC_DIGITS = str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')
BAR_COLORS = {'': GREEN, 'gold': GOLD, 'red': RED, 'amber': AMBER, 'blue': BLUE}

# how a value of each kind is rendered, for the column auto-width
_FMT = {
    'money': '{:,.2f}', 'moneyb': '{:,.2f}', 'moneyr': '{:,.2f}', 'moneyg': '{:,.2f}',
    'oldm': '{:,.2f}', 'qty': '{:,.2f}', 'qtyb': '{:,.2f}', 'qtyr': '{:,.2f}', 'old': '{:,.2f}',
    'int': '{:,.0f}', 'intr': '{:,.0f}', 'dec': '{:,.2f}', 'decb': '{:,.2f}', 'decr': '{:,.2f}',
    'pct': '{:,.1f}%', 'pctr': '{:,.1f}%',
}

def ar_num(n):
    return str(n).translate(ARABIC_DIGITS)


def col(label, kind='c', group=None):
    """One column spec: (label, kind, group)."""
    return (label, kind, group)


class MirrorXlsx(AkshabXlsxBase):
    """Subclasses implement ``build_report`` with the primitives below."""

    title_ar = ''
    title_en = ''
    MIN_W = 9.0
    MAX_W = 62.0

    # ------------------------------------------------------------------
    def build_sheets(self):
        self._mirror_formats()
        self._index = []
        self.ws_index = self.wb.add_worksheet('الفهرس')     # first tab: a cover + links
        self.ws_index.right_to_left()
        self.ws_index.hide_gridlines(2)
        self.ws_index.set_tab_color(GOLD)
        self.ws_index.set_landscape()
        self.ws_index.set_paper(9)
        self.ws_index.fit_to_pages(1, 1)
        self.ws_index.set_margins(left=0.3, right=0.3, top=0.5, bottom=0.5)
        self.ws_index.set_zoom(100)
        self.ws = None
        self.build_report()
        self._finish_sheet()
        self._write_index()

    def _write_index(self):
        ws, m = self.ws_index, self.m
        ws.set_column(0, 0, 34)
        ws.set_column(1, 1, 78)
        ws.set_row(0, 34)
        ws.merge_range(0, 0, 0, 1, self.title_ar, self.f_title_big)
        ws.merge_range(1, 0, 1, 1, '%s — %s' % (self.title_en, m['company_name']), self.f_title_en)
        r = 3
        for lbl, val in (('تاريخ المخزون', m['date_to_display']),
                         ('المستودعات', m['warehouses_display']),
                         ('الفئات', m['categories_display']),
                         ('تاريخ الطباعة', '%s · %s' % (m['print_date'], m['currency_name']))):
            ws.write(r, 0, lbl, self.f_meta_lbl)
            ws.write(r, 1, val, self.f_meta_val)
            r += 1
        r += 1
        ws.set_row(r, 22)
        ws.merge_range(r, 0, r, 1, '  محتويات الملف', self.f_sec_bar)
        r += 1
        ws.write(r, 0, 'الورقة', self.f_head_txt)
        ws.write(r, 1, 'المحتوى', self.f_head_txt)
        r += 1
        for i, (name, desc) in enumerate(self._index):
            ws.write_url(r, 0, "internal:'%s'!A1" % name, self.f_link if i % 2 == 0 else self.f_link_z, name)
            ws.write(r, 1, desc, self.f_txt if i % 2 == 0 else self.f_txt_z)
            r += 1
        ws.freeze_panes(3, 0)

    def build_report(self):
        raise NotImplementedError()

    # ------------------------------------------------------------------
    def _mirror_formats(self):
        f = self._fmt
        self.f_title_big = f(bold=True, font_size=20, font_color=GREEN, align='right', valign='vcenter')
        self.f_title_en = f(bold=True, font_size=9, font_color='#B8973F', align='right')
        self.f_sec_bar = f(bold=True, font_size=12, font_color='white', bg_color=GREEN, align='right', valign='vcenter', indent=1)
        self.f_sec_hint = f(font_size=9, font_color='#CFC7B0', bg_color=GREEN, align='left', valign='vcenter', indent=1)
        self.f_kpi_sub = f(bold=True, font_size=9, font_color='#A98A3E', bg_color=BEIGE, align='center')
        self.f_note_row = f(font_size=9, font_color='#6F6F6F', align='right', text_wrap=True, valign='top')
        self.f_legend = f(font_size=9, font_color='#555555', align='right', text_wrap=True, valign='top')
        self.f_list_head = f(bold=True, font_color='white', bg_color=GREEN, border=1, border_color=GREEN_2, align='right', indent=1)
        self.f_list_item = f(font_size=10, text_wrap=True, valign='top', border=1, border_color='#ECE7DB', align='right',
                             bg_color='#FBF9F4', indent=1)
        self.f_line = f(bottom=1, bottom_color='#B9B2A0', bg_color='#FBF9F4')
        self.f_method_k = f(bold=True, font_color=GREEN, align='right', valign='top', border=1, border_color='#ECE7DB', bg_color=BEIGE)
        self.f_method_v = f(font_size=10, font_color='#444444', align='right', valign='top', text_wrap=True, border=1, border_color='#ECE7DB')
        self.f_group = f(bold=True, font_color='white', bg_color='#2B5240', border=1, border_color=GREEN_2, align='center', text_wrap=True)
        self.f_group_old = f(bold=True, font_color='white', bg_color='#5A2F2F', border=1, border_color=GREEN_2, align='center', text_wrap=True)
        self.f_head_old = f(bold=True, font_color='white', bg_color='#5A2F2F', border=1, border_color=GREEN_2, align='center', text_wrap=True)
        # category (group) row inside a product table
        self.f_cat_txt = f(bold=True, font_size=11, font_color=GREEN, bg_color='#EFE3CB', top=2, top_color='#C4A46A',
                           bottom=1, bottom_color='#D8C79E', align='right', indent=1)
        self.f_cat_money = f(bold=True, font_color=GREEN, bg_color='#EFE3CB', top=2, top_color='#C4A46A',
                             bottom=1, bottom_color='#D8C79E', align='center', num_format='#,##0.00')
        self.f_cat_qty = f(bold=True, font_color=GREEN, bg_color='#EFE3CB', top=2, top_color='#C4A46A',
                           bottom=1, bottom_color='#D8C79E', align='center', num_format='#,##0.##')
        self.f_cat_int = f(bold=True, font_color=GREEN, bg_color='#EFE3CB', top=2, top_color='#C4A46A',
                           bottom=1, bottom_color='#D8C79E', align='center', num_format='#,##0')
        self.f_cat_pct = f(bold=True, font_color=GREEN, bg_color='#EFE3CB', top=2, top_color='#C4A46A',
                           bottom=1, bottom_color='#D8C79E', align='center', num_format='0.0%')
        self.f_cat_dec = f(bold=True, font_color=GREEN, bg_color='#EFE3CB', top=2, top_color='#C4A46A',
                           bottom=1, bottom_color='#D8C79E', align='center', num_format='0.00')
        self.f_cat_blank = f(bg_color='#EFE3CB', top=2, top_color='#C4A46A', bottom=1, bottom_color='#D8C79E')
        # extra data formats
        self.f_red_txt = f(border=1, border_color='#ECE7DB', align='right', bold=True, font_color=RED)
        self.f_red_txt_z = f(border=1, border_color='#ECE7DB', align='right', bold=True, font_color=RED, bg_color=BEIGE)
        self.f_pct_red = f(border=1, border_color='#ECE7DB', align='center', num_format='0.0%', bold=True, font_color=RED)
        self.f_pct_red_z = f(border=1, border_color='#ECE7DB', align='center', num_format='0.0%', bold=True, font_color=RED, bg_color=BEIGE)
        self.f_int_red = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0', bold=True, font_color=RED)
        self.f_int_red_z = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0', bold=True, font_color=RED, bg_color=BEIGE)
        self.f_qty_red = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.##', bold=True, font_color=RED)
        self.f_qty_red_z = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.##', bold=True, font_color=RED, bg_color=BEIGE)
        self.f_qty_b = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.##', bold=True)
        self.f_qty_b_z = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.##', bold=True, bg_color=BEIGE)
        self.f_dec_b = f(border=1, border_color='#ECE7DB', align='center', num_format='0.00', bold=True, font_color=GREEN)
        self.f_dec_b_z = f(border=1, border_color='#ECE7DB', align='center', num_format='0.00', bold=True, font_color=GREEN, bg_color=BEIGE)
        self.f_dec_r = f(border=1, border_color='#ECE7DB', align='center', num_format='0.00', bold=True, font_color=RED)
        self.f_dec_r_z = f(border=1, border_color='#ECE7DB', align='center', num_format='0.00', bold=True, font_color=RED, bg_color=BEIGE)
        self.f_old = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.##', bg_color='#FBF1F1')
        self.f_old_z = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.##', bg_color='#F6E9E9')
        self.f_old_money = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.00', bg_color='#FBF1F1')
        self.f_old_money_z = f(border=1, border_color='#ECE7DB', align='center', num_format='#,##0.00', bg_color='#F6E9E9')
        self.f_tot_dec = f(bold=True, font_color=GREEN, bg_color=BEIGE_2, top=2, top_color='#C9B27C', border=1,
                           border_color='#E5E0D3', align='center', num_format='0.00')
        self.f_tot_c = f(bold=True, font_color=GREEN, bg_color=BEIGE_2, top=2, top_color='#C9B27C', border=1,
                         border_color='#E5E0D3', align='center')
        self.f_link = f(border=1, border_color='#ECE7DB', align='right', bold=True, font_color=GREEN, underline=1, indent=1)
        self.f_link_z = f(border=1, border_color='#ECE7DB', align='right', bold=True, font_color=GREEN, underline=1,
                          bg_color=BEIGE, indent=1)
        self.f_name = f(border=1, border_color='#ECE7DB', align='right', bold=True, indent=1)
        self.f_name_z = f(border=1, border_color='#ECE7DB', align='right', bold=True, bg_color=BEIGE, indent=1)

    # ------------------------------------------------------------------
    # Sheets
    # ------------------------------------------------------------------
    def sheet(self, name, tab_color=GREEN, desc=''):
        """Close the previous sheet and start a new one (and list it in the index)."""
        self._finish_sheet()
        self._index.append((name[:31], desc))
        ws = self.wb.add_worksheet(name[:31])
        ws.right_to_left()
        ws.hide_gridlines(2)
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.set_margins(left=0.25, right=0.25, top=0.45, bottom=0.55)
        ws.set_footer('&C&"Tajawal"&9&P / &N')
        ws.set_tab_color(tab_color)
        ws.set_zoom(90)
        self.ws = ws
        self.r = 0
        self.width = {}          # col -> needed width
        self._freeze = None
        self._filter = None
        self._repeat = None
        self._span = 6           # widest table on this sheet (columns)
        self._logo_row = None
        return ws

    def _finish_sheet(self):
        if self.ws is None:
            return
        if getattr(self, '_logo_row', None) is not None:
            logo = getattr(self.w.company_id.sudo(), 'logo', None)
            try:
                raw = base64.b64decode(logo) if logo else b''
                if raw[:8] == b'\x89PNG\r\n\x1a\n' or raw[:3] == b'\xff\xd8\xff':
                    self.ws.insert_image(self._logo_row, max(5, self.span), 'logo.png', {
                        'image_data': io.BytesIO(raw), 'x_scale': 0.28, 'y_scale': 0.28, 'object_position': 3})
            except Exception:  # pragma: no cover - a logo must never break the export
                _logger.info('Akshab stock report: company logo could not be embedded in the workbook',
                             exc_info=True)
            self._logo_row = None
        for c, w in self.width.items():
            self.ws.set_column(c, c, max(self.MIN_W, min(self.MAX_W, w)))
        if self._freeze:
            self.ws.freeze_panes(*self._freeze)
        if self._filter:
            self.ws.autofilter(*self._filter)
        if self._repeat:
            self.ws.repeat_rows(*self._repeat)

    def _w(self, c, text, pad=3.0):
        """Track the width needed by ``text`` in column ``c``."""
        if text is None:
            return
        text = str(text)
        longest = max((len(part) for part in text.split('\n')), default=0)
        need = longest * 1.08 + pad
        if need > self.width.get(c, 0):
            self.width[c] = need
        if c + 1 > self._span:
            self._span = c + 1

    def _text_of(self, val, kind):
        if val is None:
            return '-'
        fmt = _FMT.get(kind)
        if fmt and isinstance(val, (int, float)):
            return fmt.format(val)
        return str(val)

    @property
    def span(self):
        """Last column index used by the widest table on this sheet."""
        return max(5, self._span - 1)

    # ------------------------------------------------------------------
    # Page frame
    # ------------------------------------------------------------------
    def header(self, subtitle=None):
        ws = self.ws
        ws.set_row(self.r, 30)
        ws.merge_range(self.r, 0, self.r, max(5, self.span), self.title_ar, self.f_title_big)
        ws.merge_range(self.r + 1, 0, self.r + 1, max(5, self.span), subtitle or self.title_en, self.f_title_en)
        self._logo_row = self.r
        self.r += 3

    def kpis(self, tiles, per_tile=2):
        """tiles = [(value, label, kind, sub)] rendered as merged cards, two columns each."""
        ws = self.ws
        for i, (val, label, kind, sub) in enumerate(tiles):
            c0 = i * per_tile
            c1 = c0 + per_tile - 1
            base = {'font_name': FONT, 'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter',
                    'font_color': RED if kind == 'money_red' else GREEN, 'bg_color': BEIGE, 'top': 3, 'top_color': GOLD}
            base['num_format'] = {'money': '#,##0.00', 'money_red': '#,##0.00', 'dec': '0.00', 'qty': '#,##0.##'}.get(kind, '#,##0')
            fmt = self.wb.add_format(base)
            ws.merge_range(self.r, c0, self.r, c1, float(val or 0.0), fmt)
            ws.merge_range(self.r + 1, c0, self.r + 1, c1, sub or '', self.f_kpi_sub)
            ws.merge_range(self.r + 2, c0, self.r + 2, c1, label, self.f_kpi_lbl)
            for c in range(c0, c1 + 1):
                self._w(c, '', pad=0)
            self._w(c1, label[: max(1, len(label) // per_tile)], pad=2)
        ws.set_row(self.r, 24)
        ws.set_row(self.r + 2, 26)
        self.r += 4

    def info(self, rows):
        """rows = [(label, value)] or [(label, value, label2, value2)] — a label/value band."""
        ws = self.ws
        span = max(7, self.span)
        half = (span + 1) // 2
        for row in rows:
            ws.set_row(self.r, 19)
            if len(row) == 2:
                ws.merge_range(self.r, 0, self.r, 1, row[0], self.f_meta_lbl)
                ws.merge_range(self.r, 2, self.r, span, row[1], self.f_meta_val)
            else:
                ws.merge_range(self.r, 0, self.r, 1, row[0], self.f_meta_lbl)
                ws.merge_range(self.r, 2, self.r, half, row[1], self.f_meta_val)
                ws.merge_range(self.r, half + 1, self.r, half + 2, row[2], self.f_meta_lbl)
                ws.merge_range(self.r, half + 3, self.r, span, row[3], self.f_meta_val)
            self.r += 1
        self.r += 1

    def section(self, title, hint='', cols=None):
        """Numbered green section bar, sized to the table that follows."""
        self.sec = getattr(self, 'sec', 0) + 1
        ws = self.ws
        last = max(5, (cols - 1) if cols else self.span)
        self._w(last, '', pad=0)
        ws.set_row(self.r, 22)
        mid = min(last, max(2, last // 2))
        ws.merge_range(self.r, 0, self.r, mid, '%s  %s' % (ar_num(self.sec), title), self.f_sec_bar)
        if mid < last:
            ws.merge_range(self.r, mid + 1, self.r, last, hint or '', self.f_sec_hint)
        self.r += 1

    def note(self, text, fmt=None, cols=None):
        ws = self.ws
        last = max(5, (cols - 1) if cols else self.span)
        ws.set_row(self.r, 16 if len(text) < 150 else 30)
        ws.merge_range(self.r, 0, self.r, last, text, fmt or self.f_note_row)
        self.r += 1

    def gap(self, n=1):
        self.r += n

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------
    def head(self, specs, freeze=True, autofilter=False):
        """specs = [(label, kind)] or [(label, kind, group)].

        When any column carries a group, a merged group row is written above the labels
        (this is what makes wide tables readable: «0 – 30 يوم» over «الكمية» / «القيمة»)."""
        ws = self.ws
        specs = [(s + (None,))[:3] if len(s) == 2 else s for s in specs]
        self.specs = specs
        n = len(specs)
        groups = [s[2] for s in specs]
        has_groups = any(groups)
        if has_groups:
            ws.set_row(self.r, 20)
            i = 0
            while i < n:
                g = groups[i]
                j = i
                while j + 1 < n and groups[j + 1] == g and g is not None:
                    j += 1
                fmt = self.f_group_old if (g and 'أكثر من' in str(g)) else self.f_group
                if g:
                    if j > i:
                        ws.merge_range(self.r, i, self.r, j, g, fmt)
                    else:
                        ws.write(self.r, i, g, fmt)
                else:
                    # a column without a group: its label spans both header rows
                    ws.merge_range(self.r, i, self.r + 1, i, specs[i][0],
                                   self.f_head_txt if specs[i][1] == 'txt' else self.f_head)
                    self._w(i, specs[i][0], pad=4)
                i = j + 1
            self.r += 1
        ws.set_row(self.r, 30)
        for i, (label, kind, g) in enumerate(specs):
            if has_groups and not g:
                continue          # already merged across the two header rows
            fmt = self.f_head_txt if kind == 'txt' else (self.f_head_old if kind == 'old' else self.f_head)
            ws.write(self.r, i, label, fmt)
            self._w(i, label if len(label) < 16 else label[:16], pad=4)
        self.r += 1
        self._head_last = self.r - 1
        if freeze:
            self._freeze = (self.r, 1)
            self._repeat = (self.r - (2 if has_groups else 1), self.r - 1)
        self._data_first = self.r
        self._want_filter = autofilter
        return n

    def _fmt_for(self, kind, zebra):
        extra = {
            'name': (self.f_name, self.f_name_z),
            'txtr': (self.f_red_txt, self.f_red_txt_z),
            'pctr': (self.f_pct_red, self.f_pct_red_z),
            'intr': (self.f_int_red, self.f_int_red_z),
            'qtyr': (self.f_qty_red, self.f_qty_red_z),
            'qtyb': (self.f_qty_b, self.f_qty_b_z),
            'decb': (self.f_dec_b, self.f_dec_b_z),
            'decr': (self.f_dec_r, self.f_dec_r_z),
            'old': (self.f_old, self.f_old_z),
            'oldm': (self.f_old_money, self.f_old_money_z),
        }
        if kind in extra:
            return extra[kind][1] if zebra else extra[kind][0]
        return self._cell_formats(kind, zebra)

    def row(self, values, zebra=False):
        """values = [(value, kind)]; 'bar:<class>' draws a data bar, 'badge:<key>' a status chip."""
        ws = self.ws
        for i, (val, kind) in enumerate(values):
            if kind.startswith('badge:'):
                key = kind.split(':', 1)[1]
                ws.write(self.r, i, val, self.f_badge.get(key, self.f_c))
                self._w(i, val)
            elif kind.startswith('bar:'):
                cls = kind.split(':', 1)[1]
                ws.write_number(self.r, i, float(val or 0.0) / 100.0, self._fmt_for('pct', zebra))
                ws.conditional_format(self.r, i, self.r, i, {
                    'type': 'data_bar', 'bar_color': BAR_COLORS.get(cls, GREEN), 'bar_solid': True,
                    'min_type': 'num', 'min_value': 0, 'max_type': 'num', 'max_value': 1})
                self._w(i, '100.0%')
            else:
                fmt = self._fmt_for(kind, zebra)
                if val is None:
                    ws.write(self.r, i, '-', self._fmt_for('c', zebra))
                    self._w(i, '-')
                elif kind in ('pct', 'pctr'):
                    ws.write_number(self.r, i, float(val) / 100.0, fmt)
                    self._w(i, self._text_of(val, kind))
                elif kind in _FMT:
                    ws.write_number(self.r, i, float(val), fmt)
                    self._w(i, self._text_of(val, kind))
                else:
                    ws.write(self.r, i, val, fmt)
                    self._w(i, val)
        self.r += 1

    def rows(self, all_rows):
        for i, vals in enumerate(all_rows):
            self.row(vals, i % 2 == 1)

    def cat_row(self, label, values):
        """Category / group row: the name on the left, its figures in their own columns."""
        ws = self.ws
        ws.set_row(self.r, 20)
        ws.write(self.r, 0, label, self.f_cat_txt)
        self._w(0, label)
        fmts = {'money': self.f_cat_money, 'qty': self.f_cat_qty, 'int': self.f_cat_int,
                'pct': self.f_cat_pct, 'dec': self.f_cat_dec}
        n = len(getattr(self, 'specs', values)) or len(values)
        for i in range(1, n):
            val, kind = values[i - 1] if i - 1 < len(values) else ('', 'blank')
            fmt = fmts.get(kind)
            if fmt is None or val is None or val == '':
                ws.write(self.r, i, '', self.f_cat_blank)
            elif kind == 'pct':
                ws.write_number(self.r, i, float(val) / 100.0, fmt)
                self._w(i, self._text_of(val, kind))
            else:
                ws.write_number(self.r, i, float(val), fmt)
                self._w(i, self._text_of(val, kind))
        self.r += 1

    def total(self, values, label_cols=1):
        """Totals row; ``values`` starts at column ``label_cols`` when it is > 1."""
        ws = self.ws
        fmts = {'money': self.f_tot_money, 'qty': self.f_tot_qty, 'int': self.f_tot_int,
                'pct': self.f_tot_pct, 'dec': self.f_tot_dec, 'c': self.f_tot_c}
        if label_cols > 1:
            ws.merge_range(self.r, 0, self.r, label_cols - 1, values[0][0], self.f_tot_txt)
            rest = values[1:]
            start = label_cols
        else:
            ws.write(self.r, 0, values[0][0], self.f_tot_txt)
            self._w(0, values[0][0])
            rest = values[1:]
            start = 1
        for j, (val, kind) in enumerate(rest):
            i = start + j
            fmt = fmts.get(kind)
            if fmt is None or val is None or val == '':
                ws.write(self.r, i, '', self.f_tot_blank)
            elif kind == 'c':
                ws.write(self.r, i, val, fmt)
                self._w(i, val)
            elif kind == 'pct':
                ws.write_number(self.r, i, float(val) / 100.0, fmt)
                self._w(i, self._text_of(val, kind))
            else:
                ws.write_number(self.r, i, float(val), fmt)
                self._w(i, self._text_of(val, kind))
        self.r += 1

    def end_table(self):
        """Close a table: enable its auto-filter when it was asked for."""
        if getattr(self, '_want_filter', False) and self.r > self._data_first:
            self._filter = (self._head_last, 0, self.r - 1, len(self.specs) - 1)
            self._want_filter = False
        self.gap()

    # ------------------------------------------------------------------
    # Blocks
    # ------------------------------------------------------------------
    def list_block(self, title, items):
        ws = self.ws
        last = max(5, self.span)
        ws.merge_range(self.r, 0, self.r, last, title, self.f_list_head)
        self.r += 1
        for i, text in enumerate(items):
            ws.set_row(self.r, 28 if len(text) > 110 else 18)
            ws.merge_range(self.r, 0, self.r, last, '%s. %s' % (ar_num(i + 1), text), self.f_list_item)
            self.r += 1
        self.r += 1

    def lines_block(self, title, n=4):
        ws = self.ws
        last = max(5, self.span)
        ws.merge_range(self.r, 0, self.r, last, title, self.f_list_head)
        self.r += 1
        for _ in range(n):
            ws.set_row(self.r, 20)
            ws.merge_range(self.r, 0, self.r, last, '', self.f_line)
            self.r += 1
        self.r += 1

    def method(self, rows):
        """Methodology sheet: [(key, text)]."""
        self.sheet('المنهجية', tab_color='#8A8A8A', desc='كيف حُسبت أرقام هذا التقرير — التعريفات والمعادلات')
        ws = self.ws
        ws.set_row(0, 26)
        ws.merge_range(0, 0, 0, 6, 'منهجية الاحتساب', self.f_title_big)
        ws.merge_range(1, 0, 1, 6, 'كيف حُسبت الأرقام في هذا التقرير', self.f_title_en)
        ws.set_column(0, 0, 26)
        ws.set_column(1, 6, 22)
        r = 3
        for key, text in rows:
            ws.set_row(r, max(30, min(120, 16 * (len(text) // 95 + 1))))
            ws.write(r, 0, key, self.f_method_k)
            ws.merge_range(r, 1, r, 6, text, self.f_method_v)
            r += 1
        self.width = {}          # widths were set explicitly above
        self._freeze = self._filter = self._repeat = None

    # ------------------------------------------------------------------
    # Shared column sets
    # ------------------------------------------------------------------
    def period_text(self, date_from, date_to, days):
        return 'من %s إلى %s \u200f(%s يوم)\u200f' % (date_from, date_to, days)

    def product_specs(self, with_category=False):
        """Name [+ warehouses] [+ category] + the standard quantity / cost / sale block."""
        cur = self.cur
        out = [col('الصنف', 'txt')]
        if self.m['multi_warehouse']:
            out.append(col('توزيع المستودعات', 'txt'))
        if with_category:
            out.append(col('الفئة', 'txt'))
        out += [
            col('الكمية', 'c', 'الرصيد الحالي'), col('الوحدة', 'c', 'الرصيد الحالي'),
            col('تكلفة الوحدة', 'c', 'التكلفة (%s)' % cur), col('القيمة بالتكلفة', 'c', 'التكلفة (%s)' % cur),
            col('سعر البيع', 'c', 'البيع (%s)' % cur), col('القيمة البيعية', 'c', 'البيع (%s)' % cur),
        ]
        return out

    def product_cells(self, rw, with_category=False):
        cells = [(rw['display_name'], 'name')]
        if self.m['multi_warehouse']:
            cells.append((rw['wh_text'] or '', 'txt'))
        if with_category:
            cells.append((rw['category'], 'txt'))
        cells += [(rw['qty'], 'qtyb'), (rw['uom'], 'c'), (rw['unit_cost'], 'money'), (rw['value'], 'moneyb'),
                  (rw['price'], 'money'), (rw['sale_value'], 'money')]
        return cells

    def product_label_cols(self, with_category=False):
        return 1 + (1 if self.m['multi_warehouse'] else 0) + (1 if with_category else 0)

    def product_totals(self, qty, value, sale_value, with_category=False):
        pad = [('', 'blank')] * (self.product_label_cols(with_category) - 1)
        return pad + [(qty, 'qty'), ('', 'blank'), ('', 'blank'), (value, 'money'), ('', 'blank'), (sale_value, 'money')]

    def bucket_specs(self, with_value=True):
        out = []
        for lbl in self.m['bucket_labels']:
            if with_value:
                out += [col('الكمية', 'c', lbl), col('القيمة', 'c', lbl)]
            else:
                out.append(col('القيمة', 'c', lbl))
        return out

    def bucket_cells(self, qtys, values=None):
        n = self.m['n_buckets']
        out = []
        for i, q in enumerate(qtys):
            last = i == n - 1
            out.append((q, 'old' if last else 'qty'))
            if values is not None:
                out.append((values[i], 'oldm' if last else 'money'))
        return out

    def bucket_totals(self, qtys, values=None):
        out = []
        for i, q in enumerate(qtys):
            out.append((q, 'qty'))
            if values is not None:
                out.append((values[i], 'money'))
        return out

    def transfers_table(self):
        d, k, cur = self.d, self.k, self.cur
        specs = [col('الصنف', 'txt'), col('الفئة', 'txt'),
                 col('المستودع', 'c', 'من'), col('الكمية فيه', 'c', 'من'), col('أيام بلا بيع', 'c', 'من'),
                 col('المستودع', 'c', 'إلى'), col('الكمية هناك', 'c', 'إلى'), col('متوسط البيع اليومي', 'c', 'إلى'),
                 col('التغطية (يوم)', 'c', 'إلى'),
                 col('الكمية', 'c', 'النقل المقترح'), col('قيمتها بالتكلفة (%s)' % cur, 'c', 'النقل المقترح')]
        self.head(specs, autofilter=True)
        for i, t in enumerate(d['transfers']):
            self.row([(t['product'], 'name'), (t['category'], 'txt'), (t['from_name'], 'txt'), (t['from_qty'], 'qty'),
                      (t['from_days_no_sale'], 'intr'), (t['to_name'], 'txt'), (t['to_qty'], 'qty'),
                      (t['to_avg_daily'], 'dec'), (t['to_cover'], 'int'), (t['qty'], 'qtyb'), (t['value'], 'moneyb')], i % 2 == 1)
        self.total([('الإجمالي: %s' % d['totals']['transfer_items'], 'txt')] + [('', 'blank')] * 8 +
                   [(d['totals']['transfer_qty'], 'qty'), (k['transfer_value'], 'money')], label_cols=2)
        self.end_table()

    def method_common(self):
        m = self.m
        return [
            ('الكميات', 'كميات المخزون في المواقع الداخلية للمستودعات/المواقع المحددة حتى تاريخ التقرير (%s). المبيعات المسجلة دون رصيد كافٍ لا تدخل في الكميات ولا في القيمة، والاستلام اللاحق يغطيها أولاً ولا يُحتسب منه إلا ما تبقى. الأصناف المؤرشفة لا تظهر في التقرير (الأصناف النشطة فقط).' % m['mode_label']),
            ('التقييم', '%s × الكمية. أسعار البيع في التقرير بدون ضريبة القيمة المضافة (تُستبعد تلقائياً إذا كان السعر شاملاً لها).' % m['cost_basis_label']),
            ('المرتجعات', 'المرتجع المرتبط بحركته الأصلية يُعالج على الحركة الأصلية وبتاريخها: مرتجع المشتريات يخفض كمية الاستلام الأصلي نفسه، ومرتجع العميل أو المستودع يعيد الكمية بعمرها الأصلي ولا يُعد استلاماً جديداً ويُخصم من مبيعات تاريخ البيع الأصلي (بما في ذلك مرتجعات نقاط البيع المرتبطة بطلبها الأصلي). المرتجع للمورد غير المرتبط بحركة يخفض آخر الاستلامات السابقة له.'),
        ]
