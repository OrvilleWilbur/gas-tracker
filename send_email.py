"""
Gas Tracker - E-Mail bei neuer Ablesung oder Löschung.
Trigger: GitHub Actions bei Push auf readings.json.
Anhang: Komplette Datentabelle als gezippte CSV.
"""

import io
import json
import os
import smtplib
import zipfile
from datetime import datetime, timedelta, timezone
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
READINGS_FILE = SCRIPT_DIR / "readings.json"
CONFIG_FILE = SCRIPT_DIR / "config.json"
CET = timezone(timedelta(hours=1))


def load_config():
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def load_readings():
    data = json.loads(READINGS_FILE.read_text(encoding="utf-8"))
    return data.get("readings", [])


def get_price_for_date(cfg, date_str):
    """Get the price entry valid for a given ISO date string."""
    ph = cfg.get("price_history", [])
    if not ph:
        return {"gas_price_per_kwh": 0, "brennwert": 0, "zustandszahl": 0}
    sorted_ph = sorted(ph, key=lambda x: x["valid_from"], reverse=True)
    d = date_str[:10]  # YYYY-MM-DD
    for entry in sorted_ph:
        if entry["valid_from"] <= d:
            return entry
    return sorted_ph[-1]


def price_per_m3_for_date(cfg, date_str):
    p = get_price_for_date(cfg, date_str)
    return p["gas_price_per_kwh"] * p["brennwert"] * p["zustandszahl"]


def get_app_url(cfg):
    return cfg.get("app_url", "")


def build_email_html(readings, cfg):
    latest = readings[-1]
    ts = datetime.fromisoformat(latest["timestamp"])
    date_str = ts.strftime("%d.%m.%Y %H:%M")
    p = price_per_m3_for_date(cfg, latest["timestamp"])
    app_url = get_app_url(cfg)

    consumption = latest.get("consumption")
    daily_avg = latest.get("daily_avg")
    days = latest.get("days_since_last")
    costs = consumption * p if consumption else 0
    suspicious = latest.get("suspicious", False)

    # Trend
    trend = ""
    if len(readings) >= 3 and daily_avg is not None:
        prev = readings[-2]
        if prev.get("daily_avg"):
            diff = (daily_avg - prev["daily_avg"]) / prev["daily_avg"] * 100
            if abs(diff) < 5:
                trend = '<span style="color:#94a3b8">→ stabil</span>'
            elif diff > 0:
                trend = f'<span style="color:#ef4444">↑ +{diff:.0f}%</span>'
            else:
                trend = f'<span style="color:#10b981">↓ {diff:.0f}%</span>'

    suspicious_banner = ""
    if suspicious:
        suspicious_banner = '<div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:16px;font-size:14px;color:#92400e;">⚠️ Dieser Wert wurde als <strong>verdächtig</strong> markiert.</div>'

    # Settings link
    settings_link = ""
    if app_url:
        settings_link = f'<div style="text-align:center;margin-top:16px;"><a href="{app_url}#settings" style="color:#3b82f6;font-size:13px;">⚙️ Preiseinstellungen ändern</a></div>'

    # Letzte 20 als Tabelle
    recent = readings[-20:]
    rows = ""
    for r in reversed(recent):
        t = datetime.fromisoformat(r["timestamp"])
        rp = price_per_m3_for_date(cfg, r["timestamp"])
        c = f'+{r["consumption"]:.3f}' if r.get("consumption") is not None else "-"
        d = f'{r.get("daily_avg", 0):.3f}' if r.get("daily_avg") is not None else "-"
        k = f'{r["consumption"] * rp:.2f} €' if r.get("consumption") is not None else "-"
        is_sus = r.get("suspicious", False)
        flag = ' ⚠️' if is_sus else ''
        row_bg = 'background:#fef3c7;' if is_sus else ''

        delete_cell = ""
