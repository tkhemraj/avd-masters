#!/usr/bin/env python3
"""Generate the VirtualDesktopMasters Grafana dashboard JSON.

Run: python grafana/dashboard_gen.py > grafana/vdm_dashboard.json
"""

import json

DS = {"type": "prometheus", "uid": "${datasource}"}

# Status 0=ok 1=warn 2=crit 3=unknown 4=offline
STATUS_MAPPINGS = [
    {
        "type": "value",
        "options": {
            "0": {"text": "OK",      "color": "green",     "index": 0},
            "1": {"text": "WARNING", "color": "yellow",    "index": 1},
            "2": {"text": "CRITICAL","color": "red",       "index": 2},
            "3": {"text": "UNKNOWN", "color": "text",      "index": 3},
            "4": {"text": "OFFLINE", "color": "dark-grey", "index": 4},
        },
    }
]

STATUS_THRESHOLDS = {
    "mode": "absolute",
    "steps": [
        {"color": "green",  "value": None},
        {"color": "yellow", "value": 1},
        {"color": "red",    "value": 2},
        {"color": "grey",   "value": 3},
    ],
}

PCT_THRESHOLDS = {
    "mode": "absolute",
    "steps": [
        {"color": "green",  "value": None},
        {"color": "yellow", "value": 75},
        {"color": "red",    "value": 90},
    ],
}

MEM_THRESHOLDS = {
    "mode": "absolute",
    "steps": [
        {"color": "green",  "value": None},
        {"color": "yellow", "value": 85},
        {"color": "red",    "value": 95},
    ],
}


# ── Panel builders ─────────────────────────────────────────────────────────

def stat(pid, title, expr, x, y, w=4, h=3,
         mappings=None, thresholds=None, unit="short", color_mode="background"):
    return {
        "id": pid, "type": "stat", "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": DS,
        "targets": [{"datasource": DS, "expr": expr, "instant": True,
                      "legendFormat": "", "refId": "A"}],
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "orientation": "auto",
            "colorMode": color_mode,
            "graphMode": "none",
            "justifyMode": "center",
            "textMode": "auto",
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "mappings": mappings or [],
                "thresholds": thresholds or {"mode": "absolute", "steps": [{"color": "green", "value": None}]},
                "color": {"mode": "thresholds"},
            },
            "overrides": [],
        },
    }


def timeseries(pid, title, targets, x, y, w=12, h=7,
               unit="short", thresholds=None, custom=None):
    return {
        "id": pid, "type": "timeseries", "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": DS,
        "targets": targets,
        "options": {
            "tooltip": {"mode": "multi", "sort": "desc"},
            "legend": {"displayMode": "table", "placement": "bottom",
                       "calcs": ["lastNotNull", "max", "mean"]},
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": custom or {
                    "lineWidth": 1,
                    "fillOpacity": 10,
                    "gradientMode": "none",
                    "showPoints": "never",
                    "spanNulls": True,
                },
                "thresholds": thresholds or {"mode": "absolute",
                                              "steps": [{"color": "green", "value": None}]},
                "color": {"mode": "palette-classic"},
            },
            "overrides": [],
        },
    }


def table(pid, title, targets, x, y, w=12, h=8,
          transforms=None, overrides=None):
    return {
        "id": pid, "type": "table", "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": DS,
        "targets": targets,
        "transformations": transforms or [],
        "options": {
            "sortBy": [],
            "footer": {"show": False},
        },
        "fieldConfig": {
            "defaults": {
                "custom": {
                    "align": "auto",
                    "displayMode": "auto",
                    "filterable": True,
                    "width": 0,
                },
            },
            "overrides": overrides or [],
        },
    }


def gauge(pid, title, expr, x, y, w=5, h=8,
          unit="percent", min_val=0, max_val=100, thresholds=None):
    return {
        "id": pid, "type": "gauge", "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": DS,
        "targets": [{"datasource": DS, "expr": expr, "instant": True,
                      "legendFormat": "{{server}}", "refId": "A"}],
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "showThresholdLabels": False,
            "showThresholdMarkers": True,
            "orientation": "auto",
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "min": min_val,
                "max": max_val,
                "thresholds": thresholds or MEM_THRESHOLDS,
                "color": {"mode": "thresholds"},
            },
            "overrides": [],
        },
    }


