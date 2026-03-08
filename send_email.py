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
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

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
    ph = cfg.get("price_history", [])
    if not ph:
        return {"gas_price_per_kwh": 0, "brennwert": 0, "zustandszahl": 0}
    sorted_ph = sorted(ph, key=lambda x: x["valid_from"], reverse=True)
    d = date_str[:10]
    for entry in sorted_ph:
        if entry["valid_from"] <= d:
            return entry
    return sorted_ph[-1]


def m3_to_kwh(m3, cfg, date_str):
    p = get_price_for_date(cfg, date_str)
    return m3 * p["brennwert"] * p["zustandszahl"]


def price_per_m3(cfg, date_str):
    p = get_price_for_date(cfg, date_str)
    return p["gas_price_per_kwh"] * p["brennwert"] * p["zustandszahl"]


def get_setup_fragment(cfg):
    app_url = cfg.get("app_url", "")
    pat = os.environ.get("GH_PAT", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not app_url or not pat or not repo:
        return app_url, ""
    return app_url, f"setup={pat}&repo={repo}&"


def build_chart_png(readings, cfg):
    if not HAS_MPL:
        return None
    dp = [r for r in readings if r.get("daily_avg") is not None]
    if len(dp) < 2:
        return None

    dates = []
    kwh_days = []
    for r in dp:
        dates.append(datetime.fromisoformat(r["timestamp"]))
        p = get_price_for_date(cfg, r["timestamp"])
        kwh_d = r["daily_avg"] * p["brennwert"] * p["zustandszahl"]
        kwh_days.append(kwh_d)

    fig, ax = plt.subplots(figsize=(6.4, 2.8))
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#1e293b")

    ax.fill_between(dates, kwh_days, alpha=0.15, color="#3b82f6")
    ax.plot(dates, kwh_days, color="#3b82f6", linewidth=2, marker="o",
            markersize=5, markerfacecolor="#3b82f6", markeredgecolor="#0f172a",
            markeredgewidth=1.5)

    for d, v in zip(dates, kwh_days):
        ax.annotate(f"{v:.1f}", (d, v), textcoords="offset points",
                    xytext=(0, 10), ha="center", fontsize=8, color="#f1f5f9",
                    fontweight="bold")

    ax.set_ylabel("kWh/Tag", color="#94a3b8", fontsize=10)
    ax.tick_params(colors="#94a3b8", labelsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m.%y"))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#334155")
    ax.spines["bottom"].set_color("#334155")
    ax.grid(axis="y", color="#334155", linewidth=0.5, alpha=0.5)
    ax.set_ylim(bottom=0)
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.tight_layout(pad=1.0)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def build_email_html(readings, cfg):
    latest = readings[-1]
    ts = datetime.fromisoformat(latest["timestamp"])
    now_str = ts.strftime("%d.%m.%Y %H:%M")

    consumption = latest.get("consumption")
    daily_avg = latest.get("daily_avg")
    days = latest.get("days_since_last")
    pm3 = price_per_m3(cfg, latest["timestamp"])

    # Absolut
    cons_m3 = f"{consumption:.3f}" if consumption is not None else "—"
    cons_kwh = f"{m3_to_kwh(consumption, cfg, latest['timestamp']):.1f}" if consumption is not None else "—"
    cons_eur = f"{consumption * pm3:.2f}" if consumption is not None else "—"

    # Pro Tag
    if daily_avg is not None and days and days > 0:
        m3_day = f"{consumption / days:.2f}"
        kwh_day = f"{m3_to_kwh(consumption, cfg, latest['timestamp']) / days:.1f}"
        eur_day = f"{consumption * pm3 / days:.2f}"
    else:
        m3_day = kwh_day = eur_day = "—"

    # Letzter Zählerstand
    prev = readings[-2] if len(readings) >= 2 else None
    if prev:
        prev_ts = datetime.fromisoformat(prev["timestamp"])
        prev_str = f"{prev['value']:.3f} m³ — {prev_ts.strftime('%d.%m.%Y %H:%M')}"
    else:
        prev_str = "—"

    days_str = f"{days:.0f}" if days else "—"

    suspicious = latest.get("suspicious", False)
    suspicious_banner = ""
    if suspicious:
        suspicious_banner = '<div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:16px;font-size:14px;color:#92400e;">⚠️ Dieser Wert wurde als <strong>verdächtig</strong> markiert.</div>'

    app_url, setup_frag = get_setup_fragment(cfg)

    # Chart
    chart_section = ""
    chart_data = build_chart_png(readings, cfg)
    if chart_data:
        chart_section = '''
  <h2 style="font-size:16px;font-weight:700;margin:24px 0 12px;color:#0f172a;">Tagesverbrauch kWh/d</h2>
  <div style="text-align:center;"><img src="cid:chart" style="max-width:100%;border-radius:12px;" /></div>
'''

    # Settings link
    settings_link = ""
    if app_url:
        settings_link = f'<div style="text-align:center;margin-top:16px;"><a href="{app_url}#{setup_frag}settings=1" style="color:#3b82f6;font-size:13px;">⚙️ Preiseinstellungen ändern</a></div>'

    # Letzte 20 als Tabelle
    recent = readings[-20:]
    rows = ""
    for r in reversed(recent):
        t = datetime.fromisoformat(r["timestamp"])
        rp = price_per_m3(cfg, r["timestamp"])
        r_kwh = m3_to_kwh(r["consumption"], cfg, r["timestamp"]) if r.get("consumption") is not None else None
        c_m3 = f'+{r["consumption"]:.3f}' if r.get("consumption") is not None else "—"
        c_kwh = f'{r_kwh:.1f}' if r_kwh is not None else "—"
        avg_str = f'{r.get("daily_avg", 0):.2f}' if r.get("daily_avg") is not None else "—"
        k = f'{r["consumption"] * rp:.2f}' if r.get("consumption") is not None else "—"
        is_sus = r.get("suspicious", False)
        flag = ' ⚠️' if is_sus else ''
        row_bg = 'background:#fef3c7;' if is_sus else ''

        delete_url = f'{app_url}#{setup_frag}delete={r["timestamp"]}' if app_url else ''
        delete_cell = f'<td style="padding:6px 4px;border-bottom:1px solid #e2e8f0;text-align:center;{row_bg}"><a href="{delete_url}" style="color:#ef4444;text-decoration:none;font-size:14px;" title="Löschen">✕</a></td>' if delete_url else f'<td style="padding:6px 4px;border-bottom:1px solid #e2e8f0;{row_bg}"></td>'

        rows += f"""<tr>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;white-space:nowrap;{row_bg}">{t.strftime("%d.%m.%y")}{flag}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:600;{row_bg}">{r['value']:.3f}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{c_m3}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{c_kwh}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{avg_str}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{k} €</td>
          {delete_cell}
        </tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:640px;margin:0 auto;padding:20px;">

<div style="background:linear-gradient(135deg,#0f172a,#1e40af);border-radius:16px 16px 0 0;padding:28px;text-align:center;">
  <h1 style="margin:0;color:#fff;font-size:22px;">🔥 Neue Gasablesung</h1>
</div>

<div style="background:#fff;padding:24px;border-radius:0 0 16px 16px;">

  {suspicious_banner}

  <!-- 1. Neuer Zählerstand -->
  <div style="background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:12px;">
    <div style="font-size:12px;color:#64748b;">Neuer Zählerstand</div>
    <div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:4px;">
      <div style="font-size:26px;font-weight:800;color:#1e40af;">{latest['value']:.3f} m³</div>
      <div style="font-size:13px;color:#94a3b8;">{now_str}</div>
    </div>
  </div>

  <!-- 2. Letzter Zählerstand -->
  <div style="background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:12px;">
    <div style="font-size:12px;color:#64748b;">Letzte Ablesung</div>
    <div style="font-size:16px;font-weight:600;color:#334155;margin-top:4px;">{prev_str}</div>
  </div>

  <!-- 3. Zeitraum -->
  <div style="background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:12px;">
    <div style="font-size:12px;color:#64748b;">Zeitraum</div>
    <div style="font-size:22px;font-weight:800;color:#334155;margin-top:4px;">{days_str} <span style="font-size:14px;color:#94a3b8;">Tage</span></div>
  </div>

  <!-- 4. Verbrauch absolut -->
  <div style="background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:12px;">
    <div style="font-size:12px;color:#64748b;margin-bottom:8px;">Verbrauch seit letzter Ablesung</div>
    <table style="width:100%;border-collapse:collapse;">
      <tr>
        <td style="text-align:center;padding:4px;"><span style="font-size:20px;font-weight:800;">{cons_m3}</span> <span style="color:#94a3b8;font-size:12px;">m³</span></td>
        <td style="text-align:center;padding:4px;"><span style="font-size:20px;font-weight:800;">{cons_kwh}</span> <span style="color:#94a3b8;font-size:12px;">kWh</span></td>
        <td style="text-align:center;padding:4px;"><span style="font-size:20px;font-weight:800;">{cons_eur}</span> <span style="color:#94a3b8;font-size:12px;">€</span></td>
      </tr>
    </table>
  </div>

  <!-- 5. Verbrauch pro Tag -->
  <div style="background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:12px;">
    <div style="font-size:12px;color:#64748b;margin-bottom:8px;">Ø pro Tag</div>
    <table style="width:100%;border-collapse:collapse;">
      <tr>
        <td style="text-align:center;padding:4px;"><span style="font-size:20px;font-weight:800;">{m3_day}</span> <span style="color:#94a3b8;font-size:12px;">m³</span></td>
        <td style="text-align:center;padding:4px;"><span style="font-size:20px;font-weight:800;">{kwh_day}</span> <span style="color:#94a3b8;font-size:12px;">kWh</span></td>
        <td style="text-align:center;padding:4px;"><span style="font-size:20px;font-weight:800;">{eur_day}</span> <span style="color:#94a3b8;font-size:12px;">€</span></td>
      </tr>
    </table>
  </div>

  <!-- 6. Diagramm -->
  {chart_section}

  <!-- 7. Letzte 20 Ablesungen -->
  <h2 style="font-size:16px;font-weight:700;margin:24px 0 12px;color:#0f172a;">Letzte 20 Ablesungen</h2>
  <div style="overflow-x:auto;">
  <table style="width:100%;border-collapse:collapse;font-size:12px;">
    <tr style="background:#f1f5f9;">
      <th style="padding:6px 8px;text-align:left;font-weight:600;color:#64748b;">Datum</th>
      <th style="padding:6px 8px;text-align:right;font-weight:600;color:#64748b;">Stand</th>
      <th style="padding:6px 8px;text-align:right;font-weight:600;color:#64748b;">m³</th>
      <th style="padding:6px 8px;text-align:right;font-weight:600;color:#64748b;">kWh</th>
      <th style="padding:6px 8px;text-align:right;font-weight:600;color:#64748b;">Ø m³/d</th>
      <th style="padding:6px 8px;text-align:right;font-weight:600;color:#64748b;">Kosten</th>
      <th style="padding:6px 4px;text-align:center;font-weight:600;color:#64748b;width:28px;"></th>
    </tr>
    {rows}
  </table>
  </div>

  <div style="margin-top:10px;font-size:11px;color:#94a3b8;">
    ⚠️ = verdächtiger Wert &nbsp; ✕ = zum Löschen klicken<br>
    Komplette Tabelle ({len(readings)} Einträge) als CSV im ZIP-Anhang.
  </div>

  <div style="margin-top:20px;padding:12px;background:#f8fafc;border-radius:8px;font-size:12px;color:#94a3b8;">
    Zähler: {cfg.get('meter_type','')} (Nr. {cfg.get('meter_id','')}) | Preis: {pm3:.4f} €/m³
  </div>
  {settings_link}

</div>

<div style="text-align:center;margin-top:16px;font-size:11px;color:#94a3b8;">Gas Tracker</div>
</div></body></html>"""


def build_csv(readings, cfg):
    lines = ["Datum;Uhrzeit;Zaehlerstand_m3;Verbrauch_m3;Verbrauch_kWh;Tage;Tagesverbrauch_m3;Kosten_EUR;Preis_EUR_m3;Verdaechtig"]
    for r in readings:
        ts = datetime.fromisoformat(r["timestamp"])
        pm = price_per_m3(cfg, r["timestamp"])
        c_m3 = f'{r["consumption"]:.3f}' if r.get("consumption") is not None else ""
        c_kwh = f'{m3_to_kwh(r["consumption"], cfg, r["timestamp"]):.1f}' if r.get("consumption") is not None else ""
        d = f'{r["days_since_last"]:.2f}' if r.get("days_since_last") is not None else ""
        a = f'{r["daily_avg"]:.3f}' if r.get("daily_avg") is not None else ""
        k = f'{r["consumption"] * pm:.2f}' if r.get("consumption") is not None else ""
        s = "ja" if r.get("suspicious") else "nein"
        lines.append(f'{ts.strftime("%d.%m.%Y")};{ts.strftime("%H:%M")};{r["value"]:.3f};{c_m3};{c_kwh};{d};{a};{k};{pm:.4f};{s}')
    return "\n".join(lines)


def create_zip(csv_content, csv_filename):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(csv_filename, csv_content)
    return buf.getvalue()


def send_email(subject, html_body, chart_data=None, zip_data=None, zip_filename=None):
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

    # HTML + inline image
    related = MIMEMultipart("related")
    related.attach(MIMEText(html_body, "html", "utf-8"))
    if chart_data:
        img = MIMEImage(chart_data, _subtype="png")
        img.add_header("Content-ID", "<chart>")
        img.add_header("Content-Disposition", "inline", filename="chart.png")
        related.attach(img)
    msg.attach(related)

    # ZIP attachment
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

    chart_data = build_chart_png(readings, cfg)
    html = build_email_html(readings, cfg)

    csv_content = build_csv(readings, cfg)
    csv_filename = f"gasverbrauch-{date_str.replace('.', '-')}.csv"
    zip_filename = f"gasverbrauch-{date_str.replace('.', '-')}.zip"
    zip_data = create_zip(csv_content, csv_filename)

    send_email(subject, html, chart_data=chart_data, zip_data=zip_data, zip_filename=zip_filename)


if __name__ == "__main__":
    main()
