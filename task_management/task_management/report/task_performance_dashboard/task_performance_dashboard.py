import frappe
from frappe import _
from frappe.utils import getdate, today, date_diff


def execute(filters=None):
    filters = filters or {}
    data = get_task_data(filters)
    stats = compute_stats(data)
    trend = compute_trend(filters)
    by_employee = compute_by_employee(data)
    by_priority = compute_by_priority(data)
    by_category = compute_by_category(data)
    by_dept = compute_by_department(data)

    html = build_dashboard_html(stats, trend, by_employee, by_priority, by_category, by_dept, filters)

    columns = [{"fieldname": "dashboard", "fieldtype": "HTML", "label": "Dashboard", "width": 1200}]
    rows = [{"dashboard": html}]
    return columns, rows


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def get_task_data(filters):
    conditions = "WHERE t.docstatus != 2"  # exclude cancelled
    args = {}

    if filters.get("from_date"):
        conditions += " AND t.start_date >= %(from_date)s"
        args["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions += " AND t.start_date <= %(to_date)s"
        args["to_date"] = filters["to_date"]
    if filters.get("department"):
        conditions += " AND t.assigned_to_department = %(department)s"
        args["department"] = filters["department"]
    if filters.get("employee"):
        conditions += " AND t.assigned_to = %(employee)s"
        args["employee"] = filters["employee"]
    if filters.get("status"):
        if filters["status"] == "Completed":
            conditions += " AND t.status = 'Completed' AND t.docstatus = 1"
        elif filters["status"] == "Open":
            conditions += " AND t.status IN ('Open','In Progress','Pending Review') AND t.docstatus = 1"
        else:
            conditions += " AND t.status = %(status)s"
            args["status"] = filters["status"]
    if filters.get("priority"):
        conditions += " AND t.priority = %(priority)s"
        args["priority"] = filters["priority"]
    if filters.get("category"):
        conditions += " AND t.category = %(category)s"
        args["category"] = filters["category"]

    # Apply permission-based scoping
    user = frappe.session.user
    roles = frappe.get_roles(user)
    if user != "Administrator" and "System Manager" not in roles:
        emp = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
        if "Task General Manager" in roles and emp:
            dept = frappe.db.get_value("Employee", emp, "department")
            if dept:
                conditions += f" AND t.assigned_to_department = '{dept}'"
        elif "Task Manager" in roles and emp:
            conditions += f" AND t.assigned_by = '{emp}'"
        elif emp:
            conditions += f" AND t.assigned_to = '{emp}'"

    return frappe.db.sql(f"""
        SELECT
            t.name, t.task_title, t.status, t.priority, t.category,
            t.assigned_to, t.assigned_to_name, t.assigned_to_department,
            t.assigned_by_name, t.start_date, t.due_date, t.completed_on,
            t.on_time, t.is_overdue, t.overdue_days, t.days_to_complete,
            t.allocated_days, t.quality_score, t.docstatus,
            t.completion_percentage
        FROM `tabEmployee Task` t
        {conditions}
        ORDER BY t.start_date DESC
    """, args, as_dict=1)


def compute_stats(data):
    total = len(data)
    # Completed = submitted (docstatus=1) AND status=Completed
    completed = [t for t in data if t.docstatus == 1 and t.status == "Completed"]
    # Open = submitted but not yet completed
    open_tasks = [t for t in data if t.docstatus == 1 and t.status in ("Open", "In Progress", "Pending Review")]
    # Draft = not yet submitted
    draft = [t for t in data if t.docstatus == 0]
    on_time = [t for t in completed if t.on_time]
    delayed = [t for t in completed if not t.on_time]
    overdue = [t for t in data if t.is_overdue and t.status != "Completed"]
    in_progress = [t for t in data if t.status == "In Progress"]

    on_time_rate = round(len(on_time) / len(completed) * 100, 1) if completed else 0
    completion_rate = round(len(completed) / total * 100, 1) if total else 0

    avg_days = round(
        sum(t.days_to_complete or 0 for t in completed) / len(completed), 1
    ) if completed else 0

    avg_overdue_days = round(
        sum(t.overdue_days or 0 for t in overdue) / len(overdue), 1
    ) if overdue else 0

    return {
        "total": total,
        "completed": len(completed),
        "on_time": len(on_time),
        "delayed": len(delayed),
        "overdue": len(overdue),
        "in_progress": len(in_progress),
        "open": len(open_tasks),
        "draft": len(draft),
        "on_time_rate": on_time_rate,
        "completion_rate": completion_rate,
        "avg_days": avg_days,
        "avg_overdue_days": avg_overdue_days,
    }


def compute_trend(filters):
    """Monthly task counts for trend chart (last 6 months or filtered range)."""
    conditions = "WHERE t.docstatus != 2"
    args = {}
    if filters.get("from_date"):
        conditions += " AND t.start_date >= %(from_date)s"
        args["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions += " AND t.start_date <= %(to_date)s"
        args["to_date"] = filters["to_date"]
    if filters.get("department"):
        conditions += " AND t.assigned_to_department = %(department)s"
        args["department"] = filters["department"]
    if filters.get("employee"):
        conditions += " AND t.assigned_to = %(employee)s"
        args["employee"] = filters["employee"]

    rows = frappe.db.sql(f"""
        SELECT
            DATE_FORMAT(t.start_date, '%%Y-%%m') AS month,
            COUNT(*) AS total,
            SUM(CASE WHEN t.docstatus=1 THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN t.docstatus=1 AND t.on_time=1 THEN 1 ELSE 0 END) AS on_time,
            SUM(CASE WHEN t.is_overdue=1 AND t.docstatus=0 THEN 1 ELSE 0 END) AS overdue
        FROM `tabEmployee Task` t
        {conditions}
        GROUP BY DATE_FORMAT(t.start_date, '%%Y-%%m')
        ORDER BY month DESC
        LIMIT 6
    """, args, as_dict=1)
    return list(reversed(rows))


def compute_by_employee(data):
    from collections import defaultdict
    emp = defaultdict(lambda: {"name": "", "dept": "", "total": 0, "completed": 0,
                                "on_time": 0, "delayed": 0, "overdue": 0})
    for t in data:
        e = t.assigned_to or "Unknown"
        emp[e]["name"] = t.assigned_to_name or e
        emp[e]["dept"] = t.assigned_to_department or ""
        emp[e]["total"] += 1
        if t.docstatus == 1 and t.status == "Completed":
            emp[e]["completed"] += 1
            if t.on_time:
                emp[e]["on_time"] += 1
            else:
                emp[e]["delayed"] += 1
        elif t.is_overdue and t.status != "Completed":
            emp[e]["overdue"] += 1
    result = sorted(emp.values(), key=lambda x: x["total"], reverse=True)
    return result[:15]  # top 15


def compute_by_priority(data):
    from collections import defaultdict
    pri = defaultdict(lambda: {"total": 0, "completed": 0, "on_time": 0, "overdue": 0})
    for t in data:
        p = t.priority or "Medium"
        pri[p]["total"] += 1
        if t.docstatus == 1 and t.status == "Completed":
            pri[p]["completed"] += 1
            if t.on_time:
                pri[p]["on_time"] += 1
        elif t.is_overdue and t.status != "Completed":
            pri[p]["overdue"] += 1
    order = ["Critical", "High", "Medium", "Low"]
    return [{"priority": p, **pri[p]} for p in order if p in pri]


def compute_by_category(data):
    from collections import defaultdict
    cat = defaultdict(lambda: {"total": 0, "completed": 0})
    for t in data:
        c = t.category or "Uncategorized"
        cat[c]["total"] += 1
        if t.docstatus == 1 and t.status == "Completed":
            cat[c]["completed"] += 1
    return sorted([{"category": k, **v} for k, v in cat.items()],
                  key=lambda x: x["total"], reverse=True)[:8]


def compute_by_department(data):
    from collections import defaultdict
    dept = defaultdict(lambda: {"total": 0, "completed": 0, "on_time": 0, "overdue": 0})
    for t in data:
        d = t.assigned_to_department or "Unknown"
        dept[d]["total"] += 1
        if t.docstatus == 1 and t.status == "Completed":
            dept[d]["completed"] += 1
            if t.on_time:
                dept[d]["on_time"] += 1
        elif t.is_overdue and t.status != "Completed":
            dept[d]["overdue"] += 1
    return sorted([{"dept": k, **v} for k, v in dept.items()],
                  key=lambda x: x["total"], reverse=True)


# ---------------------------------------------------------------------------
# HTML Dashboard Builder
# ---------------------------------------------------------------------------

def build_dashboard_html(stats, trend, by_employee, by_priority, by_category, by_dept, filters):
    # Format filter summary
    filter_parts = []
    if filters.get("from_date") and filters.get("to_date"):
        filter_parts.append(f"📅 {filters['from_date']} → {filters['to_date']}")
    if filters.get("department"):
        filter_parts.append(f"🏢 {filters['department']}")
    if filters.get("employee"):
        filter_parts.append(f"👤 {filters['employee']}")
    if filters.get("priority"):
        filter_parts.append(f"⚡ {filters['priority']}")
    if filters.get("status"):
        filter_parts.append(f"📌 {filters['status']}")
    if filters.get("category"):
        filter_parts.append(f"🏷️ {filters['category']}")
    filter_text = "  |  ".join(filter_parts) if filter_parts else "All Tasks"

    # Trend chart data for inline JS
    trend_labels = [r.month for r in trend]
    trend_total = [r.total for r in trend]
    trend_completed = [r.completed for r in trend]
    trend_overdue = [r.overdue for r in trend]

    # Priority badge colors
    pri_colors = {"Critical": "#c62828", "High": "#e65100", "Medium": "#1565C0", "Low": "#2e7d32"}
    pri_bg = {"Critical": "#ffebee", "High": "#fff3e0", "Medium": "#e3f2fd", "Low": "#e8f5e9"}

    # Employee table rows
    emp_rows = ""
    for i, e in enumerate(by_employee):
        rate = round(e["completed"] / e["total"] * 100) if e["total"] else 0
        bar_color = "#2e7d32" if rate >= 75 else "#f57c00" if rate >= 50 else "#c62828"
        emp_rows += f"""
        <tr style="border-bottom:1px solid #f0f0f0">
            <td style="padding:10px 12px;font-weight:500">{e['name']}</td>
            <td style="padding:10px 12px;color:#666;font-size:12px">{e['dept']}</td>
            <td style="padding:10px 12px;text-align:center">{e['total']}</td>
            <td style="padding:10px 12px;text-align:center;color:#2e7d32;font-weight:600">{e['completed']}</td>
            <td style="padding:10px 12px;text-align:center;color:#1565C0">{e['on_time']}</td>
            <td style="padding:10px 12px;text-align:center;color:#c62828">{e['overdue']}</td>
            <td style="padding:10px 12px;min-width:120px">
                <div style="display:flex;align-items:center;gap:8px">
                    <div style="flex:1;background:#f0f0f0;border-radius:4px;height:8px;overflow:hidden">
                        <div style="width:{rate}%;background:{bar_color};height:100%;border-radius:4px"></div>
                    </div>
                    <span style="font-size:12px;font-weight:600;color:{bar_color};min-width:32px">{rate}%</span>
                </div>
            </td>
        </tr>"""

    # Priority rows
    pri_rows = ""
    for p in by_priority:
        rate = round(p["completed"] / p["total"] * 100) if p["total"] else 0
        c = pri_colors.get(p["priority"], "#555")
        bg = pri_bg.get(p["priority"], "#f5f5f5")
        pri_rows += f"""
        <tr style="border-bottom:1px solid #f0f0f0">
            <td style="padding:10px 14px">
                <span style="background:{bg};color:{c};padding:3px 10px;border-radius:12px;
                    font-size:12px;font-weight:700">{p['priority']}</span>
            </td>
            <td style="padding:10px 14px;text-align:center">{p['total']}</td>
            <td style="padding:10px 14px;text-align:center;color:#2e7d32;font-weight:600">{p['completed']}</td>
            <td style="padding:10px 14px;text-align:center;color:#1565C0">{p['on_time']}</td>
            <td style="padding:10px 14px;text-align:center;color:#c62828">{p['overdue']}</td>
            <td style="padding:10px 14px;text-align:center;font-weight:700;
                color:{('#2e7d32' if rate>=75 else '#f57c00' if rate>=50 else '#c62828')}">{rate}%</td>
        </tr>"""

    # Category rows
    cat_rows = ""
    for c in by_category:
        rate = round(c["completed"] / c["total"] * 100) if c["total"] else 0
        cat_rows += f"""
        <tr style="border-bottom:1px solid #f0f0f0">
            <td style="padding:10px 14px;font-weight:500">{c['category']}</td>
            <td style="padding:10px 14px;text-align:center">{c['total']}</td>
            <td style="padding:10px 14px;text-align:center;color:#2e7d32;font-weight:600">{c['completed']}</td>
            <td style="padding:10px 14px;text-align:center;font-weight:700;
                color:{('#2e7d32' if rate>=75 else '#f57c00' if rate>=50 else '#c62828')}">{rate}%</td>
        </tr>"""

    # Department rows
    dept_rows = ""
    for d in by_dept:
        rate = round(d["completed"] / d["total"] * 100) if d["total"] else 0
        dept_rows += f"""
        <tr style="border-bottom:1px solid #f0f0f0">
            <td style="padding:10px 14px;font-weight:500">{d['dept']}</td>
            <td style="padding:10px 14px;text-align:center">{d['total']}</td>
            <td style="padding:10px 14px;text-align:center;color:#2e7d32;font-weight:600">{d['completed']}</td>
            <td style="padding:10px 14px;text-align:center;color:#1565C0">{d['on_time']}</td>
            <td style="padding:10px 14px;text-align:center;color:#c62828">{d['overdue']}</td>
            <td style="padding:10px 14px;text-align:center;font-weight:700;
                color:{('#2e7d32' if rate>=75 else '#f57c00' if rate>=50 else '#c62828')}">{rate}%</td>
        </tr>"""

    on_time_color = "#2e7d32" if stats["on_time_rate"] >= 75 else "#f57c00" if stats["on_time_rate"] >= 50 else "#c62828"
    comp_color = "#2e7d32" if stats["completion_rate"] >= 75 else "#f57c00" if stats["completion_rate"] >= 50 else "#c62828"

    return f"""
<style>
    .tm-dash {{
        font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        padding: 4px 8px 32px;
        max-width: 1400px;
        color: #1a1a2e;
    }}
    .tm-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 24px;
        padding-bottom: 16px;
        border-bottom: 2px solid #e8edf2;
    }}
    .tm-title {{
        font-size: 22px;
        font-weight: 700;
        color: #1a1a2e;
        letter-spacing: -0.5px;
    }}
    .tm-subtitle {{
        font-size: 12px;
        color: #888;
        margin-top: 3px;
    }}
    .tm-filter-badge {{
        background: #f0f4ff;
        border: 1px solid #c5d3f0;
        color: #3b5bdb;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 500;
    }}
    .tm-kpi-grid {{
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 12px;
        margin-bottom: 24px;
    }}
    .tm-kpi {{
        background: #fff;
        border: 1px solid #e8edf2;
        border-radius: 10px;
        padding: 16px 14px;
        position: relative;
        overflow: hidden;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        transition: transform 0.15s, box-shadow 0.15s;
    }}
    .tm-kpi:hover {{
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }}
    .tm-kpi-accent {{
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        border-radius: 10px 10px 0 0;
    }}
    .tm-kpi-label {{
        font-size: 11px;
        color: #888;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }}
    .tm-kpi-value {{
        font-size: 28px;
        font-weight: 800;
        line-height: 1;
        letter-spacing: -1px;
    }}
    .tm-kpi-sub {{
        font-size: 11px;
        color: #aaa;
        margin-top: 5px;
    }}
    .tm-row {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
        margin-bottom: 16px;
    }}
    .tm-row-3 {{
        display: grid;
        grid-template-columns: 2fr 1fr 1fr;
        gap: 16px;
        margin-bottom: 16px;
    }}
    .tm-card {{
        background: #fff;
        border: 1px solid #e8edf2;
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }}
    .tm-card-header {{
        padding: 14px 18px 12px;
        border-bottom: 1px solid #f0f0f0;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }}
    .tm-card-title {{
        font-size: 13px;
        font-weight: 700;
        color: #333;
        text-transform: uppercase;
        letter-spacing: 0.4px;
    }}
    .tm-card-badge {{
        font-size: 11px;
        background: #f0f4ff;
        color: #3b5bdb;
        padding: 2px 10px;
        border-radius: 10px;
        font-weight: 600;
    }}
    .tm-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
    }}
    .tm-table th {{
        padding: 10px 12px;
        text-align: left;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.4px;
        color: #888;
        background: #fafbfc;
        border-bottom: 1px solid #eee;
    }}
    .tm-table th.center {{ text-align: center; }}
    .tm-table tr:last-child td {{ border-bottom: none; }}
    .tm-donut-wrap {{
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 24px;
        padding: 20px 18px;
    }}
    .tm-legend {{
        display: flex;
        flex-direction: column;
        gap: 8px;
        min-width: 140px;
    }}
    .tm-legend-item {{
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 12px;
    }}
    .tm-legend-dot {{
        width: 10px; height: 10px;
        border-radius: 50%;
        flex-shrink: 0;
    }}
    .tm-bar-chart {{
        padding: 16px 18px;
    }}
    .tm-bar-row {{
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 10px;
        font-size: 12px;
    }}
    .tm-bar-label {{
        min-width: 80px;
        text-align: right;
        color: #555;
        font-weight: 500;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}
    .tm-bar-track {{
        flex: 1;
        background: #f0f0f0;
        border-radius: 4px;
        height: 20px;
        overflow: hidden;
        position: relative;
    }}
    .tm-bar-fill {{
        height: 100%;
        border-radius: 4px;
        display: flex;
        align-items: center;
        padding-left: 8px;
        font-size: 11px;
        font-weight: 700;
        color: #fff;
        min-width: 30px;
        transition: width 0.6s ease;
    }}
    .tm-trend {{
        padding: 16px 18px;
    }}
    .tm-canvas-wrap {{
        position: relative;
        height: 160px;
    }}
    @media (max-width: 900px) {{
        .tm-kpi-grid {{ grid-template-columns: repeat(4, 1fr); }}
        .tm-row, .tm-row-3 {{ grid-template-columns: 1fr; }}
    }}
</style>

<div class="tm-dash">
    <!-- Header -->
    <div class="tm-header">
        <div>
            <div class="tm-title">📋 Task Performance Dashboard</div>
            <div class="tm-subtitle">Real-time overview · Balanced Scorecard KPI</div>
        </div>
        <div class="tm-filter-badge">🔍 {filter_text}</div>
    </div>

    <!-- KPI Cards Row -->
    <div class="tm-kpi-grid">
        <div class="tm-kpi">
            <div class="tm-kpi-accent" style="background:#3b5bdb"></div>
            <div class="tm-kpi-label">Total Active</div>
            <div class="tm-kpi-value" style="color:#3b5bdb">{stats['total']}</div>
            <div class="tm-kpi-sub">All non-cancelled tasks</div>
        </div>
        <div class="tm-kpi">
            <div class="tm-kpi-accent" style="background:#2e7d32"></div>
            <div class="tm-kpi-label">Completed</div>
            <div class="tm-kpi-value" style="color:#2e7d32">{stats['completed']}</div>
            <div class="tm-kpi-sub">Submitted &amp; locked</div>
        </div>
        <div class="tm-kpi">
            <div class="tm-kpi-accent" style="background:#1565C0"></div>
            <div class="tm-kpi-label">On Time</div>
            <div class="tm-kpi-value" style="color:#1565C0">{stats['on_time']}</div>
            <div class="tm-kpi-sub">Of completed tasks</div>
        </div>
        <div class="tm-kpi">
            <div class="tm-kpi-accent" style="background:{on_time_color}"></div>
            <div class="tm-kpi-label">On-Time Rate</div>
            <div class="tm-kpi-value" style="color:{on_time_color}">{stats['on_time_rate']}%</div>
            <div class="tm-kpi-sub">On-time / completed</div>
        </div>
        <div class="tm-kpi">
            <div class="tm-kpi-accent" style="background:#e65100"></div>
            <div class="tm-kpi-label">Delayed</div>
            <div class="tm-kpi-value" style="color:#e65100">{stats['delayed']}</div>
            <div class="tm-kpi-sub">Completed late</div>
        </div>
        <div class="tm-kpi">
            <div class="tm-kpi-accent" style="background:#c62828"></div>
            <div class="tm-kpi-label">Overdue</div>
            <div class="tm-kpi-value" style="color:#c62828">{stats['overdue']}</div>
            <div class="tm-kpi-sub">Past due, not done</div>
        </div>
        <div class="tm-kpi">
            <div class="tm-kpi-accent" style="background:{comp_color}"></div>
            <div class="tm-kpi-label">Completion Rate</div>
            <div class="tm-kpi-value" style="color:{comp_color}">{stats['completion_rate']}%</div>
            <div class="tm-kpi-sub">Avg {stats['avg_days']}d to complete</div>
        </div>
    </div>

    <!-- Row 1: Trend + Status Donut -->
    <div class="tm-row">
        <!-- Trend Chart -->
        <div class="tm-card">
            <div class="tm-card-header">
                <span class="tm-card-title">📈 Monthly Trend</span>
                <span class="tm-card-badge">{len(trend)} months</span>
            </div>
            <div class="tm-trend">
                <div class="tm-canvas-wrap">
                    <canvas id="tm_trend_chart"></canvas>
                </div>
            </div>
        </div>

        <!-- Status Breakdown -->
        <div class="tm-card">
            <div class="tm-card-header">
                <span class="tm-card-title">🎯 Status Breakdown</span>
            </div>
            <div class="tm-donut-wrap">
                <canvas id="tm_status_chart" width="150" height="150"></canvas>
                <div class="tm-legend">
                    <div class="tm-legend-item">
                        <div class="tm-legend-dot" style="background:#2e7d32"></div>
                        <span>Completed <b>{stats['completed']}</b></span>
                    </div>
                    <div class="tm-legend-item">
                        <div class="tm-legend-dot" style="background:#1565C0"></div>
                        <span>In Progress <b>{stats['in_progress']}</b></span>
                    </div>
                    <div class="tm-legend-item">
                        <div class="tm-legend-dot" style="background:#78909c"></div>
                        <span>Open/Active <b>{stats['open']}</b></span>
                    </div>
                    <div class="tm-legend-item">
                        <div class="tm-legend-dot" style="background:#b0bec5"></div>
                        <span>Draft <b>{stats['draft']}</b></span>
                    </div>
                    <div class="tm-legend-item">
                        <div class="tm-legend-dot" style="background:#c62828"></div>
                        <span>Overdue <b>{stats['overdue']}</b></span>
                    </div>
                    <div class="tm-legend-item">
                        <div class="tm-legend-dot" style="background:#e65100"></div>
                        <span>Delayed <b>{stats['delayed']}</b></span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Row 2: Employee Table + Priority + Category -->
    <div class="tm-row-3">
        <!-- Employee Table -->
        <div class="tm-card">
            <div class="tm-card-header">
                <span class="tm-card-title">👥 By Employee</span>
                <span class="tm-card-badge">{len(by_employee)} employees</span>
            </div>
            <div style="overflow-x:auto;max-height:320px;overflow-y:auto">
                <table class="tm-table">
                    <thead>
                        <tr>
                            <th>Employee</th>
                            <th>Dept</th>
                            <th class="center">Total</th>
                            <th class="center">Done</th>
                            <th class="center">On Time</th>
                            <th class="center">Overdue</th>
                            <th>Completion</th>
                        </tr>
                    </thead>
                    <tbody>{emp_rows}</tbody>
                </table>
            </div>
        </div>

        <!-- Priority Breakdown -->
        <div class="tm-card">
            <div class="tm-card-header">
                <span class="tm-card-title">⚡ By Priority</span>
            </div>
            <table class="tm-table">
                <thead>
                    <tr>
                        <th>Priority</th>
                        <th class="center">Total</th>
                        <th class="center">Done</th>
                        <th class="center">On-T</th>
                        <th class="center">OD</th>
                        <th class="center">Rate</th>
                    </tr>
                </thead>
                <tbody>{pri_rows}</tbody>
            </table>
        </div>

        <!-- Category Breakdown -->
        <div class="tm-card">
            <div class="tm-card-header">
                <span class="tm-card-title">🏷️ By Category</span>
            </div>
            <table class="tm-table">
                <thead>
                    <tr>
                        <th>Category</th>
                        <th class="center">Total</th>
                        <th class="center">Done</th>
                        <th class="center">Rate</th>
                    </tr>
                </thead>
                <tbody>{cat_rows}</tbody>
            </table>
        </div>
    </div>

    <!-- Row 3: Department -->
    <div class="tm-card">
        <div class="tm-card-header">
            <span class="tm-card-title">🏢 By Department</span>
            <span class="tm-card-badge">{len(by_dept)} departments</span>
        </div>
        <div class="tm-bar-chart">
            {"".join([
                f'''<div class="tm-bar-row">
                    <div class="tm-bar-label" title="{d['dept']}">{d['dept'][:14]}</div>
                    <div class="tm-bar-track">
                        <div class="tm-bar-fill" style="width:{round(d['completed']/d['total']*100) if d['total'] else 0}%;
                            background:{'#2e7d32' if (round(d['completed']/d['total']*100) if d['total'] else 0)>=75 else '#f57c00' if (round(d['completed']/d['total']*100) if d['total'] else 0)>=50 else '#c62828'}">
                            {round(d['completed']/d['total']*100) if d['total'] else 0}%
                        </div>
                    </div>
                    <span style="font-size:11px;color:#888;min-width:60px">{d['completed']}/{d['total']} tasks</span>
                </div>'''
                for d in by_dept
            ])}
        </div>
    </div>
</div>

<script>
(function() {{
    // Wait for Chart.js to be ready
    function waitForChartJs(cb) {{
        if (window.Chart) {{ cb(); return; }}
        // Lazy-load Chart.js from CDN
        var s = document.createElement('script');
        s.src = 'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js';
        s.onload = cb;
        document.head.appendChild(s);
    }}

    waitForChartJs(function() {{
        // --- Trend Line Chart ---
        var trendCtx = document.getElementById('tm_trend_chart');
        if (trendCtx) {{
            new Chart(trendCtx, {{
                type: 'line',
                data: {{
                    labels: {trend_labels},
                    datasets: [
                        {{
                            label: 'Total',
                            data: {trend_total},
                            borderColor: '#3b5bdb',
                            backgroundColor: 'rgba(59,91,219,0.08)',
                            borderWidth: 2,
                            pointRadius: 4,
                            pointBackgroundColor: '#3b5bdb',
                            tension: 0.4,
                            fill: true,
                        }},
                        {{
                            label: 'Completed',
                            data: {trend_completed},
                            borderColor: '#2e7d32',
                            backgroundColor: 'rgba(46,125,50,0.08)',
                            borderWidth: 2,
                            pointRadius: 4,
                            pointBackgroundColor: '#2e7d32',
                            tension: 0.4,
                            fill: true,
                        }},
                        {{
                            label: 'Overdue',
                            data: {trend_overdue},
                            borderColor: '#c62828',
                            backgroundColor: 'rgba(198,40,40,0.05)',
                            borderWidth: 2,
                            pointRadius: 4,
                            pointBackgroundColor: '#c62828',
                            tension: 0.4,
                            fill: true,
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ position: 'bottom', labels: {{ boxWidth: 10, font: {{ size: 11 }} }} }}
                    }},
                    scales: {{
                        y: {{ beginAtZero: true, ticks: {{ stepSize: 1, font: {{ size: 11 }} }}, grid: {{ color: '#f5f5f5' }} }},
                        x: {{ ticks: {{ font: {{ size: 11 }} }}, grid: {{ display: false }} }}
                    }}
                }}
            }});
        }}

        // --- Status Donut Chart ---
        var statusCtx = document.getElementById('tm_status_chart');
        if (statusCtx) {{
            new Chart(statusCtx, {{
                type: 'doughnut',
                data: {{
                    labels: ['Completed', 'Open/Active', 'Overdue', 'Delayed Late', 'Draft'],
                    datasets: [{{
                        data: [{stats['completed']}, {stats['open']}, {stats['overdue']}, {stats['delayed']}, {stats['draft']}],
                        backgroundColor: ['#2e7d32','#1565C0','#c62828','#e65100','#b0bec5'],
                        borderWidth: 0,
                        hoverOffset: 4,
                    }}]
                }},
                options: {{
                    responsive: false,
                    plugins: {{
                        legend: {{ display: false }},
                        tooltip: {{ callbacks: {{
                            label: function(ctx) {{
                                return ' ' + ctx.label + ': ' + ctx.raw;
                            }}
                        }}}}
                    }},
                    cutout: '65%',
                }}
            }});
        }}
    }});
}})();
</script>
"""
