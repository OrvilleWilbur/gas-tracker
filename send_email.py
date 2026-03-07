"""
Gas Tracker - E-Mail bei neuer Ablesung oder Löschung.
Trigger: GitHub Actions bei Push auf readings.json.
Anhang: Komplette Datentabelle als gezippte CSV.
"""

import base64
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

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

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


def price_per_m3_for_date(cfg, date_str):
    p = get_price_for_date(cfg, date_str)
    return p["gas_price_per_kwh"] * p["brennwert"] * p["zustandszahl"]


def m3_to_kwh(cfg, m3, date_str):
    p = get_price_for_date(cfg, date_str)
    return m3 * p["brennwert"] * p["zustandszahl"]


def get_app_url(cfg):
    return cfg.get("app_url", "")


def get_setup_fragment(cfg):
    app_url = cfg.get("app_url", "")
    pat = os.environ.get("GH_PAT", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not app_url or not pat or not repo:
        return app_url, ""
    return app_url, f"setup={pat}&repo={repo}&"


def build_chart_png(readings, cfg):
    dp = [r for r in readings if r.get("daily_avg") is not None]
    if len(dp) < 2:
        return None

    dates = []
    costs_per_day = []
    for r in dp:
        t = datetime.fromisoformat(r["timestamp"])
        dates.append(t)
        p = get_price_for_date(cfg, r["timestamp"])
        kwh_d = r["daily_avg"] * p["brennwert"] * p["zustandszahl"]
        euro_d = kwh_d * p["gas_price_per_kwh"]
        costs_per_day.append(euro_d)

    fig, ax = plt.subplots(figsize=(6, 2.5), dpi=150)
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#1e293b")

    ax.fill_between(dates, costs_per_day, alpha=0.15, color="#3b82f6")
    ax.plot(dates, costs_per_day, color="#3b82f6", linewidth=2, marker="o",
            markersize=5, markerfacecolor="#3b82f6", markeredgecolor="#0f172a",
            markeredgewidth=1.5)

    for d, c in zip(dates, costs_per_day):
        ax.annotate(f"{c:.2f}", (d, c), textcoords="offset points",
                    xytext=(0, 10), ha="center", fontsize=7, color="#f1f5f9",
                    fontweight="bold")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
    ax.tick_params(colors="#94a3b8", labelsize=7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#334155")
    ax.spines["bottom"].set_color("#334155")
    ax.yaxis.label.set_color("#94a3b8")
    ax.set_ylabel("€/Tag", fontsize=8, color="#94a3b8")
    ax.grid(axis="y", color="#334155", linewidth=0.5)

    plt.tight_layout(pad=0.5)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def build_email_html(readings, cfg, chart_cid=None):
    latest = readings[-1]
    ts = datetime.fromisoformat(latest["timestamp"])
    date_str = ts.strftime("%d.%m.%Y")
    time_str = ts.strftime("%H:%M")
    app_url, setup_frag = get_setup_fragment(cfg)

    consumption = latest.get("consumption")
    daily_avg = latest.get("daily_avg")
    days = latest.get("days_since_last")

    prev = readings[-2] if len(readings) >= 2 else None
    prev_date = ""
    if prev:
        prev_ts = datetime.fromisoformat(prev["timestamp"])
        prev_date = prev_ts.strftime("%d.%m.%Y")

    kwh = m3_to_kwh(cfg, consumption, latest["timestamp"]) if consumption else 0
    kwh_d = kwh / days if days and days > 0 else 0
    p_m3 = price_per_m3_for_date(cfg, latest["timestamp"])
    costs = consumption * p_m3 if consumption else 0
    cost_d = costs / days if days and days > 0 else 0

    trend = ""
    if len(readings) >= 3 and daily_avg is not None and prev and prev.get("daily_avg"):
        prev_kwh_d = m3_to_kwh(cfg, prev["daily_avg"], prev["timestamp"])
        diff = (kwh_d - prev_kwh_d) / prev_kwh_d * 100 if prev_kwh_d else 0
        if abs(diff) < 5:
            trend = '<span style="color:#94a3b8">→ stabil</span>'
        elif diff > 0:
            trend = f'<span style="color:#ef4444">↑ +{diff:.0f}%</span>'
        else:
            trend = f'<span style="color:#10b981">↓ {diff:.0f}%</span>'

    suspicious_banner = ""
    if latest.get("suspicious"):
        suspicious_banner = '<div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:16px;font-size:14px;color:#92400e;">⚠️ Dieser Wert wurde als <strong>verdächtig</strong> markiert.</div>'

    settings_link = ""
    if app_url:
        settings_link = f'<div style="text-align:center;margin-top:16px;"><a href="{app_url}#{setup_frag}settings" style="color:#3b82f6;font-size:13px;">⚙️ Preiseinstellungen ändern</a></div>'

    chart_html = ""
    if chart_cid:
        chart_html = f"""
  <div style="margin:20px 0;">
    <h2 style="font-size:16px;font-weight:700;margin:0 0 12px;color:#0f172a;">Kosten pro Tag (€/d)</h2>
    <img src="cid:{chart_cid}" style="width:100%;max-width:600px;border-radius:12px;" alt="Kosten pro Tag">
  </div>"""

    recent = readings[-20:]
    rows = ""
    for r in reversed(recent):
        t = datetime.fromisoformat(r["timestamp"])
        rp = price_per_m3_for_date(cfg, r["timestamp"])
        rc = r.get("consumption")
        r_kwh = m3_to_kwh(cfg, rc, r["timestamp"]) if rc is not None else None
        c_kwh = f'{r_kwh:.1f}' if r_kwh is not None else "-"
        c_m3 = f'{rc:.3f}' if rc is not None else "-"
        d = f'{r.get("daily_avg", 0):.3f}' if r.get("daily_avg") is not None else "-"
        k = f'{rc * rp:.2f} €' if rc is not None else "-"
        is_sus = r.get("suspicious", False)
        flag = ' ⚠️' if is_sus else ''
        row_bg = 'background:#fef3c7;' if is_sus else ''

        delete_cell = ""
        if app_url:
            delete_url = f'{app_url}#{setup_frag}delete={r["timestamp"]}'
            delete_cell = f'<td style="padding:8px 6px;border-bottom:1px solid #e2e8f0;text-align:center;{row_bg}"><a href="{delete_url}" style="color:#ef4444;text-decoration:none;font-size:16px;" title="Löschen">✕</a></td>'
        else:
            delete_cell = f'<td style="padding:8px 6px;border-bottom:1px solid #e2e8f0;{row_bg}"></td>'

        rows += f"""<tr>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;{row_bg}">{t.strftime("%d.%m.%Y")}{flag}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:600;{row_bg}">{r['value']:.3f}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{c_m3}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{c_kwh}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{d}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{k}</td>
          {delete_cell}
        </tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:640px;margin:0 auto;padding:20px;">

<div style="background:linear-gradient(135deg,#0f172a,#1e40af);border-radius:16px 16px 0 0;padding:28px;text-align:center;">
  <h1 style="margin:0;color:#fff;font-size:22px;">🔥 Zählerstand gemeldet</h1>
  <p style="margin:8px 0 0;color:rgba(255,255,255,.7);font-size:14px;">{date_str} um {time_str} Uhr</p>
</div>

<div style="background:#fff;padding:24px;border-radius:0 0 16px 16px;">

  {suspicious_banner}

  <div style="text-align:center;margin-bottom:24px;">
    <div style="font-size:48px;font-weight:800;color:#0f172a;">{latest['value']:.3f}</div>
    <div style="font-size:16px;color:#64748b;">m³</div>
  </div>

  <div style="background:#f8fafc;border-radius:12px;padding:20px;margin-bottom:20px;">
    <div style="font-size:14px;color:#64748b;margin-bottom:12px;">
      Ø Tagesverbrauch seit letzter Ablesung am {prev_date} ({f"{days:.0f}" if days else "-"} Tage)
    </div>
    <div style="display:flex;gap:16px;flex-wrap:wrap;">
      <div style="flex:1;min-width:100px;text-align:center;">
        <div style="font-size:28px;font-weight:800;color:#1e40af;">{kwh_d:.1f}</div>
        <div style="font-size:12px;color:#64748b;">kWh/Tag</div>
      </div>
      <div style="flex:1;min-width:100px;text-align:center;">
        <div style="font-size:28px;font-weight:800;color:#d97706;">{cost_d:.2f}</div>
        <div style="font-size:12px;color:#64748b;">€/Tag</div>
      </div>
      <div style="flex:1;min-width:100px;text-align:center;">
        <div style="font-size:28px;font-weight:800;color:#059669;">{kwh:.0f}</div>
        <div style="font-size:12px;color:#64748b;">kWh gesamt</div>
      </div>
    </div>
    <div style="text-align:center;margin-top:10px;font-size:14px;font-weight:600;">
      {trend}
    </div>
  </div>

  {chart_html}

  <h2 style="font-size:16px;font-weight:700;margin:20px 0 12px;color:#0f172a;">Letzte 20 Ablesungen</h2>
  <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <tr style="background:#f1f5f9;">
      <th style="padding:8px 10px;text-align:left;font-weight:600;color:#64748b;">Datum</th>
      <th style="padding:8px 10px;text-align:right;font-weight:600;color:#64748b;">Stand</th>
      <th style="padding:8px 10px;text-align:right;font-weight:600;color:#64748b;">m³</th>
      <th style="padding:8px 10px;text-align:right;font-weight:600;color:#64748b;">kWh</th>
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
    Zähler: {cfg['meter_type']} (Nr. {cfg['meter_id']}) | Preis: {p_m3:.4f} €/m³
  </div>
  {settings_link}

</div>

<div style="text-align:center;margin-top:16px;font-size:11px;color:#94a3b8;">Gas Tracker</div>
</div></body></html>"""


def build_csv(readings, cfg):
    lines = ["Datum;Uhrzeit;Zaehlerstand_m3;Verbrauch_m3;Verbrauch_kWh;Tage;Tagesverbrauch_m3;Tagesverbrauch_kWh;Kosten_EUR;Preis_EUR_m3;Verdaechtig"]
    for r in readings:
        ts = datetime.fromisoformat(r["timestamp"])
        p = price_per_m3_for_date(cfg, r["timestamp"])
        rc = r.get("consumption")
        r_kwh = m3_to_kwh(cfg, rc, r["timestamp"]) if rc is not None else None
        da = r.get("daily_avg")
        da_kwh = m3_to_kwh(cfg, da, r["timestamp"]) if da is not None else None
        c = f'{rc:.3f}' if rc is not None else ""
        c_kwh = f'{r_kwh:.1f}' if r_kwh is not None else ""
        d = f'{r["days_since_last"]:.2f}' if r.get("days_since_last") is not None else ""
        a = f'{da:.3f}' if da is not None else ""
        a_kwh = f'{da_kwh:.1f}' if da_kwh is not None else ""
        k = f'{rc * p:.2f}' if rc is not None else ""
        s = "ja" if r.get("suspicious") else "nein"
        lines.append(f'{ts.strftime("%d.%m.%Y")};{ts.strftime("%H:%M")};{r["value"]:.3f};{c};{c_kwh};{d};{a};{a_kwh};{k};{p:.4f};{s}')
    return "\n".join(lines)


def create_zip(csv_content, csv_filename):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(csv_filename, csv_content)
    return buf.getvalue()


def send_email(subject, html_body, zip_data=None, zip_filename=None, chart_png=None):
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

    related = MIMEMultipart("related")
    related.attach(MIMEText(html_body, "html", "utf-8"))

    if chart_png:
        img = MIMEImage(chart_png, _subtype="png")
        img.add_header("Content-ID", "<chart_costs>")
        img.add_header("Content-Disposition", "inline", filename="chart.png")
        related.attach(img)

    msg.attach(related)

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

    kwh = m3_to_kwh(cfg, latest.get("consumption", 0), latest["timestamp"]) if latest.get("consumption") else 0

    subject = f"Gasablesung {date_str}: {latest['value']:.3f} m³"
    if latest.get("consumption") is not None:
        subject += f" (+{kwh:.0f} kWh)"
    if latest.get("suspicious"):
        subject += " ⚠️"

    chart_png = build_chart_png(readings, cfg)
    chart_cid = "chart_costs" if chart_png else None

    html = build_email_html(readings, cfg, chart_cid=chart_cid)

    csv_content = build_csv(readings, cfg)
    csv_filename = f"gasverbrauch-{date_str.replace('.', '-')}.csv"
    zip_filename = f"gasverbrauch-{date_str.replace('.', '-')}.zip"
    zip_data = create_zip(csv_content, csv_filename)

    send_email(subject, html, zip_data=zip_data, zip_filename=zip_filename, chart_png=chart_png)


if __name__ == "__main__":
    main()
