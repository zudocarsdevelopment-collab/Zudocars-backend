# zudo_pdf_generator.py
"""
Generates a Zudo Cars-branded estimate PDF from:
  1) the booking context you already have when you call theRentOS
     (customer phone, vehicle name, location names, dates/times) -- because
     theRentOS's /admin/estimates response does NOT echo these back, and
  2) the raw JSON response returned by theRentOS's estimate-creation endpoint.

v2 design: modern "SaaS dashboard" look -- deep navy header with a soft
teal gradient-blob accent and a thin top stripe, rounded card sections,
color-coded status chip, and a bold coral-accented grand total card.
"""

import io
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.graphics.shapes import Drawing, Group, Path, Circle

FONT = 'Helvetica'
FONT_BOLD = 'Helvetica-Bold'
FONT_ITALIC = 'Helvetica-Oblique'

# ---- Fixed Zudo Cars contact number (always shown in the header; not fetched) ----
ZUDO_PHONE_DISPLAY = '85899 00964'

# ---- Zudo Cars brand palette (modern navy / teal / coral) ----
NAVY = colors.HexColor('#0A1930')
NAVY_SOFT = colors.HexColor('#132A4D')
TEAL = colors.HexColor('#14B8A6')
TEAL_DARK = colors.HexColor('#0D9488')
TEAL_LIGHT = colors.HexColor('#EAFBF8')
TEAL_BORDER = colors.HexColor('#BEEEE7')
CORAL = colors.HexColor('#FF6B4A')
AMBER = colors.HexColor('#F59E0B')
AMBER_LIGHT = colors.HexColor('#FEF3E2')
INK = colors.HexColor('#0F172A')
MUTED = colors.HexColor('#64748B')
BORDER = colors.HexColor('#E6EAF0')
CARD_BG = colors.HexColor('#F8FAFC')
WHITE = colors.white

PAGE_W, PAGE_H = A4
HEADER_H = 40 * mm
TOP_STRIP_H = 2.4 * mm

STATUS_CHIP = {
    'DRAFT': (AMBER_LIGHT, AMBER),
    'SENT': (colors.HexColor('#E7ECFB'), colors.HexColor('#3B5BDB')),
    'CONFIRMED': (TEAL_LIGHT, TEAL_DARK),
    'ACCEPTED': (TEAL_LIGHT, TEAL_DARK),
    'CANCELLED': (colors.HexColor('#FDEAEA'), colors.HexColor('#E03131')),
}
STATUS_DEFAULT = (colors.HexColor('#EEF1F5'), MUTED)