def row_panel(pid, title, y, collapsed=False):
    return {
        "id": pid, "type": "row", "title": title,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
        "collapsed": collapsed,
        "panels": [],
    }


def ts_target(expr, legend, ref):
    return {"datasource": DS, "expr": expr,
            "legendFormat": legend, "refId": ref}


def instant_target(expr, ref, fmt="table"):
    return {"datasource": DS, "expr": expr, "instant": True,
            "format": fmt, "refId": ref, "legendFormat": "__auto"}


# ── Status table overrides ─────────────────────────────────────────────────

def status_override(field_name):
    return {
        "matcher": {"id": "byName", "options": field_name},
        "properties": [
            {"id": "mappings", "value": STATUS_MAPPINGS},
            {"id": "thresholds", "value": STATUS_THRESHOLDS},
            {"id": "custom.displayMode", "value": "color-background"},
            {"id": "color", "value": {"mode": "thresholds"}},
            {"id": "custom.width", "value": 110},
        ],
    }


def pct_override(field_name, warn=75, crit=90):
    return {
        "matcher": {"id": "byName", "options": field_name},
        "properties": [
            {"id": "unit", "value": "percent"},
            {"id": "custom.displayMode", "value": "color-background"},
            {"id": "thresholds", "value": {
                "mode": "absolute",
                "steps": [
                    {"color": "green", "value": None},
                    {"color": "yellow", "value": warn},
                    {"color": "red",    "value": crit},
                ],
            }},
            {"id": "color", "value": {"mode": "thresholds"}},
            {"id": "custom.width", "value": 90},
        ],
    }


# ── Merge transform helper ─────────────────────────────────────────────────

def merge_transform(renames: dict, excludes: list[str] | None = None):
    exclude_map = {k: True for k in (excludes or ["Time", "__name__", "job", "instance"])}
    return [
        {"id": "merge", "options": {}},
        {
            "id": "organize",
            "options": {
                "renameByName": renames,
                "excludeByName": exclude_map,
                "indexByName": {},
            },
        },
    ]


# ── Build dashboard ────────────────────────────────────────────────────────