if app_url:
            delete_url = f'{app_url}#delete={r["timestamp"]}'
            delete_cell = f'<td style="padding:8px 6px;border-bottom:1px solid #e2e8f0;text-align:center;{row_bg}"><a href="{delete_url}" style="color:#ef4444;text-decoration:none;font-size:16px;" title="Löschen">✕</a></td>'
        else:
            delete_cell = f'<td style="padding:8px 6px;border-bottom:1px solid #e2e8f0;{row_bg}"></td>'

        rows += f"""<tr>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;{row_bg}">{t.strftime("%d.%m.%Y")}{flag}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:600;{row_bg}">{r['value']:.3f}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{c}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{d}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{k}</td>
          {delete_cell}
        </tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:640px;margin:0 auto;padding:20px;">

<div style="background:linear-gradient(135deg,#0f172a,#1e40af);border-radius:16px 16px 0 0;padding:28px;text-align:center;">
  <h1 style="margin:0;color:#fff;font-size:22px;">🔥 Neue Gasablesung</h1>
  <p style="margin:8px 0 0;color:rgba(255,255,255,.7);font-size:14px;">{date_str} Uhr</p>
</div>

<div style="background:#fff;padding:24px;border-radius:0 0 16px 16px;">

  {suspicious_banner}

  <div style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap;">
    <div style="flex:1;min-width:120px;background:#f8fafc;border-radius:12px;padding:16px;text-align:center;">
      <div style="font-size:24px;font-weight:800;color:#1e40af;">{latest['value']:.3f}</div>
      <div style="font-size:12px;color:#64748b;">Zählerstand (m³)</div>
    </div>
    <div style="flex:1;min-width:120px;background:#f8fafc;border-radius:12px;padding:16px;text-align:center;">
      <div style="font-size:24px;font-weight:800;color:#059669;">{consumption:.3f if consumption else '-'}</div>
      <div style="font-size:12px;color:#64748b;">Verbrauch (m³)</div>
    </div>
    <div style="flex:1;min-width:120px;background:#f8fafc;border-radius:12px;padding:16px;text-align:center;">
      <div style="font-size:24px;font-weight:800;color:#d97706;">{costs:.2f} €</div>
      <div style="font-size:12px;color:#64748b;">Kosten</div>
    </div>
  </div>

  <div style="background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:20px;">
    <div style="font-size:14px;color:#64748b;">Ø Tagesverbrauch</div>
    <div style="font-size:20px;font-weight:700;margin-top:4px;">
      {f'{daily_avg:.3f} m³/Tag' if daily_avg else '-'} {trend}
    </div>
    <div style="font-size:13px;color:#94a3b8;margin-top:4px;">Zeitraum: {f'{days:.1f} Tage' if days else '-'}</div>
  </div>

  <h2 style="font-size:16px;font-weight:700;margin:20px 0 12px;color:#0f172a;">Letzte 20 Ablesungen</h2>
  <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <tr style="background:#f1f5f9;">
      <th style="padding:8px 10px;text-align:left;font-weight:600;color:#64748b;">Datum</th>
      <th style="padding:8px 10px;text-align:right;font-weight:600;color:#64748b;">Stand</th>
      <th style="padding:8px 10px;text-align:right;font-weight:600;color:#64748b;">Verbr.</th>
      <th style="padding:8px 10px;text-align:right;font-weight:600;color:#64748b;">Ø/Tag</th>
      <th style="padding:8px 10px;text-align:right;font-weight:600;color:#64748b;">Kosten</th>
      <th style="padding:8px 6px;text-align:center;font-weight:600;color:#64748b;width:30px;"></th>
    </tr>
    {rows}
  </table>

  <div style="margin-top:12px;font-size:12px;color:#94a3b8;">
    ⚠️ = verdächtiger Wert &nbsp; ✕ = zum Löschen klicken<br>
    Komplette Tabelle ({len(readings)} Einträge) als CSV im ZIP-Anhang.
  </div>

  <div style="margin-top:20px;padding:12px;background:#f8fafc;border-radius:8px;font-size:12px;color:#94a3b8;">
    Zähler: {cfg['meter_type']} (Nr. {cfg['meter_id']}) | Aktueller Preis: {p:.4f} €/m³<br>
    {len(cfg.get('price_history', []))} Preiseintr{'ag' if len(cfg.get('price_history', [])) == 1 else 'äge'} in der Historie
  </div>
  {settings_link}

</div>

<div style="text-align:center;margin-top:16px;font-size:11px;color:#94a3b8;">Gas Tracker</div>
</div></body></html>"""


def build_csv(readings, cfg):
    lines = ["Datum;Uhrzeit;Zaehlerstand_m3;Verbrauch_m3;Tage;Tagesverbrauch_m3;Kosten_EUR;Preis_EUR_m3;Verdaechtig"]
    for r in readings:
        ts = datetime.fromisoformat(r["timestamp"])
        p = price_per_m3_for_date(cfg, r["timestamp"])
        c = f'{r["consumption"]:.3f}' if r.get("consumption") is not None else ""
        d = f'{r["days_since_last"]:.2f}' if r.get("days_since_last") is not None else ""
        a = f'{r["daily_avg"]:.3f}' if r.get("daily_avg") is not None else ""
        k = f'{r["consumption"] * p:.2f}' if r.get("consumption") is not None else ""
        s = "ja" if r.get("suspicious") else "nein"
        lines.append(f'{ts.strftime("%d.%m.%Y")};{ts.strftime("%H:%M")};{r["value"]:.3f};{c};{d};{a};{k};{p:.4f};{s}')
    return "\n".join(lines)


def create_zip(csv_content, csv_filename):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(csv_filename, csv_content)
    return buf.getvalue()


def send_email(subject, html_body, zip_data=None, zip_filename=None):
    smtp_email = os.environ.get("SMTP_EMAIL")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    notify_raw = os.environ.get("NOTIFY_EMAIL", smtp_email)
    if not smtp_email or not smtp_password:
        print("SMTP nicht konfiguriert.")
        return
    recipients = [a.strip() for a in notify_raw.split(",") if a.strip()]

    msg = MIMEMultipart("mixed")
    msg["From"] = smtp_email
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if zip_data and zip_filename:
        part = MIMEBase("application", "zip")
        part.set_payload(zip_data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=zip_filename)
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(smtp_email, smtp_password)
        server.sendmail(smtp_email, recipients, msg.as_string())
    print(f"E-Mail gesendet an {', '.join(recipients)}")


def main():
    cfg = load_config()
    readings = load_readings()
    if not readings:
        return

    latest = readings[-1]
    ts = datetime.fromisoformat(latest["timestamp"])
    date_str = ts.strftime("%d.%m.%Y")

    subject = f"Gasablesung {date_str}: {latest['value']:.3f} m³"
    if latest.get("consumption") is not None:
        subject += f" (+{latest['consumption']:.3f})"
    if latest.get("suspicious"):
        subject += " ⚠️"

    html = build_email_html(readings, cfg)

    csv_content = build_csv(readings, cfg)
    csv_filename = f"gasverbrauch-{date_str.replace('.', '-')}.csv"
    zip_filename = f"gasverbrauch-{date_str.replace('.', '-')}.zip"
    zip_data = create_zip(csv_content, csv_filename)

    send_email(subject, html, zip_data=zip_data, zip_filename=zip_filename)


if __name__ == "__main__":
    main()