def _styles():
    ss = getSampleStyleSheet()
    styles = {
        'brand': ParagraphStyle('brand', parent=ss['Normal'], fontName=FONT_BOLD,
                                 fontSize=21, textColor=WHITE, leading=23),
        'brand_sub': ParagraphStyle('brand_sub', parent=ss['Normal'], fontName=FONT,
                                     fontSize=8.7, textColor=colors.HexColor('#9FD8D1'), leading=12.5),
        'contact': ParagraphStyle('contact', parent=ss['Normal'], fontName=FONT,
                                   fontSize=8.7, textColor=WHITE, alignment=TA_RIGHT, leading=13),
        'h1': ParagraphStyle('h1', parent=ss['Normal'], fontName=FONT_BOLD,
                              fontSize=19, textColor=INK, leading=22),
        'h1_sub': ParagraphStyle('h1_sub', parent=ss['Normal'], fontName=FONT,
                                  fontSize=9, textColor=MUTED, leading=12),
        'chip_label': ParagraphStyle('chip_label', parent=ss['Normal'], fontName=FONT_BOLD,
                                      fontSize=7.3, textColor=TEAL_DARK, alignment=TA_CENTER, leading=9),
        'chip_num': ParagraphStyle('chip_num', parent=ss['Normal'], fontName=FONT_BOLD,
                                    fontSize=7.3, textColor=MUTED, alignment=TA_RIGHT, leading=9),
        'chip_num_val': ParagraphStyle('chip_num_val', parent=ss['Normal'], fontName=FONT_BOLD,
                                        fontSize=10.5, textColor=INK, alignment=TA_RIGHT, leading=13),
        'section': ParagraphStyle('section', parent=ss['Normal'], fontName=FONT_BOLD,
                                   fontSize=8.7, textColor=NAVY, leading=11),
        'label': ParagraphStyle('label', parent=ss['Normal'], fontName=FONT,
                                 fontSize=9, textColor=MUTED, leading=13),
        'value': ParagraphStyle('value', parent=ss['Normal'], fontName=FONT_BOLD,
                                 fontSize=9.5, textColor=INK, alignment=TA_RIGHT, leading=13),
        'panel_label': ParagraphStyle('panel_label', parent=ss['Normal'], fontName=FONT,
                                       fontSize=8.6, textColor=colors.HexColor('#0B4B45'), leading=12.5),
        'panel_value': ParagraphStyle('panel_value', parent=ss['Normal'], fontName=FONT_BOLD,
                                       fontSize=9.5, textColor=NAVY, alignment=TA_RIGHT, leading=12.5),
        'panel_total_label': ParagraphStyle('panel_total_label', parent=ss['Normal'], fontName=FONT_BOLD,
                                             fontSize=9, textColor=TEAL_DARK, leading=12.5),
        'panel_total_value': ParagraphStyle('panel_total_value', parent=ss['Normal'], fontName=FONT_BOLD,
                                             fontSize=10.5, textColor=TEAL_DARK, alignment=TA_RIGHT, leading=13),
        'panel_h': ParagraphStyle('panel_h', fontName=FONT_BOLD, fontSize=8, textColor=TEAL_DARK,
                                   leading=10),
        'grand_label': ParagraphStyle('grand_label', parent=ss['Normal'], fontName=FONT_BOLD,
                                       fontSize=9, textColor=colors.HexColor('#BFD3E8'), leading=12),
        'grand_sub': ParagraphStyle('grand_sub', parent=ss['Normal'], fontName=FONT,
                                     fontSize=6.9, textColor=colors.HexColor('#7E93AE'), leading=9.5),
        'grand_value': ParagraphStyle('grand_value', parent=ss['Normal'], fontName=FONT_BOLD,
                                       fontSize=15.5, textColor=colors.HexColor('#FF8A6E'), alignment=TA_RIGHT, leading=17),
        'footnote': ParagraphStyle('footnote', parent=ss['Normal'], fontName=FONT_ITALIC,
                                    fontSize=8, textColor=MUTED, leading=11.5),
        'footer_brand': ParagraphStyle('footer_brand', parent=ss['Normal'], fontName=FONT_BOLD,
                                        fontSize=8.3, textColor=NAVY),
        'staff_name': ParagraphStyle('staff_name', parent=ss['Normal'], fontName=FONT_BOLD,
                                      fontSize=9.5, textColor=INK, leading=12),
        'staff_meta': ParagraphStyle('staff_meta', parent=ss['Normal'], fontName=FONT,
                                      fontSize=8.3, textColor=MUTED, leading=11.5),
    }
    return styles


def _inr(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return '\u2014'
    if value == int(value):
        return f"Rs. {int(value):,}"
    return f"Rs. {value:,.2f}"


def _fmt_dt(date_str, time_str):
    """'2026-08-05' + '00:00' -> '05 Aug, 12:00 AM' (compact, fits the narrow panel column)"""
    if not date_str:
        return '\u2014'
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        date_part = d.strftime('%d %b')
    except ValueError:
        date_part = date_str
    if time_str:
        try:
            t = datetime.strptime(time_str, '%H:%M')
            return f"{date_part}, {t.strftime('%I:%M %p').lstrip('0')}"
        except ValueError:
            pass
    return date_part


def _kv_table(rows, col_widths, styles, label_style='label', value_style='value', line=True):
    data = []
    for label, value in rows:
        data.append([Paragraph(label, styles[label_style]), Paragraph(str(value), styles[value_style])])
    t = Table(data, colWidths=col_widths, hAlign='LEFT')
    style_cmds = [
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 3.6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.6),
    ]
    if line:
        style_cmds.append(('LINEBELOW', (0, 0), (-1, -2), 0.6, BORDER))
    t.setStyle(TableStyle(style_cmds))
    return t


