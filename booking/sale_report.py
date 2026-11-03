"""Sale report downloads, using recorded return dates in India time."""
from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED
from zoneinfo import ZoneInfo

from django.http import HttpResponse
from rest_framework import serializers
from .views import BookingListAPIView
from .models import Booking

INDIA = ZoneInfo('Asia/Kolkata')
HEADERS = ['Booking ID', 'Customer', 'Phone', 'Vehicle', 'Returned on (IST)',
           'Rental (INR)', 'Discount (INR)', 'Location (INR)', 'Total (INR)']


class SaleReportQuery(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    file_type = serializers.ChoiceField(choices=['pdf', 'xlsx'])
    search = serializers.CharField(required=False, allow_blank=True, default='', max_length=250)

    def validate(self, attrs):
        if attrs['date_to'] < attrs['date_from']:
            raise serializers.ValidationError('End date must be on or after start date.')
        if attrs['date_to'].year >= 9999:
            raise serializers.ValidationError('Select an earlier end date.')
        return attrs


def report_rows(bookings):
    return [[b.reference, b.customer_name, b.customer_phone,
             ' · '.join(filter(None, [b.cart_vehicle.get('name', ''), b.vehicle_plate_number])),
             b.returned_at.astimezone(INDIA).strftime('%d/%m/%Y %H:%M'),
             b.rental_amount, b.discount_amount, b.delivery_amount, b.total_amount] for b in bookings]


def totals(rows):
    return [sum((row[col] for row in rows), Decimal('0')) for col in range(5, 9)]


def pdf_report(rows, period):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    output = BytesIO()
    styles = getSampleStyleSheet()
    cell = ParagraphStyle('ReportCell', parent=styles['Normal'], fontSize=8, leading=11)
    header = ParagraphStyle('ReportHead', parent=cell, textColor=colors.white)
    story = [Paragraph('Zudocars - Sale report', styles['Title']),
             Paragraph(escape(f'Return dates (IST): {period} | Completed transactions: {len(rows)} | Currency: INR'), styles['Normal']), Spacer(1, 16)]
    data = [[Paragraph(escape(h), header) for h in HEADERS]]
    for row in rows:
        data.append([Paragraph(escape(str(value) if col < 5 else f'{value:,.2f}'), cell) for col, value in enumerate(row)])
    if not rows:
        data.append([Paragraph('No completed transactions in this date range.', cell)] + [''] * 8)
    data.append([Paragraph('TOTAL', cell), '', '', '', ''] + [Paragraph(f'{value:,.2f}', cell) for value in totals(rows)])
    table = Table(data, colWidths=[109, 90, 79, 110, 91, 65, 65, 65, 80], repeatRows=1)
    commands = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#047857')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f0fdf4')]),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#d1fae5')),
                ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LINEBELOW', (0, 0), (-1, 0), .5, colors.HexColor('#047857'))]
    if not rows:
        commands.append(('SPAN', (0, 1), (-1, 1)))
    table.setStyle(TableStyle(commands))
    story.append(table)

    def footer(canvas, doc):
        canvas.setFont('Helvetica', 8)
        canvas.drawString(22, 18, 'Zudocars | Completed rental transactions | INR')
        canvas.drawRightString(819, 18, f'Page {doc.page}')

    SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=22, rightMargin=22,
                      topMargin=24, bottomMargin=32).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def xlsx_report(rows, period):
    # Native Office Open XML workbook; inline strings keep customer input literal.
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    def cell(value, col, row, style=0):
        ref = f'{chr(65 + col)}{row}'
        if isinstance(value, Decimal):
            return f'<c r="{ref}" s="{style or 2}"><v>{value:.2f}</v></c>'
        clean = ''.join(c for c in str(value) if ord(c) >= 32 or c in '\n\t\r')
        return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(clean)}</t></is></c>'
    records = [(1, ['Zudocars - Sale report'], 1), (2, [f'Return dates (IST): {period} | Currency: INR'], 0),
               (3, [f'Completed transactions: {len(rows)}'], 0), (5, HEADERS, 1)]
    records += [(i + 6, row, 0) for i, row in enumerate(rows)]
    records.append((len(rows) + 6, ['TOTAL', '', '', '', ''] + totals(rows), 3))
    sheet_rows = ''.join(f'<row r="{index}" ht="30" customHeight="1">' + ''.join(cell(v, col, index, style if col < 5 or style != 3 else 4) for col, v in enumerate(values)) + '</row>' for index, values, style in records)
    widths = [26, 26, 20, 32, 24, 20, 20, 20, 20]
    columns = ''.join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths, 1))
    sheet = f'<worksheet xmlns="{ns}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="5" topLeftCell="A6" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{columns}</cols><sheetData>{sheet_rows}</sheetData><autoFilter ref="A5:I{5 + len(rows)}"/><mergeCells count="3"><mergeCell ref="A1:I1"/><mergeCell ref="A2:I2"/><mergeCell ref="A3:I3"/></mergeCells></worksheet>'
    styles = f'<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF047857"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="5"><xf fontId="0" fillId="0" borderId="0"><alignment wrapText="1"/></xf><xf fontId="1" fillId="2" borderId="0"><alignment wrapText="1"/></xf><xf numFmtId="4" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/><xf fontId="1" fillId="2" borderId="0"/><xf numFmtId="4" fontId="1" fillId="2" borderId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sale report" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        archive.writestr('xl/styles.xml', styles)
        archive.writestr('xl/worksheets/sheet1.xml', sheet)
    return output.getvalue()


class SaleReportAPIView(BookingListAPIView):
    def get(self, request):
        query = SaleReportQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        start = datetime.combine(data['date_from'], time.min, INDIA)
        end = datetime.combine(data['date_to'] + timedelta(days=1), time.min, INDIA)
        bookings = Booking.objects.filter(status='completed', returned_at__gte=start, returned_at__lt=end).order_by('returned_at', 'reference')
        if not request.user.is_superuser and getattr(request.user, 'role', 'staff') != 'admin':
            bookings = bookings.filter(assigned_email__iexact=request.user.email)
        search = data['search'].lower()
        bookings = [b for b in bookings if not search or search in f"{b.reference} {b.customer_name} {b.customer_phone} {' · '.join(filter(None, [b.cart_vehicle.get('name', ''), b.vehicle_plate_number]))} Completed {b.assigned_email}".lower()]
        rows = report_rows(bookings)
        period = f"{data['date_from'].isoformat()} to {data['date_to'].isoformat()}"
        kind = data['file_type']
        content = pdf_report(rows, period) if kind == 'pdf' else xlsx_report(rows, period)
        response = HttpResponse(content, content_type='application/pdf' if kind == 'pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="sale-report-{data["date_from"]}-{data["date_to"]}.{kind}"'
        response['Cache-Control'] = 'no-store'
        return response
