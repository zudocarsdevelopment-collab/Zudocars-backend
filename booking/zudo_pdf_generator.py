"""Black, gold and ivory booking PDFs, generated from saved booking prices."""
from datetime import datetime
from html import escape, unescape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

INK = colors.HexColor('#171717')
GOLD = colors.HexColor('#B9975B')
IVORY = colors.HexColor('#F7F2E9')
LINE = colors.HexColor('#DED5C6')
MUTED = colors.HexColor('#726A5D')


def _inr(value):
    return f"Rs. {float(value or 0):,.2f}"


def _fmt_dt(date, time):
    try:
        return datetime.strptime(f'{date} {time}', '%Y-%m-%d %H:%M').strftime('%d %b %Y, %I:%M %p')
    except (ValueError, TypeError):
        return f'{date or "-"} {time or ""}'.strip()


def _page(canvas, doc):
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(IVORY)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    # Wide sweeping curves echo the reference without using a raster background.
    for offset, color in [(0, GOLD), (7, INK)]:
        p = canvas.beginPath()
        p.moveTo(0, height)
        p.lineTo(width, height)
        p.lineTo(width, height - 28 + offset)
        p.curveTo(width - 120, height - 110 + offset, 330, height - 8 + offset, 260, height - 107 + offset)
        p.curveTo(180, height - 219 + offset, 75, height - 186 + offset, 0, height - 173 + offset)
        p.close()
        canvas.setFillColor(color)
        canvas.drawPath(p, fill=1, stroke=0)
    canvas.setFillColor(GOLD)
    canvas.setFont('Times-Italic', 47)
    canvas.drawString(46, height - 71, 'Z')
    canvas.setFont('Times-Roman', 27)
    canvas.drawString(46, height - 111, 'ZUDO CARS')
    canvas.setFont('Helvetica', 8)
    canvas.drawString(48, height - 128, 'YOUR JOURNEY. YOUR WAY.')
    for offset, color in [(5, GOLD), (0, INK)]:
        p = canvas.beginPath()
        p.moveTo(0, 0)
        p.lineTo(width, 0)
        p.lineTo(width, 64 + offset)
        p.curveTo(440, 96 + offset, 417, 23 + offset, 300, 41 + offset)
        p.curveTo(155, 67 + offset, 99, 105 + offset, 0, 53 + offset)
        p.close()
        canvas.setFillColor(color)
        canvas.drawPath(p, fill=1, stroke=0)
    canvas.setFillColor(GOLD)
    canvas.setFont('Helvetica-Bold', 10)
    canvas.drawString(46, 32, 'ZUDO CARS')
    canvas.setFillColor(IVORY)
    canvas.setFont('Helvetica', 8)
    canvas.drawRightString(width - 46, 32, 'Thank you for choosing Zudo Cars')
    canvas.restoreState()