def _car_icon_group(scale, fill_color):
    """Builds an original, simple side-view car icon as a reportlab shapes Group,
    in a local 0-240 x 0-100 coordinate box, scaled and colored as requested."""
    body = Path(fillColor=fill_color, strokeColor=None)
    body.moveTo(10, 35)
    body.curveTo(10, 45, 15, 52, 25, 55)
    body.lineTo(55, 55)
    body.curveTo(60, 72, 75, 85, 100, 88)
    body.lineTo(140, 88)
    body.curveTo(160, 85, 172, 72, 178, 55)
    body.lineTo(210, 55)
    body.curveTo(222, 52, 228, 45, 228, 35)
    body.lineTo(228, 28)
    body.lineTo(10, 28)
    body.closePath()
    return Group(
        body,
        Circle(55, 28, 20, fillColor=fill_color, strokeColor=None),
        Circle(185, 28, 20, fillColor=fill_color, strokeColor=None),
        transform=(scale, 0, 0, scale, 0, 0),
    )


def _draw_car_silhouette_canvas(c, x0, y0, scale, color, alpha, rotate=0):
    c.saveState()
    c.translate(x0, y0)
    if rotate:
        c.rotate(rotate)
    c.scale(scale, scale)
    c.setFillColor(color)
    c.setFillAlpha(alpha)
    c.setStrokeAlpha(0)
    body = c.beginPath()
    body.moveTo(10, 35)
    body.curveTo(10, 45, 15, 52, 25, 55)
    body.lineTo(55, 55)
    body.curveTo(60, 72, 75, 85, 100, 88)
    body.lineTo(140, 88)
    body.curveTo(160, 85, 172, 72, 178, 55)
    body.lineTo(210, 55)
    body.curveTo(222, 52, 228, 45, 228, 35)
    body.lineTo(228, 28)
    body.lineTo(10, 28)
    body.close()
    c.drawPath(body, fill=1, stroke=0)
    c.circle(55, 28, 20, fill=1, stroke=0)
    c.circle(185, 28, 20, fill=1, stroke=0)
    c.restoreState()


def _draw_blob_cluster(c, cx, cy, base_r, color, alphas):
    c.saveState()
    for i, a in enumerate(alphas):
        r = base_r * (1 - i * 0.22)
        c.setFillColor(color)
        c.setFillAlpha(a)
        c.setStrokeAlpha(0)
        c.circle(cx - i * base_r * 0.18, cy + i * base_r * 0.12, r, fill=1, stroke=0)
    c.restoreState()


def _page_background(canvas, doc):
    """Draws the full header band (gradient-ish navy + teal blob accents + top
    stripe) and a faint full-page car watermark, all sitting behind the
    flowable content drawn afterwards."""
    canvas.saveState()

    # Deep navy header band
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, fill=1, stroke=0)

    # Subtle secondary navy wash in the lower part of the header for depth
    canvas.setFillColor(NAVY_SOFT)
    canvas.setFillAlpha(0.55)
    canvas.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H * 0.42, fill=1, stroke=0)
    canvas.setFillAlpha(1)

    # Soft teal gradient-blob accent, top-right of the header
    _draw_blob_cluster(
        canvas, cx=PAGE_W - 34 * mm, cy=PAGE_H - 10 * mm, base_r=30 * mm,
        color=TEAL, alphas=[0.16, 0.14, 0.14, 0.16],
    )

    # Thin coral top stripe -- modern two-tone accent line
    canvas.setFillColor(CORAL)
    canvas.rect(0, PAGE_H - TOP_STRIP_H, PAGE_W, TOP_STRIP_H, fill=1, stroke=0)

    # Faint full-page car watermark, lower-right of the body area
    _draw_car_silhouette_canvas(
        canvas, x0=PAGE_W - 60 * mm, y0=34 * mm, scale=0.95,
        color=NAVY, alpha=0.045, rotate=0,
    )

    canvas.restoreState()


