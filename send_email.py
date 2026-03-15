"""
Utility Tracker - E-Mail bei neuer Ablesung oder Löschung.
Trigger: GitHub Actions bei Push auf meters/*/readings.json.
Anhang: Komplette Datentabelle als gezippte CSV.
"""

import io
import json
import os
import sys
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


def parse_iso(s):
    """Parse ISO timestamp, handling 'Z' suffix for Python < 3.11."""
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    return datetime.fromisoformat(s)


METER_INFO = {
    'garten-strom':      {'name': 'Strom',       'property': 'Garten',            'type': 'strom',  'icon': '⚡', 'unit': 'kWh', 'dec': 1},
    'garten-wasser':     {'name': 'Wasser',       'property': 'Garten',            'type': 'wasser', 'icon': '💧', 'unit': 'm³',  'dec': 3},
    'gustav-strom':      {'name': 'Strom',        'property': 'Gustav-Adolf-Str.', 'type': 'strom',  'icon': '⚡', 'unit': 'kWh', 'dec': 1},
    'gustav-kaltwasser': {'name': 'Kaltwasser',   'property': 'Gustav-Adolf-Str.', 'type': 'wasser', 'icon': '💧', 'unit': 'm³',  'dec': 3},
    'gustav-warmwasser': {'name': 'Warmwasser',   'property': 'Gustav-Adolf-Str.', 'type': 'wasser', 'icon': '🔴', 'unit': 'm³',  'dec': 3},
    'fritz-gas':         {'name': 'Gas',          'property': 'Fritz-Haber-Str.',  'type': 'gas',    'icon': '🔥', 'unit': 'm³',  'dec': 3},
    'fritz-strom1':      {'name': 'Strom HT',     'property': 'Fritz-Haber-Str.',  'type': 'strom',  'icon': '⚡', 'unit': 'kWh', 'dec': 1},
    'fritz-strom2':      {'name': 'Strom NT',     'property': 'Fritz-Haber-Str.',  'type': 'strom',  'icon': '⚡', 'unit': 'kWh', 'dec': 1},
}


def load_config(meter_id):
    path = SCRIPT_DIR / "meters" / meter_id / "config.json"
    if not path.exists():
        return {"price_history": []}
    return json.loads(path.read_text(encoding="utf-8"))


def load_readings(meter_id):
    path = SCRIPT_DIR / "meters" / meter_id / "readings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("readings", [])


def get_price_for_date(cfg, date_str):
    ph = cfg.get("price_history", [])
    if not ph:
        return {}
    sorted_ph = sorted(ph, key=lambda x: x["valid_from"], reverse=True)
    d = date_str[:10]
    for entry in sorted_ph:
        if entry["valid_from"] <= d:
            return entry
    return sorted_ph[-1]


def cons_to_kwh(cons, cfg, date_str, meter_type):
    if meter_type == 'gas':
        p = get_price_for_date(cfg, date_str)
        return cons * p.get("brennwert", 0) * p.get("zustandszahl", 0)
    if meter_type == 'strom':
        return cons
    return None


def cons_to_cost(cons, cfg, date_str, meter_type):
    p = get_price_for_date(cfg, date_str)
    if meter_type == 'gas':
        return cons * p.get("gas_price_per_kwh", 0) * p.get("brennwert", 0) * p.get("zustandszahl", 0)
    if meter_type == 'strom':
        return cons * p.get("price_per_kwh", 0)
    if meter_type == 'wasser':
        return cons * p.get("price_per_m3", 0)
    return 0


def has_prices(cfg):
    return len(cfg.get("price_history", [])) > 0


