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

    plt.tight_layout(pad=0.5