def generate_zudo_estimate_pdf(payload, output_path):
    response = payload.get('booking_response') or {}
    estimate = response.get('estimate') or {}
    styles = {
        'body': ParagraphStyle('body', fontName='Helvetica', fontSize=9, leading=14, textColor=INK),
        'muted': ParagraphStyle('muted', fontName='Helvetica', fontSize=8, leading=12, textColor=MUTED),
        'label': ParagraphStyle('label', fontName='Helvetica-Bold', fontSize=8, leading=13, textColor=GOLD),
        'title': ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=21, leading=25, textColor=INK, alignment=2),
        'head': ParagraphStyle('head', fontName='Helvetica-Bold', fontSize=8, leading=12, textColor=GOLD),
        'total': ParagraphStyle('total', fontName='Helvetica-Bold', fontSize=11, leading=15, textColor=IVORY),
        'thanks': ParagraphStyle('thanks', fontName='Times-Italic', fontSize=28, leading=34, textColor=GOLD, alignment=2),
    }

    def p(text, style='body'):
        # Accept both raw input and the endpoint's escaped text, escaping once.
        return Paragraph(escape(unescape(str(text or '-'))), styles[style])

    def table(rows, widths, background=None):
        result = Table(rows, colWidths=widths, hAlign='LEFT')
        commands = [('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]
        if background:
            commands.append(('BACKGROUND', (0, 0), (-1, -1), background))
        result.setStyle(TableStyle(commands))
        return result

    doc = SimpleDocTemplate(output_path, pagesize=A4, leftMargin=46, rightMargin=46,
                            topMargin=185, bottomMargin=100,
                            title='Zudo Cars Booking Estimate', author='Zudo Cars')
    width = A4[0] - 92
    reference = response.get('reference', response.get('estimate_id', '-'))
    customer = [p('PREPARED FOR', 'label'), p(payload.get('customer_name', response.get('customer_name'))),
                p(f"+{payload.get('customer_country_code', '91')} {payload.get('customer_phone', '-')}")]
    metadata = table([[p('BOOKING NO.', 'muted'), p(reference)],
                      [p('ISSUED', 'muted'), p(payload.get('issued_date', datetime.now().strftime('%d %b %Y')))],
                      [p('STATUS', 'muted'), p(str(response.get('status', 'pending')).upper())]], [76, 185])
    story = [p('BOOKING ESTIMATE', 'title'), Spacer(1, 17),
             table([[customer, metadata]], [width - 261, 261]), Spacer(1, 17), p('YOUR RENTAL', 'label')]
    rental = [
        [p('VEHICLE', 'muted'), p(payload.get('vehicle_name')), p('DURATION', 'muted'), p(f"{estimate.get('total_booking_hours', '-')} hours")],
        [p('PICKUP', 'muted'), [p(payload.get('pickup_location_name')), p(_fmt_dt(payload.get('date_from'), payload.get('time_from')), 'muted')],
         p('RETURN', 'muted'), [p(payload.get('dropoff_location_name')), p(_fmt_dt(payload.get('date_to'), payload.get('time_to')), 'muted')]],
    ]
    story.extend([table(rental, [55, width / 2 - 55, 55, width / 2 - 55]), Spacer(1, 19)])
    charges = [('Vehicle rental', (estimate.get('vehicle') or {}).get('subtotal', 0))]
    charges.extend((r.get('name', 'Additional charge'), float(r.get('total_estimate') or 0) + float(r.get('tax_amt') or 0))
                   for r in estimate.get('reposition_charges', []))
    deposit = float(estimate.get('total_deposit_estimate') or 0)
    if deposit:
        charges.append(('Refundable security deposit', deposit))
    rows = [[p('NO.', 'head'), p('DESCRIPTION', 'head'), p('AMOUNT', 'head')]]
    rows.extend([p(f'{i:02d}'), p(name), p(_inr(amount))] for i, (name, amount) in enumerate(charges, 1))
    prices = table(rows, [38, width - 156, 118])
    prices.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), INK), ('BOX', (0, 0), (-1, -1), 0.8, GOLD),
        ('INNERGRID', (0, 1), (-1, -1), 0.4, LINE),
        ('LEFTPADDING', (0, 0), (-1, -1), 12), ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
    ]))
    total = float(estimate.get('total_final') or 0) + deposit
    totals = table([[p('RENTAL & CHARGES', 'muted'), p(_inr(estimate.get('total_final')))],
                    [p('REFUNDABLE DEPOSIT', 'muted'), p(_inr(deposit))],
                    [p('TOTAL DUE', 'total'), p(_inr(total), 'total')]], [117, 116], colors.HexColor('#EEE5D7'))
    totals.setStyle(TableStyle([('BACKGROUND', (0, -1), (-1, -1), INK),
                                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                                ('TOPPADDING', (0, 0), (-1, -1), 8),
                                ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    notes = [p('BOOKING INFORMATION', 'label'),
             p('Keep your booking number handy when contacting our team.', 'muted'), Spacer(1, 10),
             p('PAYMENT', 'label'), p('This estimate is not a payment receipt. Contact Zudo Cars for payment and confirmation details.', 'muted')]
    story.extend([prices, Spacer(1, 15), table([[notes, totals]], [width - 233, 233]),
                  Spacer(1, 10), p('Thank You', 'thanks'), p('We look forward to your journey with us.', 'muted')])
    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return output_path