def get_setup_fragment(cfg):
    app_url = cfg.get("app_url", os.environ.get("APP_URL", "https://orvillewilbur.github.io/gas-tracker/"))
    pat = os.environ.get("GH_PAT", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not pat or not repo:
        return app_url, ""
    return app_url, f"setup={pat}&repo={repo}&"


def fv(val, dec):
    """Format value with given decimal places."""
    return f"{val:.{dec}f}"


def build_chart_png(readings, cfg, info):
    if not HAS_MPL:
        return None
    dp = [r for r in readings if r.get("daily_avg") is not None]
    if len(dp) < 2:
        return None

    mtype = info['type']
    dates, vals = [], []
    for r in dp:
        dates.append(parse_iso(r["timestamp"]))
        if mtype == 'gas':
            p = get_price_for_date(cfg, r["timestamp"])
            vals.append(r["daily_avg"] * p.get("brennwert", 1) * p.get("zustandszahl", 1))
        else:
            vals.append(r["daily_avg"])

    color_map = {'gas': '#f59e0b', 'strom': '#3b82f6', 'wasser': '#06b6d4'}
    color = color_map.get(mtype, '#3b82f6')
    ylabel = 'kWh/Tag' if mtype in ('gas', 'strom') else 'm³/Tag'

    fig, ax = plt.subplots(figsize=(6.4, 2.8))
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#1e293b")
    ax.fill_between(dates, vals, alpha=0.15, color=color)
    ax.plot(dates, vals, color=color, linewidth=2, marker="o", markersize=5,
            markerfacecolor=color, markeredgecolor="#0f172a", markeredgewidth=1.5)

    for d, v in zip(dates, vals):
        ax.annotate(f"{v:.1f}", (d, v), textcoords="offset points",
                    xytext=(0, 10), ha="center", fontsize=8, color="#f1f5f9", fontweight="bold")

    ax.set_ylabel(ylabel, color="#94a3b8", fontsize=10)
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


def build_email_html(readings, cfg, info, meter_id):
    mtype = info['type']
    unit = info['unit']
    dec = info['dec']
    icon = info['icon']
    hp = has_prices(cfg)

    latest = readings[-1]
    ts = parse_iso(latest["timestamp"])
    now_str = ts.strftime("%d.%m.%Y %H:%M")

    consumption = latest.get("consumption")
    daily_avg = latest.get("daily_avg")
    days = latest.get("days_since_last")

    # Consumption strings
    cons_unit = fv(consumption, dec) if consumption is not None else "—"
    cost_total = f"{cons_to_cost(consumption, cfg, latest['timestamp'], mtype):.2f}" if consumption is not None and hp else None

    # kWh for gas
    kwh_total = None
    if mtype == 'gas' and consumption is not None:
        kwh_total = f"{cons_to_kwh(consumption, cfg, latest['timestamp'], mtype):.1f}"

    # Liter for wasser
    liter_total = None
    if mtype == 'wasser' and consumption is not None:
        liter_total = f"{consumption * 1000:.0f}"

    # Per day
    if daily_avg is not None and days and days > 0:
        cons_day = fv(consumption / days, max(1, dec))
        cost_day = f"{cons_to_cost(consumption, cfg, latest['timestamp'], mtype) / days:.2f}" if hp else None
        kwh_day = f"{cons_to_kwh(consumption, cfg, latest['timestamp'], mtype) / days:.1f}" if mtype == 'gas' and consumption else None
        liter_day = f"{consumption * 1000 / days:.0f}" if mtype == 'wasser' and consumption else None
    else:
        cons_day = cost_day = kwh_day = liter_day = "—"

    # Previous reading
    prev = readings[-2] if len(readings) >= 2 else None
    prev_value = f"{fv(prev['value'], dec)} {unit}" if prev else "—"
    prev_date = parse_iso(prev["timestamp"]).strftime("%d.%m.%Y %H:%M") if prev else ""
    days_str = f"{days:.0f}" if days else "—"

    suspicious_banner = ""
    if latest.get("suspicious"):
        suspicious_banner = '<div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:16px;font-size:14px;color:#92400e;">⚠️ Dieser Wert wurde als <strong>verdächtig</strong> markiert.</div>'

    app_url, setup_frag = get_setup_fragment(cfg)

    # Title
    title = f"{icon} {info['property']} {info['name']}"
    color_map = {'gas': '#f59e0b', 'strom': '#3b82f6', 'wasser': '#06b6d4'}
    accent = color_map.get(mtype, '#3b82f6')

    # Stats columns
    def stat_cell(value, label):
        return f'<td style="text-align:center;padding:4px;"><span style="font-size:20px;font-weight:800;">{value}</span> <span style="color:#94a3b8;font-size:12px;">{label}</span></td>'

    stats_total = stat_cell(cons_unit, unit)
    if kwh_total:
        stats_total += stat_cell(kwh_total, "kWh")
    if liter_total:
        stats_total += stat_cell(liter_total, "Liter")
    if cost_total:
        stats_total += stat_cell(cost_total, "€")

    stats_day = stat_cell(cons_day, unit)
    if kwh_day and kwh_day != "—":
        stats_day += stat_cell(kwh_day, "kWh")
    if liter_day and liter_day != "—":
        stats_day += stat_cell(liter_day, "L")
    if cost_day and cost_day != "—":
        stats_day += stat_cell(cost_day, "€")

    # Chart
    chart_section = ""
    chart_data = build_chart_png(readings, cfg, info)
    if chart_data:
        ylabel = 'kWh/d' if mtype in ('gas', 'strom') else 'm³/d'
        chart_section = f'''
  <h2 style="font-size:16px;font-weight:700;margin:24px 0 12px;color:#0f172a;">Tagesverbrauch {ylabel}</h2>
  <div style="text-align:center;"><img src="cid:chart" style="max-width:100%;border-radius:12px;" /></div>
'''

    # Settings link
    settings_link = ""
    if app_url:
        settings_link = f'<div style="text-align:center;margin-top:16px;"><a href="{app_url}#{setup_frag}meter={meter_id}&settings=1" style="color:{accent};font-size:13px;">⚙️ Preiseinstellungen ändern</a></div>'

    # Table: last 20 readings
    recent = readings[-20:]
    rows = ""
    for r in reversed(recent):
        t = parse_iso(r["timestamp"])
        c = r.get("consumption")
        c_str = f'+{fv(c, dec)}' if c is not None else "—"
        avg_str = fv(r["daily_avg"], max(1, dec)) if r.get("daily_avg") is not None else "—"
        k = f'{cons_to_cost(c, cfg, r["timestamp"], mtype):.2f} €' if c is not None and hp else "—"
        is_sus = r.get("suspicious", False)
        flag = ' ⚠️' if is_sus else ''
        row_bg = 'background:#fef3c7;' if is_sus else ''

        delete_url = f'{app_url}#{setup_frag}meter={meter_id}&delete={r["timestamp"]}' if app_url else ''
        delete_cell = f'<td style="padding:6px 4px;border-bottom:1px solid #e2e8f0;text-align:center;{row_bg}"><a href="{delete_url}" style="color:#ef4444;text-decoration:none;font-size:14px;" title="Löschen">✕</a></td>' if delete_url else ''

        rows += f"""<tr>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;white-space:nowrap;{row_bg}">{t.strftime("%d.%m.%y")}{flag}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:600;{row_bg}">{fv(r['value'], dec)}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{c_str}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{avg_str}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;{row_bg}">{k}</td>
          {delete_cell}
        </tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:640px;margin:0 auto;padding:20px;">

<div style="background:linear-gradient(135deg,#0f172a,#1e40af);border-radius:16px 16px 0 0;padding:28px;text-align:center;">
  <h1 style="margin:0;color:#fff;font-size:22px;">{title}</h1>
  <p style="margin:4px 0 0;color:rgba(255,255,255,0.7);font-size:13px;">Neue Ablesung</p>
</div>

<div style="background:#fff;padding:24px;border-radius:0 0 16px 16px;">

  {suspicious_banner}

  <div style="background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:12px;">
    <div style="font-size:12px;color:#64748b;">Neuer Zählerstand</div>
    <div style="font-size:28px;font-weight:800;color:#1e40af;margin-top:6px;">{fv(latest['value'], dec)} {unit}</div>
    <div style="font-size:13px;color:#94a3b8;margin-top:4px;">{now_str}</div>
  </div>

  <div style="background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:12px;">
    <div style="font-size:12px;color:#64748b;">Letzte Ablesung</div>
    <div style="font-size:18px;font-weight:700;color:#334155;margin-top:6px;">{prev_value}</div>
    <div style="font-size:13px;color:#94a3b8;margin-top:4px;">{prev_date}</div>
  </div>

  <div style="background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:12px;">
    <div style="font-size:12px;color:#64748b;">Zeitraum</div>
    <div style="font-size:22px;font-weight:800;color:#334155;margin-top:4px;">{days_str} <span style="font-size:14px;color:#94a3b8;">Tage</span></div>
  </div>

  <div style="background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:12px;">
    <div style="font-size:12px;color:#64748b;margin-bottom:8px;">Verbrauch gesamt</div>
    <table style="width:100%;border-collapse:collapse;"><tr>{stats_total}</tr></table>
  </div>

  <div style="background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:12px;">
    <div style="font-size:12px;color:#64748b;margin-bottom:8px;">Ø pro Tag</div>
    <table style="width:100%;border-collapse:collapse;"><tr>{stats_day}</tr></table>
  </div>

  {chart_section}

  <h2 style="font-size:16px;font-weight:700;margin:24px 0 12px;color:#0f172a;">Letzte Ablesungen</h2>
  <div style="overflow-x:auto;">
  <table style="width:100%;border-collapse:collapse;font-size:12px;">
    <tr style="background:#f1f5f9;">
      <th style="padding:6px 8px;text-align:left;font-weight:600;color:#64748b;">Datum</th>
      <th style="padding:6px 8px;text-align:right;font-weight:600;color:#64748b;">Stand</th>
      <th style="padding:6px 8px;text-align:right;font-weight:600;color:#64748b;">{unit}</th>
      <th style="padding:6px 8px;text-align:right;font-weight:600;color:#64748b;">Ø/d</th>
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
    Zähler: {cfg.get('meter_id', '')} | Typ: {mtype}
  </div>
  {settings_link}

</div>

<div style="text-align:center;margin-top:16px;font-size:11px;color:#94a3b8;">Zähler-Tracker</div>
</div></body></html>"""


def build_csv(readings, cfg, info):
    mtype = info['type']
    dec = info['dec']
    unit = info['unit']
    header = f"Datum;Uhrzeit;Stand_{unit};Verbrauch_{unit};Tage;Tagesverbrauch_{unit}"
    if mtype == 'gas':
        header += ";Verbrauch_kWh"
    if has_prices(cfg):
        header += ";Kosten_EUR"
    header += ";Verdaechtig"

    lines = [header]
    for r in readings:
        ts = parse_iso(r["timestamp"])
        c = r.get("consumption")
        c_str = fv(c, dec) if c is not None else ""
        d = f'{r["days_since_last"]:.2f}' if r.get("days_since_last") is not None else ""
        a = fv(r["daily_avg"], max(1, dec)) if r.get("daily_avg") is not None else ""
        s = "ja" if r.get("suspicious") else "nein"

        line = f'{ts.strftime("%d.%m.%Y")};{ts.strftime("%H:%M")};{fv(r["value"], dec)};{c_str};{d};{a}'
        if mtype == 'gas':
            kwh = f'{cons_to_kwh(c, cfg, r["timestamp"], mtype):.1f}' if c is not None else ""
            line += f';{kwh}'
        if has_prices(cfg):
            k = f'{cons_to_cost(c, cfg, r["timestamp"], mtype):.2f}' if c is not None else ""
            line += f';{k}'
        line += f';{s}'
        lines.append(line)
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

    related = MIMEMultipart("related")
    related.attach(MIMEText(html_body, "html", "utf-8"))
    if chart_data:
        img = MIMEImage(chart_data, _subtype="png")
        img.add_header("Content-ID", "<chart>")
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
    if len(sys.argv) < 2:
        print("Usage: send_email.py <meter-id>")
        print(f"Available meters: {', '.join(METER_INFO.keys())}")
        sys.exit(1)

    meter_id = sys.argv[1]
    if meter_id not in METER_INFO:
        print(f"Unknown meter: {meter_id}")
        sys.exit(1)

    info = METER_INFO[meter_id]
    cfg = load_config(meter_id)
    readings = load_readings(meter_id)
    if not readings:
        print(f"Keine Ablesungen für {meter_id}")
        return

    latest = readings[-1]
    ts = parse_iso(latest["timestamp"])
    date_str = ts.strftime("%d.%m.%Y")
    dec = info['dec']

    subject = f"{info['property']} {info['name']}: {date_str} — {fv(latest['value'], dec)} {info['unit']}"
    if latest.get("consumption") is not None:
        subject += f" (+{fv(latest['consumption'], dec)})"
    if latest.get("suspicious"):
        subject += " ⚠️"

    chart_data = build_chart_png(readings, cfg, info)
    html = build_email_html(readings, cfg, info, meter_id)

    name_slug = f"{info['property'].lower().replace('.','').replace(' ','-')}-{info['name'].lower().replace(' ','-')}"
    csv_content = build_csv(readings, cfg, info)
    csv_filename = f"{name_slug}-{date_str.replace('.', '-')}.csv"
    zip_filename = f"{name_slug}-{date_str.replace('.', '-')}.zip"
    zip_data = create_zip(csv_content, csv_filename)

    send_email(subject, html, chart_data=chart_data, zip_data=zip_data, zip_filename=zip_filename)


if __name__ == "__main__":
    main()