def build():
    panels = []
    pid = 1

    # ── Summary row ─────────────────────────────────────────────────────────
    y = 0

    panels.append(stat(
        pid, "AVD Status",
        'vdm_overall_status{platform="avd"}',
        x=0, y=y, w=4, h=3,
        mappings=STATUS_MAPPINGS, thresholds=STATUS_THRESHOLDS,
    ))
    pid += 1

    panels.append(stat(
        pid, "RDS Status",
        'vdm_overall_status{platform="rds"}',
        x=4, y=y, w=4, h=3,
        mappings=STATUS_MAPPINGS, thresholds=STATUS_THRESHOLDS,
    ))
    pid += 1

    panels.append(stat(
        pid, "Citrix Status",
        'vdm_overall_status{platform="citrix"}',
        x=8, y=y, w=4, h=3,
        mappings=STATUS_MAPPINGS, thresholds=STATUS_THRESHOLDS,
    ))
    pid += 1

    panels.append(stat(
        pid, "Total Active Sessions",
        (
            "sum(avd_host_pool_active_sessions) or vector(0)"
            " + sum(rds_session_host_active_sessions) or vector(0)"
            " + sum(citrix_delivery_group_active_sessions) or vector(0)"
        ),
        x=12, y=y, w=6, h=3,
        thresholds={"mode": "absolute", "steps": [{"color": "blue", "value": None}]},
        color_mode="none",
    ))
    pid += 1

    panels.append(stat(
        pid, "Collection Errors (24h)",
        "increase(vdm_collection_errors_total[24h])",
        x=18, y=y, w=6, h=3,
        thresholds={
            "mode": "absolute",
            "steps": [
                {"color": "green", "value": None},
                {"color": "yellow", "value": 1},
                {"color": "red",    "value": 5},
            ],
        },
    ))
    pid += 1

    # ── AVD Row ─────────────────────────────────────────────────────────────
    y = 3
    panels.append(row_panel(pid, "Azure Virtual Desktop", y))
    pid += 1
    y += 1  # row header takes 1 unit

    # Host Pool table
    panels.append(table(
        pid, "Host Pools",
        targets=[
            instant_target("avd_host_pool_status",               "A"),
            instant_target("avd_host_pool_active_sessions",      "B"),
            instant_target("avd_host_pool_disconnected_sessions","C"),
            instant_target("avd_host_pool_available_hosts",      "D"),
            instant_target("avd_host_pool_total_hosts",          "E"),
        ],
        x=0, y=y, w=12, h=8,
        transforms=merge_transform(
            {
                "Value #A": "Status",
                "Value #B": "Active Sessions",
                "Value #C": "Disconnected",
                "Value #D": "Available Hosts",
                "Value #E": "Total Hosts",
                "host_pool": "Host Pool",
                "resource_group": "Resource Group",
            },
            excludes=["Time", "__name__", "job", "instance"],
        ),
        overrides=[
            status_override("Status"),
            {
                "matcher": {"id": "byName", "options": "Active Sessions"},
                "properties": [{"id": "custom.width", "value": 115}],
            },
        ],
    ))
    pid += 1

    # Active sessions per pool time series
    panels.append(timeseries(
        pid, "Active Sessions per Host Pool",
        targets=[
            ts_target("avd_host_pool_active_sessions",      "{{host_pool}} active",      "A"),
            ts_target("avd_host_pool_disconnected_sessions","{{host_pool}} disconnected", "B"),
        ],
        x=12, y=y, w=12, h=8,
        unit="short",
    ))
    pid += 1
    y += 8

    # Session host CPU
    panels.append(timeseries(
        pid, "Session Host CPU %",
        targets=[ts_target(
            "avd_session_host_cpu_percent",
            "{{host_pool}} / {{host}}", "A",
        )],
        x=0, y=y, w=12, h=7,
        unit="percent",
        thresholds=PCT_THRESHOLDS,
    ))
    pid += 1

    # Session host Memory
    panels.append(timeseries(
        pid, "Session Host Memory %",
        targets=[ts_target(
            "avd_session_host_memory_percent",
            "{{host_pool}} / {{host}}", "A",
        )],
        x=12, y=y, w=12, h=7,
        unit="percent",
        thresholds=MEM_THRESHOLDS,
    ))
    pid += 1
    y += 7

    # Session host detail table
    panels.append(table(
        pid, "Session Host Details",
        targets=[
            instant_target("avd_session_host_status",           "A"),
            instant_target("avd_session_host_sessions",          "B"),
            instant_target("avd_session_host_allow_new_sessions","C"),
            instant_target("avd_session_host_cpu_percent",       "D"),
            instant_target("avd_session_host_memory_percent",    "E"),
        ],
        x=0, y=y, w=24, h=7,
        transforms=merge_transform(
            {
                "Value #A": "Status",
                "Value #B": "Sessions",
                "Value #C": "Accepts New",
                "Value #D": "CPU %",
                "Value #E": "Memory %",
                "host_pool": "Host Pool",
                "host": "Host",
            },
            excludes=["Time", "__name__", "job", "instance"],
        ),
        overrides=[
            status_override("Status"),
            pct_override("CPU %",    75, 90),
            pct_override("Memory %", 85, 95),
            {
                "matcher": {"id": "byName", "options": "Accepts New"},
                "properties": [
                    {"id": "mappings", "value": [
                        {"type": "value", "options": {
                            "1": {"text": "Yes", "color": "green",  "index": 0},
                            "0": {"text": "No",  "color": "orange", "index": 1},
                        }},
                    ]},
                    {"id": "custom.displayMode", "value": "color-text"},
                    {"id": "custom.width", "value": 100},
                ],
            },
        ],
    ))
    pid += 1
    y += 7

    # ── RDS Row ─────────────────────────────────────────────────────────────
    panels.append(row_panel(pid, "Terminal Services (RDS)", y))
    pid += 1
    y += 1

    # Session hosts table
    panels.append(table(
        pid, "Session Hosts",
        targets=[
            instant_target("rds_session_host_status",               "A"),
            instant_target("rds_session_host_active_sessions",      "B"),
            instant_target("rds_session_host_disconnected_sessions","C"),
            instant_target("rds_session_host_cpu_percent",           "D"),
            instant_target("rds_session_host_memory_percent",        "E"),
            instant_target("rds_session_host_disk_percent",          "F"),
            instant_target("rds_session_host_uptime_hours",          "G"),
        ],
        x=0, y=y, w=14, h=8,
        transforms=merge_transform(
            {
                "Value #A": "Status",
                "Value #B": "Active",
                "Value #C": "Disc.",
                "Value #D": "CPU %",
                "Value #E": "Memory %",
                "Value #F": "Disk %",
                "Value #G": "Uptime (h)",
                "farm": "Farm",
                "host": "Host",
            },
            excludes=["Time", "__name__", "job", "instance"],
        ),
        overrides=[
            status_override("Status"),
            pct_override("CPU %",    75, 90),
            pct_override("Memory %", 85, 95),
            pct_override("Disk %",   80, 95),
        ],
    ))
    pid += 1

    # License gauge
    panels.append(gauge(
        pid, "CAL Utilisation",
        "rds_license_utilization_percent",
        x=14, y=y, w=5, h=8,
        unit="percent",
        thresholds={
            "mode": "absolute",
            "steps": [
                {"color": "green",  "value": None},
                {"color": "yellow", "value": 80},
                {"color": "red",    "value": 95},
            ],
        },
    ))
    pid += 1

    # CAL stats
    cal_stat = stat(
        pid, "CALs Used / Total",
        "rds_license_cals_used",
        x=19, y=y, w=5, h=4,
        thresholds={
            "mode": "absolute",
            "steps": [
                {"color": "green",  "value": None},
                {"color": "yellow", "value": 80},
                {"color": "red",    "value": 95},
            ],
        },
        unit="short",
        color_mode="none",
    )
    panels.append(cal_stat)
    pid += 1

    cal_avail = stat(
        pid, "CALs Available",
        "rds_license_cals_available",
        x=19, y=y + 4, w=5, h=4,
        thresholds={
            "mode": "absolute",
            "steps": [
                {"color": "red",    "value": None},
                {"color": "yellow", "value": 10},
                {"color": "green",  "value": 20},
            ],
        },
        unit="short",
    )
    panels.append(cal_avail)
    pid += 1
    y += 8

    # RDS CPU
    panels.append(timeseries(
        pid, "Session Host CPU %",
        targets=[ts_target("rds_session_host_cpu_percent", "{{host}}", "A")],
        x=0, y=y, w=12, h=7,
        unit="percent", thresholds=PCT_THRESHOLDS,
    ))
    pid += 1

    # RDS Memory
    panels.append(timeseries(
        pid, "Session Host Memory %",
        targets=[ts_target("rds_session_host_memory_percent", "{{host}}", "A")],
        x=12, y=y, w=12, h=7,
        unit="percent", thresholds=MEM_THRESHOLDS,
    ))
    pid += 1
    y += 7

    # RDS active sessions
    panels.append(timeseries(
        pid, "Sessions per Host",
        targets=[
            ts_target("rds_session_host_active_sessions",       "{{host}} active",      "A"),
            ts_target("rds_session_host_disconnected_sessions", "{{host}} disconnected", "B"),
        ],
        x=0, y=y, w=12, h=7,
    ))
    pid += 1

    # RDS broker + license trend
    panels.append(timeseries(
        pid, "License CAL Usage Trend",
        targets=[
            ts_target("rds_license_cals_used",      "Used",      "A"),
            ts_target("rds_license_cals_total",     "Total",     "B"),
            ts_target("rds_license_cals_available", "Available", "C"),
        ],
        x=12, y=y, w=12, h=7,
        unit="short",
    ))
    pid += 1
    y += 7

    # ── Citrix Row ───────────────────────────────────────────────────────────
    panels.append(row_panel(pid, "Citrix VDI", y))
    pid += 1
    y += 1

    # Delivery groups table
    panels.append(table(
        pid, "Delivery Groups",
        targets=[
            instant_target("citrix_delivery_group_status",               "A"),
            instant_target("citrix_delivery_group_total_machines",       "B"),
            instant_target("citrix_delivery_group_registered_machines",  "C"),
            instant_target("citrix_delivery_group_active_sessions",      "D"),
            instant_target("citrix_delivery_group_disconnected_sessions","E"),
        ],
        x=0, y=y, w=14, h=8,
        transforms=merge_transform(
            {
                "Value #A": "Status",
                "Value #B": "Total VDAs",
                "Value #C": "Registered",
                "Value #D": "Active Sessions",
                "Value #E": "Disconnected",
                "site": "Site",
                "delivery_group": "Delivery Group",
            },
            excludes=["Time", "__name__", "job", "instance"],
        ),
        overrides=[
            status_override("Status"),
            {
                "matcher": {"id": "byName", "options": "Registered"},
                "properties": [
                    {"id": "custom.displayMode", "value": "color-background"},
                    {"id": "thresholds", "value": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "red",   "value": None},
                            {"color": "green", "value": 100},
                        ],
                    }},
                    {"id": "color", "value": {"mode": "thresholds"}},
                ],
            },
        ],
    ))
    pid += 1

    # Unregistered VDAs bar gauge
    panels.append({
        "id": pid, "type": "bargauge", "title": "Unregistered VDAs per Delivery Group",
        "gridPos": {"x": 14, "y": y, "w": 10, "h": 8},
        "datasource": DS,
        "targets": [{
            "datasource": DS,
            "expr": (
                "citrix_delivery_group_total_machines"
                " - citrix_delivery_group_registered_machines"
            ),
            "instant": True,
            "legendFormat": "{{delivery_group}}",
            "refId": "A",
        }],
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "orientation": "horizontal",
            "displayMode": "gradient",
            "valueMode": "color",
            "showUnfilled": True,
            "minVizWidth": 0,
            "minVizHeight": 16,
        },
        "fieldConfig": {
            "defaults": {
                "unit": "short",
                "min": 0,
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "green",  "value": None},
                        {"color": "yellow", "value": 1},
                        {"color": "red",    "value": 3},
                    ],
                },
                "color": {"mode": "thresholds"},
            },
            "overrides": [],
        },
    })
    pid += 1
    y += 8

    # Citrix sessions time series
    panels.append(timeseries(
        pid, "Sessions per Delivery Group",
        targets=[
            ts_target("citrix_delivery_group_active_sessions",       "{{delivery_group}} active",      "A"),
            ts_target("citrix_delivery_group_disconnected_sessions",  "{{delivery_group}} disconnected","B"),
        ],
        x=0, y=y, w=12, h=7,
    ))
    pid += 1

    # Controllers table
    panels.append(table(
        pid, "Delivery Controllers",
        targets=[instant_target("citrix_controller_status", "A")],
        x=12, y=y, w=12, h=7,
        transforms=merge_transform(
            {
                "Value #A": "Status",
                "site": "Site",
                "controller": "Controller",
            },
            excludes=["Time", "__name__", "job", "instance"],
        ),
        overrides=[status_override("Status")],
    ))
    pid += 1

    # ── Assemble dashboard ───────────────────────────────────────────────────
    return {
        "uid": "vdm-v1",
        "title": "VirtualDesktopMasters",
        "description": "Unified monitoring for Azure Virtual Desktop, RDS Terminal Services, and Citrix VDI",
        "tags": ["avd", "rds", "citrix", "vdi", "monitoring"],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "refresh": "1m",
        "time": {"from": "now-3h", "to": "now"},
        "timepicker": {},
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "panels": panels,
        "templating": {
            "list": [
                {
                    "name": "datasource",
                    "type": "datasource",
                    "label": "Prometheus",
                    "query": "prometheus",
                    "current": {},
                    "hide": 0,
                    "includeAll": False,
                    "multi": False,
                    "options": [],
                    "pluginId": "prometheus",
                    "refresh": 1,
                    "regex": "",
                    "sort": 1,
                },
            ]
        },
        "annotations": {
            "list": [
                {
                    "builtIn": 1,
                    "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                    "enable": True,
                    "hide": True,
                    "iconColor": "rgba(0, 211, 255, 1)",
                    "name": "Annotations & Alerts",
                    "type": "dashboard",
                }
            ]
        },
        "links": [],
        "liveNow": False,
        "preload": False,
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
