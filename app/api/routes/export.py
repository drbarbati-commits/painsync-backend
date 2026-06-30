import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.pain_log import PainLog
from app.models.user import User

router = APIRouter(prefix="/export", tags=["Export"])


def _is_premium(user: User) -> bool:
    return user.subscription_status in ("active", "trial")


@router.get("/pain-logs/csv")
def export_pain_logs_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_premium(current_user):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Premium subscription required",
        )

    logs = (
        db.query(PainLog)
        .filter(PainLog.user_id == current_user.id)
        .order_by(PainLog.timestamp.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Pain Level", "Location", "Locations",
        "Duration (hours)", "Duration (minutes)",
        "Symptoms", "Notes", "Body Temp (°C)", "Weight (kg)",
    ])

    for log in logs:
        writer.writerow([
            log.timestamp.isoformat() if log.timestamp else "",
            log.pain_level,
            log.pain_location,
            ", ".join(log.pain_locations) if log.pain_locations else "",
            log.duration_hours or "",
            log.duration_minutes or "",
            ", ".join(log.symptoms) if log.symptoms else "",
            log.notes or "",
            log.body_temp_celsius or "",
            log.weight_at_log_kg or "",
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=painsync_pain_logs.csv"
        },
    )


@router.get("/pain-logs/pdf")
def export_pain_logs_pdf(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_premium(current_user):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Premium subscription required",
        )

    logs = (
        db.query(PainLog)
        .filter(PainLog.user_id == current_user.id)
        .order_by(PainLog.timestamp.desc())
        .all()
    )

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("PainSync - Pain Logs Export", styles["Title"]))
    elements.append(Spacer(1, 0.25 * inch))
    elements.append(
        Paragraph(
            f"Exported on: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.25 * inch))

    if not logs:
        elements.append(Paragraph("No data available.", styles["Normal"]))
    else:
        table_data = [[
            "Date", "Pain Level", "Location",
            "Duration (min)", "Symptoms", "Notes",
        ]]
        for log in logs:
            dur = ""
            if log.duration_minutes:
                dur = str(int(log.duration_minutes))
            elif log.duration_hours:
                dur = str(int(log.duration_hours * 60))

            table_data.append([
                log.timestamp.strftime("%Y-%m-%d %H:%M") if log.timestamp else "",
                str(log.pain_level),
                log.pain_location,
                dur,
                ", ".join(log.symptoms) if log.symptoms else "",
                log.notes or "",
            ])

        col_widths = [1.4 * inch, 0.8 * inch, 1.5 * inch, 1.0 * inch, 2.0 * inch, 3.0 * inch]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6750A4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (5, 1), (5, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                colors.white,
                colors.HexColor("#F3EDF7"),
            ]),
        ]))
        elements.append(table)

    doc.build(elements)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=painsync_pain_logs.pdf"
        },
    )
