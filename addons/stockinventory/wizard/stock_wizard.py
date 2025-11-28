from odoo import models, fields
import io
from datetime import timedelta
import base64
import xlsxwriter

class StockAgeingWizard(models.TransientModel):
    _name = 'stock.wizard'
    _description = 'Stock Ageing Report Wizard'

    period_length = fields.Integer(string="Period Length (Days)", default=30, required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, required=True)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouse')
    date = fields.Date(string="Date", default=lambda self: fields.Date.today(), required=True)
    filter_by = fields.Selection([('product', 'Product'), ('category', 'Product Category')], default='product', required=True)
    location_ids = fields.Many2many('stock.location', string='Locations')
    product_ids = fields.Many2many('product.product', string='Products')
    category_ids = fields.Many2many('product.category', string='Categories')


    def action_print_excel(self):
        

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet("Stock Inventory Aging")

        bold = workbook.add_format({'bold': True})
        title_format = workbook.add_format({'bold': True, 'font_size': 14})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D9D9D9', 'align': 'center'})
        wrap_format = workbook.add_format({'text_wrap': True})

        worksheet.merge_range('C2:F2', 'Stock Inventory Aging', title_format)
        worksheet.write('B4', 'Date', bold)
        worksheet.write('C4', str(self.date))
        worksheet.write('E4', 'Period Length', bold)
        worksheet.write('F4', self.period_length)
        worksheet.write('B5', 'Company', bold)
        worksheet.write('C5', self.company_id.name)
        warehouse_names = ', '.join(self.warehouse_ids.mapped('name'))
        worksheet.write('B6', 'Warehouse', bold)
        worksheet.write('C6', warehouse_names)

        worksheet.merge_range(10, 0, 11, 0, 'Code', header_format)
        worksheet.merge_range(10, 1, 11, 1, 'Product', header_format)
        worksheet.merge_range(10, 2, 11, 2, 'Total Qty', header_format)
        worksheet.merge_range(10, 3, 11, 3, 'Total Value', header_format)

        ageing_ranges = ["0-30", "30-60", "60-90", "90-120", "120-150", "150-180", "+180"]
        start_col = 4
        for i, label in enumerate(ageing_ranges):
            col = start_col + i * 2
            worksheet.merge_range(10, col, 10, col + 1, label, header_format)
            worksheet.write(11, col, "Qty", header_format)
            worksheet.write(11, col + 1, "Value", header_format)

    
        aging_date = self.date
        buckets = [(0, 30), (30, 60), (60, 90), (90, 120), (120, 150), (150, 180), (180, 9999)]

        # import pdb;
        # pdb.set_trace()

        if self.filter_by == 'product':
            products = self.product_ids or self.env['product.product'].search([])
        else:
            products = self.env['product.product'].search([('categ_id', 'in', self.category_ids.ids)])

        locations = self.location_ids or self.env['stock.location'].search([('usage', 'in', ['internal', 'transit'])])

        stock_quants = self.env['stock.quant'].search([
            ('product_id', 'in', products.ids),
            ('location_id', 'in', locations.ids),
            ('quantity', '>', 0),
            ('in_date', '!=', False),
            ('company_id', '=', self.company_id.id),
        ])

        ageing_data = {}
        for quant in stock_quants:
            product = quant.product_id
            days_diff = (aging_date - quant.in_date.date()).days
            price = product.standard_price
            qty = quant.quantity
            value = qty * price

            if product not in ageing_data:
                ageing_data[product] = {
                    'total_qty': 0.0,
                    'total_value': 0.0,
                    'buckets': [(0.0, 0.0) for _ in buckets],
                }

            ageing_data[product]['total_qty'] += qty
            ageing_data[product]['total_value'] += value
            for i, (start, end) in enumerate(buckets):
                if start <= days_diff < end:
                    q, v = ageing_data[product]['buckets'][i]
                    ageing_data[product]['buckets'][i] = (q + qty, v + value)
                    break

        row = 12
        total_qty = 0.0
        total_value = 0.0
        total_buckets = [(0.0, 0.0) for _ in buckets]

        for product in products:
            if product not in ageing_data:
                continue
            data = ageing_data[product]
            col = 0
            worksheet.write(row, col, product.default_code or '')
            col += 1
            worksheet.write(row, col, product.name, wrap_format)
            col += 1
            worksheet.write(row, col, data['total_qty'])
            col += 1
            worksheet.write(row, col, data['total_value'])
            col += 1

            total_qty += data['total_qty']
            total_value += data['total_value']
            for i, (q, v) in enumerate(data['buckets']):
                worksheet.write(row, col, q)
                worksheet.write(row, col + 1, v)
                tq, tv = total_buckets[i]
                total_buckets[i] = (tq + q, tv + v)
                col += 2
            row += 1

      
        col = 0
        worksheet.write(row, col, 'TOTAL', bold)
        worksheet.write(row, col + 1, '', bold)
        worksheet.write(row, col + 2, total_qty, bold)
        worksheet.write(row, col + 3, total_value, bold)
        col += 4
        for q, v in total_buckets:
            worksheet.write(row, col, q, bold)
            worksheet.write(row, col + 1, v, bold)
            col += 2

     
        column_widths = [15, 30, 12, 15] + [10] * 14
        for i, width in enumerate(column_widths):
            worksheet.set_column(i, i, width)

        workbook.close()
        output.seek(0)
        file_data = base64.b64encode(output.read())
        attachment = self.env['ir.attachment'].create({
            'name': 'stock_ageing_report.xlsx',
            'type': 'binary',
            'datas': file_data,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = f'/web/content/{attachment.id}?download=true'
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'self',
        }