def _rounded_card(flowables, colWidth, bg, border=None, pad=5 * mm, radius=7):
    inner = Table([[f] for f in flowables], colWidths=[colWidth - 2 * pad])
    style_cmds = [
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (0, 0), 0),
        ('BOTTOMPADDING', (-1, -1), (-1, -1), 0),
        ('TOPPADDING', (0, 1), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -2), 0),
    ]
    inner.setStyle(TableStyle(style_cmds))
    outer = Table([[inner]], colWidths=[colWidth])
    outer_style = [
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('ROUNDEDCORNERS', [radius, radius, radius, radius]),
        ('LEFTPADDING', (0, 0), (-1, -1), pad),
        ('RIGHTPADDING', (0, 0), (-1, -1), pad),
        ('TOPPADDING', (0, 0), (-1, -1), pad),
        ('BOTTOMPADDING', (0, 0), (-1, -1), pad),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]
    if border:
        outer_style.append(('BOX', (0, 0), (-1, -1), 0.75, border))
    outer.setStyle(TableStyle(outer_style))
    return outer


def _section_header(text, styles):
    dot = Drawing(3 * mm, 3 * mm)
    dot.add(Circle(1.5 * mm, 1.5 * mm, 1.5 * mm, fillColor=TEAL, strokeColor=None))
    t = Table([[dot, Paragraph(text, styles['section'])]], colWidths=[4.2 * mm, None])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 1.5 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t


