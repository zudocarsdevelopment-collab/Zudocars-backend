# zudo_pdf_generator.py
"""
Generates a Zudo Cars-branded estimate PDF from:
  1) the booking context you already have when you call theRentOS
     (customer phone, vehicle name, location names, dates/times) -- because
     theRentOS's /admin/estimates response does NOT echo these back, and
  2) the raw JSON response returned by theRentOS's estimate-creation endpoint.

Visual design is intentionally different from the AVS/theRentOS PDF:
navy/teal brand bar instead of black/yellow, single accent panel instead
of a full yellow sidebar, rounded-style section headers.
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

FONT = 'Helvetica'
FONT_BOLD = 'Helvetica-Bold'
FONT_ITALIC = 'Helvetica-Oblique'

# ---- Zudo Cars brand palette (swap these to match real brand guidelines) ----
NAVY = colors.HexColor('#0B2545')
TEAL = colors.HexColor('#13A89E')
TEAL_LIGHT = colors.HexColor('#E6F7F6')
INK = colors.HexColor('#1A1A1A')
MUTED = colors.HexColor('#6B7280')
WHITE = colors.white


def _styles():
    ss = getSampleStyleSheet()
    styles = {
        'brand': ParagraphStyle('brand', parent=ss['Normal'], fontName=FONT_BOLD,
                                 fontSize=20, textColor=WHITE, leading=22),
        'brand_sub': ParagraphStyle('brand_sub', parent=ss['Normal'], fontName=FONT,
                                     fontSize=8.5, textColor=colors.HexColor('#CFE8E6'), leading=12),
        'contact': ParagraphStyle('contact', parent=ss['Normal'], fontName=FONT,
                                   fontSize=8.5, textColor=WHITE, alignment=TA_RIGHT, leading=12),
        'h1': ParagraphStyle('h1', parent=ss['Normal'], fontName=FONT_BOLD,
                              fontSize=17, textColor=INK),
        'badge': ParagraphStyle('badge', parent=ss['Normal'], fontName=FONT_BOLD,
                                 fontSize=7.5, textColor=NAVY),
        'meta_label': ParagraphStyle('meta_label', parent=ss['Normal'], fontName=FONT,
                                      fontSize=8, textColor=MUTED, alignment=TA_RIGHT),
        'meta_value': ParagraphStyle('meta_value', parent=ss['Normal'], fontName=FONT_BOLD,
                                      fontSize=11, textColor=INK, alignment=TA_RIGHT),
        'section': ParagraphStyle('section', parent=ss['Normal'], fontName=FONT_BOLD,
                                   fontSize=9.5, textColor=TEAL, spaceAfter=4),
        'label': ParagraphStyle('label', parent=ss['Normal'], fontName=FONT,
                                 fontSize=9, textColor=MUTED),
        'value': ParagraphStyle('value', parent=ss['Normal'], fontName=FONT_BOLD,
                                 fontSize=9.5, textColor=INK, alignment=TA_RIGHT),
        'panel_label': ParagraphStyle('panel_label', parent=ss['Normal'], fontName=FONT,
                                       fontSize=8.7, textColor=NAVY),
        'panel_value': ParagraphStyle('panel_value', parent=ss['Normal'], fontName=FONT_BOLD,
                                       fontSize=9.5, textColor=NAVY, alignment=TA_RIGHT),
        'grand_label': ParagraphStyle('grand_label', parent=ss['Normal'], fontName=FONT,
                                       fontSize=8.5, textColor=colors.HexColor('#CFE8E6')),
        'grand_sub': ParagraphStyle('grand_sub', parent=ss['Normal'], fontName=FONT,
                                     fontSize=6.8, textColor=colors.HexColor('#9FC8C5')),
        'grand_value': ParagraphStyle('grand_value', parent=ss['Normal'], fontName=FONT_BOLD,
                                       fontSize=14.5, textColor=WHITE, alignment=TA_RIGHT),
        'footnote': ParagraphStyle('footnote', parent=ss['Normal'], fontName=FONT_ITALIC,
                                    fontSize=8, textColor=MUTED),
        'staff_name': ParagraphStyle('staff_name', parent=ss['Normal'], fontName=FONT_BOLD,
                                      fontSize=9.5, textColor=INK),
        'staff_meta': ParagraphStyle('staff_meta', parent=ss['Normal'], fontName=FONT,
                                      fontSize=8.3, textColor=MUTED),
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
    """'2026-08-05' + '00:00' -> '05 Aug 2026, 12:00 AM'"""
    if not date_str:
        return '\u2014'
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        date_part = d.strftime('%d %b %Y')
    except ValueError:
        date_part = date_str
    if time_str:
        try:
            t = datetime.strptime(time_str, '%H:%M')
            return f"{date_part}, {t.strftime('%I:%M %p')}"
        except ValueError:
            pass
    return date_part


def _kv_table(rows, col_widths, styles, label_style='label', value_style='value'):
    data = []
    for label, value in rows:
        data.append([Paragraph(label, styles[label_style]), Paragraph(str(value), styles[value_style])])
    t = Table(data, colWidths=col_widths, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#EDEDED')),
    ]))
    return t


def generate_zudo_estimate_pdf(payload, output_path):
    """
    payload: dict shaped like --

    {
        "customer_name": "Zudo cars",
        "customer_phone": "6282744675",
        "customer_country_code": "91",
        "vehicle_name": "Alto K10 PETROL MT",
        "transmission": "Manual",
        "fuel_type": "Petrol",
        "pickup_location_name": "Edapally Lulu",
        "dropoff_location_name": "Edapally Lulu",
        "date_from": "2026-08-05", "time_from": "00:00",
        "date_to": "2026-08-07", "time_to": "00:00",
        "extra_km_charge": 8.0,
        "staff_name": "Ani", "staff_phone": "+91 9387005555",
        "therentos_response": { ... the raw JSON from /admin/estimates ... }
    }

    output_path: where to write the PDF file.
    Returns output_path.
    """
    styles = _styles()
    tr = payload.get('therentos_response', {}) or {}
    est = tr.get('estimate', {}) or {}
    km = est.get('km', {}) or {}
    vehicle_est = est.get('vehicle', {}) or {}
    reposition = est.get('reposition_charges', []) or []

    estimate_id = tr.get('estimate_id', '\u2014')
    status = (tr.get('status') or 'draft').upper()
    public_url = tr.get('public_url', '')

    booking_hours = est.get('total_booking_hours')
    duration_days = round(booking_hours / 24, 1) if booking_hours else None
    duration_label = f"{duration_days:g} day" if duration_days else '\u2014'

    rent_incl_tax = vehicle_est.get('subtotal')  # base + tax, excl. reposition/deposit
    total_incl_gst = est.get('total_final')      # rent + reposition, incl tax, excl deposit
    deposit = est.get('total_deposit_estimate')
    grand_total = None
    if total_incl_gst is not None and deposit is not None:
        grand_total = float(total_incl_gst) + float(deposit)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=0, bottomMargin=14 * mm, leftMargin=14 * mm, rightMargin=14 * mm,
    )
    story = []

    # ---- Brand header bar (full-bleed, so build it as its own table with 0 side margins) ----
    header_inner = Table(
        [[
            Paragraph('ZUDO CARS', styles['brand']),
            Paragraph(
                f"Phone <b>+91 {payload.get('staff_phone_display', '90000 00000')}</b><br/>"
                f"Self-drive &amp; chauffeur rentals, Kerala",
                styles['contact'],
            ),
        ]],
        colWidths=[84 * mm, 70 * mm],
    )
    header_inner.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (-1, 0), (-1, 0), 0),
    ]))
    header_outer = Table([[header_inner]], colWidths=[182 * mm])
    header_outer.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('LEFTPADDING', (0, 0), (-1, -1), 14 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 14 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 10 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10 * mm),
    ]))
    story.append(header_outer)
    story.append(Spacer(1, 10 * mm))

    # ---- Title row: Estimate + badge   |   Estimate ID + date ----
    title_left = Table(
        [[Paragraph('Estimate', styles['h1'])],
         [Table([[Paragraph('&nbsp;&nbsp;PROVISIONAL &mdash; INVOICE&nbsp;&nbsp;', styles['badge'])]],
                style=TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), TEAL_LIGHT),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))]],
        colWidths=[100 * mm],
    )
    title_left.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (1, 0), (1, 0), 4)]))

    title_right = Table(
        [[Paragraph('ESTIMATE #', styles['meta_label']), ],
         [Paragraph(f"ZD-{estimate_id}", styles['meta_value'])],
         [Paragraph('STATUS', styles['meta_label'])],
         [Paragraph(status, styles['meta_value'])]],
        colWidths=[82 * mm],
    )
    title_right.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 1)]))

    title_row = Table([[title_left, title_right]], colWidths=[100 * mm, 82 * mm])
    title_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.append(title_row)
    story.append(Spacer(1, 7 * mm))

    # ---- Left column content ----
    country_code = payload.get('customer_country_code', '91')
    phone = payload.get('customer_phone', '\u2014')
    left_flow = []
    left_flow.append(Paragraph('CUSTOMER', styles['section']))
    left_flow.append(_kv_table(
        [('Name', payload.get('customer_name', tr.get('customer_name', '\u2014'))),
         ('Mobile', f"+{country_code} {phone}")],
        [40 * mm, 60 * mm], styles,
    ))
    left_flow.append(Spacer(1, 5 * mm))
    left_flow.append(Paragraph('VEHICLE', styles['section']))
    left_flow.append(_kv_table(
        [('Category', payload.get('vehicle_name', '\u2014')),
         ('Transmission', payload.get('transmission', '\u2014')),
         ('Fuel type', payload.get('fuel_type', '\u2014'))],
        [40 * mm, 60 * mm], styles,
    ))
    left_flow.append(Spacer(1, 5 * mm))
    left_flow.append(Paragraph('LOCATIONS', styles['section']))
    left_flow.append(_kv_table(
        [('Pickup', payload.get('pickup_location_name', '\u2014')),
         ('Drop-off', payload.get('dropoff_location_name', '\u2014'))],
        [40 * mm, 60 * mm], styles,
    ))
    left_flow.append(Spacer(1, 6 * mm))
    staff_name = payload.get('staff_name')
    if staff_name:
        left_flow.append(Paragraph('ESTIMATE PREPARED BY', styles['section']))
        left_flow.append(Paragraph(staff_name, styles['staff_name']))
        left_flow.append(Paragraph(f"Zudo Cars &middot; {payload.get('staff_phone', '')}", styles['staff_meta']))

    # ---- Right column: teal panel ----
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
    amount_rows.append(('Total (incl. GST)', _inr(total_incl_gst)))
    amount_rows.append(('Refundable deposit', _inr(deposit)))

    panel_content = []
    panel_content.append(Paragraph('RENTAL TERMS', ParagraphStyle(
        'panel_h', fontName=FONT_BOLD, fontSize=8.5, textColor=NAVY, spaceAfter=3)))
    panel_content.append(_kv_table(panel_rows, [30 * mm, 32 * mm], styles, 'panel_label', 'panel_value'))
    panel_content.append(Spacer(1, 4 * mm))
    panel_content.append(Paragraph('AMOUNT', ParagraphStyle(
        'panel_h2', fontName=FONT_BOLD, fontSize=8.5, textColor=NAVY, spaceAfter=3)))
    panel_content.append(_kv_table(amount_rows, [30 * mm, 32 * mm], styles, 'panel_label', 'panel_value'))

    panel_table = Table([[c] for c in panel_content], colWidths=[66 * mm])
    panel_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), TEAL_LIGHT),
        ('LEFTPADDING', (0, 0), (-1, -1), 5 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5 * mm),
        ('TOPPADDING', (0, 0), (0, 0), 5 * mm),
        ('BOTTOMPADDING', (-1, -1), (-1, -1), 5 * mm),
    ]))

    grand_table = Table(
        [[Table(
            [[Paragraph('GRAND TOTAL', styles['grand_label'])],
             [Paragraph('Rent + charges + GST + deposit', styles['grand_sub'])]],
            colWidths=[28 * mm],
        ), Paragraph(_inr(grand_total), styles['grand_value'])]],
        colWidths=[28 * mm, 38 * mm],
    )
    grand_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (0, 0), 5 * mm),
        ('RIGHTPADDING', (-1, 0), (-1, 0), 5 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 4 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4 * mm),
    ]))

    right_flow = [panel_table, Spacer(1, 3), grand_table]

    body_row = Table(
        [[left_flow, right_flow]],
        colWidths=[104 * mm, 68 * mm],
    )
    body_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (1, 0), (1, 0), 6 * mm),
    ]))
    story.append(body_row)

    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width='100%', color=colors.HexColor('#EDEDED'), thickness=0.7))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        'Validity: 4 hours from issue, subject to vehicle availability at time of confirmation. '
        'Fuel is charged at actuals and is non-refundable.',
        styles['footnote'],
    ))
    if public_url:
        story.append(Spacer(1, 2))
        story.append(Paragraph(f'View online: {public_url}', styles['footnote']))

    doc.build(story)
    return output_path