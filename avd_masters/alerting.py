"""
AVD Masters — Real Alerting & Management Engine

This is the practical heart that turns AVD Masters from "pretty monitoring" into something that actually helps you manage your GPU fleet.

Core responsibilities:
- Evaluate current state against rules
- Fire meaningful alerts with context and recommended actions
- Tie into cost, forecasting, Midas, Signals, and Governance
- Be actionable (not just "utilization is high")
- Notify humans when shit gets funky (email supported)

Design goals:
- Simple to extend with new rules
- Rich context (cost impact, recommendations, etc.)
- Multiple output formats (console, email, JSON, webhooks later)
- "Yum factor": professional, clear, slightly spicy Grok voice in notifications
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """A single actionable alert."""
    id: str
    severity: Severity
    title: str
    description: str
    resource: str
    metric: str
    value: float
    threshold: float
    impact: str | None = None          # e.g. "$420/month extra cost"
    recommendation: str | None = None  # actionable next step
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tags: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "resource": self.resource,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "impact": self.impact,
            "recommendation": self.recommendation,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
        }

    def __str__(self) -> str:
        icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🔥"}[self.severity.value]
        return (
            f"{icon} [{self.severity.upper()}] {self.title}\n"
            f"   Resource: {self.resource}\n"
            f"   {self.metric}: {self.value} (threshold: {self.threshold})\n"
            f"   Impact: {self.impact or 'N/A'}\n"
            f"   → {self.recommendation or 'No recommendation yet'}"
        )


class AlertEngine:
    """
    The actual engine that evaluates data and fires alerts.
    """

    def __init__(self):
        self._rules: list[Callable] = []
        self._alerts: list[Alert] = []

    def add_rule(self, rule_func: Callable[[dict], Alert | None]):
        """Register a new alerting rule."""
        self._rules.append(rule_func)

    def evaluate(self, context: dict) -> list[Alert]:
        """
        Run all rules against the current context and return fired alerts.

        Context example:
        {
            "host_name": "...",
            "gpu_util_avg": 87.3,
            "imbalance_score": 52.0,
            "daily_cost": 1240.0,
            "forecast_next_30d": 48000,
            ...
        }
        """
        new_alerts = []
        for rule in self._rules:
            try:
                alert = rule(context)
                if alert:
                    new_alerts.append(alert)
                    self._alerts.append(alert)
            except Exception as e:
                # Never let one bad rule break the whole engine
                print(f"[AlertEngine] Rule failed: {e}")

        return new_alerts

    def get_alerts(self, severity: Severity | None = None) -> list[Alert]:
        if severity:
            return [a for a in self._alerts if a.severity == severity]
        return list(self._alerts)

    def clear(self):
        self._alerts.clear()


# =============================================================================
# Built-in Rules (these are the ones that actually help you manage)
# =============================================================================

def rule_high_gpu_utilization(context: dict) -> Alert | None:
    """Fire when average GPU utilization is critically high."""
    util = context.get("gpu_util_avg")
    if util is not None and util >= 90:
        return Alert(
            id=f"high-util-{context.get('host_name', 'unknown')}",
            severity=Severity.CRITICAL,
            title="Critical GPU Saturation",
            description=f"Host is running at {util}% average GPU utilization.",
            resource=context.get("host_name", "unknown"),
            metric="gpu_util_avg",
            value=util,
            threshold=90,
            impact="Risk of user experience degradation + potential throttling",
            recommendation="Consider adding capacity or rebalancing workloads immediately.",
        )
    elif util is not None and util >= 75:
        return Alert(
            id=f"high-util-warning-{context.get('host_name', 'unknown')}",
            severity=Severity.WARNING,
            title="High GPU Utilization",
            description=f"Host GPU utilization at {util}%.",
            resource=context.get("host_name", "unknown"),
            metric="gpu_util_avg",
            value=util,
            threshold=75,
            impact="Approaching performance cliff",
            recommendation="Monitor closely. Plan capacity increase.",
        )
    return None


def rule_high_cost_burn(context: dict) -> Alert | None:
    """Alert on expensive daily burn rate."""
    daily_cost = context.get("daily_cost_usd")
    if daily_cost is not None and daily_cost > 800:
        return Alert(
            id=f"high-cost-{context.get('host_name', 'unknown')}",
            severity=Severity.WARNING,
            title="High Daily Cost Burn",
            description=f"This host/pool is burning ~${daily_cost:.0f} per day.",
            resource=context.get("host_name", "unknown"),
            metric="daily_cost_usd",
            value=daily_cost,
            threshold=800,
            impact=f"~${daily_cost * 30:.0f} per month at current rate",
            recommendation="Review for optimization opportunities or right-sizing.",
        )
    return None


def rule_severe_imbalance(context: dict) -> Alert | None:
    """Fire on bad pool imbalance (the original killer feature)."""
    score = context.get("imbalance_score")
    if score is not None and score >= 50:
        return Alert(
            id=f"imbalance-critical-{context.get('pool_name', 'unknown')}",
            severity=Severity.CRITICAL,
            title="Severe Pool Imbalance",
            description=f"Pool imbalance score is {score}. Workloads are very unevenly distributed.",
            resource=context.get("pool_name", "unknown"),
            metric="imbalance_score",
            value=score,
            threshold=50,
            impact="Wasted capacity + inconsistent user experience",
            recommendation="Rebalance workloads or adjust session placement logic.",
        )
    elif score is not None and score >= 35:
        return Alert(
            id=f"imbalance-warning-{context.get('pool_name', 'unknown')}",
            severity=Severity.WARNING,
            title="Moderate Pool Imbalance",
            description=f"Pool imbalance score is {score}.",
            resource=context.get("pool_name", "unknown"),
            metric="imbalance_score",
            value=score,
            threshold=35,
            impact="Suboptimal resource usage",
            recommendation="Consider rebalancing soon.",
        )
    return None


def rule_forecast_overrun(context: dict) -> Alert | None:
    """Alert when forecasting predicts major cost overrun."""
    forecast = context.get("forecast_next_30d_cost")
    baseline = context.get("baseline_monthly_cost")
    if forecast and baseline and forecast > baseline * 1.4:
        overrun = forecast - baseline
        return Alert(
            id=f"forecast-overrun-{context.get('entity', 'unknown')}",
            severity=Severity.WARNING,
            title="Projected Cost Overrun",
            description=f"Current trends predict ${forecast:,.0f} next 30 days vs baseline ${baseline:,.0f}.",
            resource=context.get("entity", "unknown"),
            metric="forecast_next_30d_cost",
            value=forecast,
            threshold=baseline * 1.4,
            impact=f"+${overrun:,.0f} projected overrun",
            recommendation="Investigate utilization trends or apply optimization recommendations now.",
        )
    return None


# =============================================================================
# Latency & User Experience Rules (making AVD actually feel good)
# =============================================================================

def rule_high_latency(context: dict) -> Alert | None:
    """Fire when user experience is suffering (high frame times or input lag)."""
    p95_frame = context.get("p95_frame_time_ms")
    input_latency = context.get("input_latency_ms")

    if p95_frame and p95_frame > 50:
        return Alert(
            id=f"high-frame-latency-{context.get('host_name', 'unknown')}",
            severity=Severity.CRITICAL,
            title="Poor Frame Rendering Latency",
            description=f"P95 frame time at {p95_frame}ms — users will feel stutter and jank.",
            resource=context.get("host_name", "unknown"),
            metric="p95_frame_time_ms",
            value=p95_frame,
            threshold=50,
            impact="Direct degradation of user experience on expensive GPU hardware",
            recommendation="Investigate GPU load, driver, encoding settings, or right-size the workload.",
        )
    if input_latency and input_latency > 100:
        return Alert(
            id=f"high-input-latency-{context.get('host_name', 'unknown')}",
            severity=Severity.WARNING,
            title="High Input-to-Photon Latency",
            description=f"End-to-end input latency around {input_latency}ms.",
            resource=context.get("host_name", "unknown"),
            metric="input_latency_ms",
            value=input_latency,
            threshold=100,
            impact="Users feel the system is 'laggy' even if GPU util looks fine",
            recommendation="Check network path, AVD protocol settings, and encoding pipeline.",
        )
    return None


# =============================================================================
# Default Engine Factory
# =============================================================================

def create_default_alert_engine() -> AlertEngine:
    """Returns an AlertEngine pre-loaded with the most useful rules."""
    engine = AlertEngine()
    engine.add_rule(rule_high_gpu_utilization)
    engine.add_rule(rule_high_cost_burn)
    engine.add_rule(rule_severe_imbalance)
    engine.add_rule(rule_forecast_overrun)
    engine.add_rule(rule_high_latency)
    # Profile misconfiguration rules would be added here once we have real profile collectors
    return engine


# =============================================================================
# Email Notifications (when shit gets funky)
# =============================================================================

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def get_email_config() -> dict:
    """Pull email settings from environment (never hardcode secrets)."""
    return {
        "enabled": os.getenv("AVD_ALERT_EMAIL_ENABLED", "false").lower() == "true",
        "smtp_host": os.getenv("AVD_ALERT_SMTP_HOST", "localhost"),
        "smtp_port": int(os.getenv("AVD_ALERT_SMTP_PORT", "587")),
        "smtp_user": os.getenv("AVD_ALERT_SMTP_USER", ""),
        "smtp_pass": os.getenv("AVD_ALERT_SMTP_PASS", ""),
        "from_addr": os.getenv("AVD_ALERT_FROM", "avd-masters@yourcompany.com"),
        "to_addrs": os.getenv("AVD_ALERT_TO", "").split(",") if os.getenv("AVD_ALERT_TO") else [],
        "use_tls": os.getenv("AVD_ALERT_SMTP_TLS", "true").lower() == "true",
    }


def send_email_alert(
    subject: str,
    body_text: str,
    body_html: str | None = None,
    config: dict | None = None,
) -> bool:
    """
    Send a nicely formatted email alert.

    Returns True if sent successfully (or if email is disabled).
    """
    cfg = config or get_email_config()

    if not cfg["enabled"]:
        print("[Alert] Email disabled via AVD_ALERT_EMAIL_ENABLED=false")
        return False

    if not cfg["to_addrs"]:
        print("[Alert] No AVD_ALERT_TO configured. Skipping email.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg["from_addr"]
        msg["To"] = ", ".join(cfg["to_addrs"])

        msg.attach(MIMEText(body_text, "plain"))

        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
            if cfg["use_tls"]:
                server.starttls()
            if cfg["smtp_user"]:
                server.login(cfg["smtp_user"], cfg["smtp_pass"])
            server.sendmail(cfg["from_addr"], cfg["to_addrs"], msg.as_string())

        print(f"[Alert] Email sent: {subject}")
        return True

    except Exception as e:
        print(f"[Alert] Failed to send email: {e}")
        return False


def send_funky_gpu_email(
    title: str,
    summary: str,
    details: list[str],
    recommendations: list[str],
    impact: str | None = None,
    config: dict | None = None,
) -> bool:
    """
    Send a high-signal "shit is getting funky" email.

    This is the one you actually want in your inbox at 2am.
    """
    cfg = config or get_email_config()

    text_lines = [
        f"AVD MASTERS — FUNKY GPU SITUATION",
        f"Title: {title}",
        "",
        "SUMMARY:",
        summary,
        "",
        "DETAILS:",
    ]
    for d in details:
        text_lines.append(f"• {d}")
    text_lines.append("")
    text_lines.append("RECOMMENDED ACTIONS:")
    for r in recommendations:
        text_lines.append(f"→ {r}")
    if impact:
        text_lines.append("")
        text_lines.append(f"IMPACT: {impact}")

    text_body = "\n".join(text_lines)

    html_body = f"""
    <html>
      <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.5;">
        <h2 style="color: #c00;">AVD Masters — Funky GPU Situation</h2>
        <h3>{title}</h3>
        <p><strong>Summary:</strong> {summary}</p>
        <h4>Details</h4>
        <ul>
          {''.join(f'<li>{d}</li>' for d in details)}
        </ul>
        <h4>Recommended Actions</h4>
        <ul>
          {''.join(f'<li>{r}</li>' for r in recommendations)}
        </ul>
        {f'<p><strong>Impact:</strong> {impact}</p>' if impact else ''}
        <p style="color: #666; font-size: 0.9em;">Generated by AVD Masters. Go touch the gold.</p>
      </body>
    </html>
    """

    subject = f"[AVD Masters] {title}"
    return send_email_alert(subject, text_body, html_body, cfg)