def generate_zudo_estimate_pdf(payload, output_path):
    styles = _styles()
    tr = payload.get('therentos_response', {}) or {}
    est = tr.get('estimate', {}) or {}
    km = est.get('km', {}) or {}
    vehicle_est = est.get('vehicle', {}) or {}
    reposition = est.get('reposition_charges', []) or []

    estimate_id = tr.get('estimate_id', '\u2014')
    status = (tr.get('status') or 'draft').upper()
    public_url = tr.get('public_url', '')
    chip_bg, chip_fg = STATUS_CHIP.get(status, STATUS_DEFAULT)

    booking_hours = est.get('total_booking_hours')
    duration_days = round(booking_hours / 24, 1) if booking_hours else None
    duration_label = f"{duration_days:g} day" if duration_days else '\u2014'

    rent_incl_tax = vehicle_est.get('subtotal')
    total_incl_gst = est.get('total_final')
    deposit = est.get('total_deposit_estimate')
    grand_total = None
    if total_incl_gst is not None and deposit is not None:
        grand_total = float(total_incl_gst) + float(deposit)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=0, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
    )
    story = []

    # ---------------------------------------------------------------- HEADER
    logo_h = 10 * mm
    logo_s = logo_h / 100.0
    logo_drawing = Drawing(238 * logo_s, logo_h)
    logo_drawing.add(_car_icon_group(logo_s, WHITE))

    brand_row = Table(
        [[logo_drawing, Paragraph('ZUDO CARS', styles['brand'])]],
        colWidths=[23 * mm, None],
    )
    brand_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 2.5 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    header_left = Table(
        [[brand_row],
         [Spacer(1, 2)],
         [Paragraph('SELF-DRIVE &amp; CHAUFFEUR RENTALS &middot; KERALA', styles['brand_sub'])]],
        colWidths=[110 * mm],
    )
    header_left.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    header_right = Paragraph(
        f"Call or WhatsApp<br/><b>+91 {ZUDO_PHONE_DISPLAY}</b>",
        styles['contact'],
    )

    header_row = Table([[header_left, header_right]], colWidths=[112 * mm, 62 * mm])
    header_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))

    header_outer = Table([[header_row]], colWidths=[178 * mm])
    header_outer.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 16 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 15 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15 * mm),
    ]))
    story.append(header_outer)
    story.append(Spacer(1, 11 * mm))

    # ------------------------------------------------------------- TITLE ROW
    badge = Table(
        [[Paragraph('&nbsp;&#9679;&nbsp; PROVISIONAL ESTIMATE &nbsp;', styles['chip_label'])]],
        colWidths=[52 * mm],
    )
    badge.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), TEAL_LIGHT),
        ('ROUNDEDCORNERS', [10, 10, 10, 10]),
        ('BOX', (0, 0), (-1, -1), 0.6, TEAL_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 3.4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.4),
    ]))

    title_left = Table(
        [[Paragraph('Estimate', styles['h1'])],
         [Spacer(1, 2.5 * mm)],
         [badge]],
        colWidths=[100 * mm],
    )
    title_left.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 0)]))

    est_chip = Table(
        [[Paragraph(f"ZD-{estimate_id}", styles['chip_num_val'])],
         [Paragraph('ESTIMATE NO.', styles['chip_num'])]],
        colWidths=[38 * mm],
    )
    est_chip.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), CARD_BG),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
        ('BOX', (0, 0), (-1, -1), 0.6, BORDER),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.5 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.5 * mm),
        ('TOPPADDING', (0, 0), (0, 0), 3 * mm),
        ('BOTTOMPADDING', (-1, -1), (-1, -1), 3 * mm),
        ('TOPPADDING', (0, 1), (-1, -1), 0.5 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 0.5 * mm),
    ]))

    status_chip = Table(
        [[Paragraph(status, ParagraphStyle('status_val', fontName=FONT_BOLD, fontSize=10.5,
                                            textColor=chip_fg, alignment=TA_RIGHT, leading=13))],
         [Paragraph('STATUS', styles['chip_num'])]],
        colWidths=[30 * mm],
    )
    status_chip.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), chip_bg),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.5 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.5 * mm),
        ('TOPPADDING', (0, 0), (0, 0), 3 * mm),
        ('BOTTOMPADDING', (-1, -1), (-1, -1), 3 * mm),
        ('TOPPADDING', (0, 1), (-1, -1), 0.5 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 0.5 * mm),
    ]))

    title_right = Table([[est_chip, status_chip]], colWidths=[40 * mm, 32 * mm])
    title_right.setStyle(TableStyle([
        ('LEFTPADDING', (1, 0), (1, 0), 2.5 * mm),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    title_row = Table([[title_left, title_right]], colWidths=[106 * mm, 72 * mm])
    title_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.append(title_row)
    story.append(Spacer(1, 8 * mm))

    # -------------------------------------------------------------- BODY
    country_code = payload.get('customer_country_code', '91')
    phone = payload.get('customer_phone', '\u2014')

    customer_card = _rounded_card(
        [
            _section_header('CUSTOMER', styles),
            Spacer(1, 2.2 * mm),
            _kv_table(
                [('Name', payload.get('customer_name', tr.get('customer_name', '\u2014'))),
                 ('Mobile', f"+{country_code} {phone}")],
                [22 * mm, 62 * mm], styles,
            ),
        ], colWidth=90 * mm, bg=CARD_BG, border=BORDER,
    )

    vehicle_card = _rounded_card(
        [
            _section_header('VEHICLE', styles),
            Spacer(1, 2.2 * mm),
            _kv_table(
                [('Category', payload.get('vehicle_name', '\u2014')),
                 ('Transmission', payload.get('transmission', '\u2014')),
                 ('Fuel type', payload.get('fuel_type', '\u2014'))],
                [22 * mm, 62 * mm], styles,
            ),
        ], colWidth=90 * mm, bg=CARD_BG, border=BORDER,
    )

    locations_card = _rounded_card(
        [
            _section_header('LOCATIONS', styles),
            Spacer(1, 2.2 * mm),
            _kv_table(
                [('Pickup', payload.get('pickup_location_name', '\u2014')),
                 ('Drop-off', payload.get('dropoff_location_name', '\u2014'))],
                [22 * mm, 62 * mm], styles,
            ),
        ], colWidth=90 * mm, bg=CARD_BG, border=BORDER,
    )

    left_flow = [customer_card, Spacer(1, 4 * mm), vehicle_card, Spacer(1, 4 * mm), locations_card]

    staff_name = payload.get('staff_name')
    if staff_name:
        left_flow += [
            Spacer(1, 4 * mm),
            _rounded_card(
                [
                    Paragraph('ESTIMATE PREPARED BY', ParagraphStyle(
                        'sm_label', fontName=FONT, fontSize=7.6, textColor=MUTED, leading=10)),
                    Spacer(1, 1.4 * mm),
                    Paragraph(staff_name, styles['staff_name']),
                    Paragraph(f"Zudo Cars &middot; {ZUDO_PHONE_DISPLAY}", styles['staff_meta']),
                ], colWidth=90 * mm, bg=WHITE, border=BORDER,
            ),
        ]

    panel_rows = [
        ('Start', _fmt_dt(payload.get('date_from'), payload.get('time_from'))),
        ('End', _fmt_dt(payload.get('date_to'), payload.get('time_to'))),
        ('Duration', duration_label),
        ('Allowed KM', f"{km.get('total_km_limit', '\u2014')} km"),
    ]
    if payload.get('extra_km_charge') is not None:
        panel_rows.append(('Extra KM charge', f"{_inr(payload['extra_km_charge'])} / km"))

    amount_rows = [('Rent (incl. tax)', _inr(rent_incl_tax))]
    for r in reposition:
        incl_tax = (r.get('total_estimate') or 0) + (r.get('tax_amt') or 0)
        amount_rows.append((r.get('name', 'Charge'), _inr(incl_tax)))
    amount_rows.append(('Refundable deposit', _inr(deposit)))

    amount_table_rows = _kv_table(amount_rows, [30 * mm, 34 * mm], styles, 'panel_label', 'panel_value')
    total_row = _kv_table(
        [('Total (incl. GST)', _inr(total_incl_gst))],
        [30 * mm, 34 * mm], styles, 'panel_total_label', 'panel_total_value', line=False,
    )

    right_card = _rounded_card(
        [
            Paragraph('RENTAL TERMS', styles['panel_h']),
            Spacer(1, 2 * mm),
            _kv_table(panel_rows, [30 * mm, 34 * mm], styles, 'panel_label', 'panel_value'),
            Spacer(1, 3.5 * mm),
            Paragraph('AMOUNT', styles['panel_h']),
            Spacer(1, 2 * mm),
            amount_table_rows,
            HRFlowable(width='100%', thickness=0.7, color=TEAL_BORDER, spaceBefore=1.5, spaceAfter=1.5),
            total_row,
        ], colWidth=72 * mm, bg=TEAL_LIGHT, border=TEAL_BORDER,
    )

    grand_inner = Table(
        [[Table(
            [[Paragraph('GRAND TOTAL', styles['grand_label'])],
             [Paragraph('Rent + charges + GST + deposit', styles['grand_sub'])]],
            colWidths=[26 * mm],
            style=TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 0),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]),
        ), Paragraph(_inr(grand_total), styles['grand_value'])]],
        colWidths=[26 * mm, 35 * mm],
    )
    grand_inner.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    grand_card = _rounded_card([grand_inner], colWidth=72 * mm, bg=NAVY, pad=5.5 * mm, radius=9)

    right_flow = [right_card, Spacer(1, 4 * mm), grand_card]

    body_row = Table(
        [[left_flow, right_flow]],
        colWidths=[90 * mm, 72 * mm],
    )
    body_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('LEFTPADDING', (1, 0), (1, 0), 8 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(body_row)

    story.append(Spacer(1, 9 * mm))
    story.append(HRFlowable(width='100%', color=BORDER, thickness=0.8))
    story.append(Spacer(1, 3.5 * mm))
    story.append(Paragraph(
        '<b>Validity:</b> 4 hours from issue, subject to vehicle availability at time of confirmation. '
        'Fuel is charged at actuals and is non-refundable.',
        styles['footnote'],
    ))

    doc.build(story, onFirstPage=_page_background, onLaterPages=_page_background)
    return output_path