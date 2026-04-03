import frappe
from frappe.model.document import Document
from frappe.utils import today, date_diff, now_datetime, getdate
from frappe import _

# ---------------------------------------------------------------------------
# WORKFLOW:
#   1. Manager creates task (Draft/Open) — employee is NOT notified yet
#   2. Manager clicks "Submit Task to Employee" → docstatus=1, employee notified
#   3. Employee sees task, adds progress updates (% updates)
#   4. Manager closes task → status=Completed, KPI calculated
#
# KPI FORMULA:
#   Sales dept:   Completion Rate (33%) + On-Time Rate (33%) + Quality (34%) + Target Achievement (50% bonus)
#   Other depts:  Completion Rate (34%) + On-Time Rate (33%) + Quality (33%)
#   Target Achievement = (actual_sales / sales_target) × 100 — from submitted Sales Orders
#
# CLOSED TASK = docstatus=2 (cancelled in Frappe terms, but we use "Closed" status)
# Actually: submitted(1)=active assigned, cancelled(2)=closed/completed in KPI
# ---------------------------------------------------------------------------

QUALITY_MAP = {"5 - Excellent": 5, "4 - Good": 4, "3 - Average": 3,
               "2 - Below Average": 2, "1 - Poor": 1}

SALES_DEPT_KEYWORDS = ["sales", "sale"]  # keyword fallback


def is_manager(user=None):
    user = user or frappe.session.user
    roles = frappe.get_roles(user)
    return "Task Manager" in roles or "Task General Manager" in roles or "Administrator" in roles


def get_current_employee(user=None):
    user = user or frappe.session.user
    return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")


def is_sales_department(department):
    """
    Returns True if department should use Sales KPI formula.
    Priority:
      1. Manual override — 'Is Sales Department' checkbox on Department doctype
      2. Keyword detection — department name contains 'sale' or 'sales'
    """
    if not department:
        return False
    # 1. Manual override checkbox — only check if column exists in DB
    try:
        col_exists = frappe.db.sql(
            "SHOW COLUMNS FROM `tabDepartment` LIKE 'is_sales_department'"
        )
        if col_exists:
            manual = frappe.db.get_value("Department", department, "is_sales_department")
            if manual:
                return True
    except Exception:
        pass
    # 2. Keyword fallback
    return any(kw in (department or "").lower() for kw in SALES_DEPT_KEYWORDS)


class EmployeeTask(Document):

    def before_insert(self):
        """Auto-fill Assigned By from the currently logged-in manager."""
        if not self.assigned_by:
            emp = get_current_employee()
            if emp:
                self.assigned_by = emp
                emp_doc = frappe.get_doc("Employee", emp)
                self.assigned_by_name = emp_doc.employee_name
                self.manager_department = emp_doc.department
        # Default progress to 0 on creation
        self.completion_percentage = 0
        if not self.status:
            self.status = "Open"

    def validate(self):
        self.enforce_manager_only_create()
        self.auto_fill_assigned_by()
        self.validate_dates()
        self.validate_department_scope()
        self.calculate_overdue()
        self.validate_status_change()

    def enforce_manager_only_create(self):
        if frappe.session.user == "Administrator":
            return
        if "System Manager" in frappe.get_roles(frappe.session.user):
            return
        if self.is_new() and not is_manager():
            frappe.throw(_("Only Managers can create tasks."))

    def auto_fill_assigned_by(self):
        if not self.assigned_by:
            emp = get_current_employee()
            if emp:
                self.assigned_by = emp
        if self.assigned_by and not self.assigned_by_name:
            self.assigned_by_name = frappe.db.get_value("Employee", self.assigned_by, "employee_name")
        if self.assigned_by and not self.manager_department:
            self.manager_department = frappe.db.get_value("Employee", self.assigned_by, "department")

    def validate_dates(self):
        if self.start_date and self.due_date:
            if getdate(self.start_date) > getdate(self.due_date):
                frappe.throw(_("Due Date must be after Start Date."))

    def validate_department_scope(self):
        """Division Manager can only assign to employees in their department."""
        if frappe.session.user == "Administrator":
            return
        roles = frappe.get_roles(frappe.session.user)
        if "System Manager" in roles or "Task General Manager" in roles:
            return
        if "Task Manager" in roles and self.assigned_to and self.assigned_by:
            mgr_dept = frappe.db.get_value("Employee", self.assigned_by, "department")
            emp_dept = frappe.db.get_value("Employee", self.assigned_to, "department")
            if mgr_dept and emp_dept and mgr_dept != emp_dept:
                frappe.throw(_(f"You can only assign tasks to employees in your department ({mgr_dept})."))

    def calculate_overdue(self):
        today_date = getdate(today())
        due = getdate(self.due_date) if self.due_date else None
        if not due:
            return
        if self.status in ["Completed", "Cancelled", "Closed"]:
            self.is_overdue = 0
            self.overdue_days = 0
        elif due < today_date:
            self.is_overdue = 1
            self.overdue_days = date_diff(today_date, due)
        else:
            self.is_overdue = 0
            self.overdue_days = 0

    def validate_status_change(self):
        if self.is_new():
            return
        old_doc = self.get_doc_before_save() if hasattr(self, 'get_doc_before_save') else getattr(self, '_doc_before_save', None)
        if old_doc and old_doc.status == "Completed":
            if not is_manager():
                frappe.throw(_("Only Managers can reopen a completed task."))

    def before_save(self):
        # On close (status=Completed), record completion metrics
        if self.status == "Completed" and not self.completed_on:
            self.completed_on = today()
            due = getdate(self.due_date)
            completed = getdate(self.completed_on)
            start = getdate(self.start_date) if self.start_date else completed
            self.days_to_complete = date_diff(completed, start)
            self.allocated_days = max(date_diff(due, start), 1)
            self.on_time = 1 if completed <= due else 0
            self.overdue_days = 0 if self.on_time else date_diff(completed, due)
        # Do NOT auto-set completion_percentage here — only add_progress_update does that

    def before_submit(self):
        """
        Submit = Assign task to employee (notify them).
        Progress % stays at 0. Status stays Open.
        Only managers can submit.
        """
        u = frappe.session.user
        if u != "Administrator" and "System Manager" not in frappe.get_roles(u):
            if not is_manager():
                frappe.throw(_("Only Managers can submit (assign) tasks to employees."))
        # Keep status as Open and progress at 0 when submitting
        if self.status not in ["Open", "In Progress", "Pending Review"]:
            self.status = "Open"
        self.completion_percentage = self.completion_percentage or 0

    def on_submit(self):
        """Notify employee that a task has been assigned to them."""
        self._notify("assigned")

    def before_cancel(self):
        """Only managers can cancel/close tasks."""
        u = frappe.session.user
        if u != "Administrator" and "System Manager" not in frappe.get_roles(u):
            if not is_manager():
                frappe.throw(_("Only Managers can close/cancel tasks."))

    def on_cancel(self):
        recalculate_employee_kpi(self.assigned_to)
        self._notify("cancelled")

    def _notify(self, event):
        try:
            emp = frappe.get_doc("Employee", self.assigned_to)
            if not emp.user_id:
                return
            msgs = {
                "assigned": (
                    f"New Task Assigned: {self.task_title}",
                    f"A new task <b>{self.task_title}</b> has been assigned to you by "
                    f"<b>{self.assigned_by_name}</b>.<br>"
                    f"Due: <b>{self.due_date}</b> | Priority: <b>{self.priority}</b>"
                ),
                "completed": (
                    f"Task Closed: {self.task_title}",
                    f"Your task <b>{self.task_title}</b> has been marked <b>Completed</b> "
                    f"by your manager. It is now counted in your KPI."
                ),
                "cancelled": (
                    f"Task Cancelled: {self.task_title}",
                    f"Your task <b>{self.task_title}</b> has been <b>Cancelled</b> "
                    f"by your manager."
                ),
            }
            subject, msg = msgs.get(event, (None, None))
            if subject:
                frappe.sendmail(recipients=[emp.user_id], subject=subject, message=msg)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Whitelisted API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def close_task(task_name, manager_review=None, quality_score=None):
    """
    Manager closes a submitted task.
    Sets status=Completed, records quality, recalculates KPI, notifies employee.
    This is the ONLY way a task gets into KPI calculations.
    """
    u = frappe.session.user
    if u != "Administrator" and "System Manager" not in frappe.get_roles(u):
        if not is_manager():
            frappe.throw(_("Only Managers can close tasks."))

    doc = frappe.get_doc("Employee Task", task_name)
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted tasks can be closed."))
    if doc.status == "Completed":
        frappe.throw(_("This task is already closed."))

    completed_on = today()
    due = getdate(doc.due_date)
    completed_date = getdate(completed_on)
    start = getdate(doc.start_date) if doc.start_date else completed_date
    days_to_complete = date_diff(completed_date, start)
    allocated_days = max(date_diff(due, start), 1)
    on_time = 1 if completed_date <= due else 0
    overdue_days = 0 if on_time else date_diff(completed_date, due)

    # Direct DB update — bypasses Frappe submission lock
    frappe.db.sql("""
        UPDATE `tabEmployee Task`
        SET status           = 'Completed',
            completed_on     = %(completed_on)s,
            days_to_complete = %(days_to_complete)s,
            allocated_days   = %(allocated_days)s,
            on_time          = %(on_time)s,
            overdue_days     = %(overdue_days)s,
            is_overdue       = 0,
            completion_percentage = 100,
            manager_review   = %(manager_review)s,
            quality_score    = %(quality_score)s,
            modified         = NOW(),
            modified_by      = %(user)s
        WHERE name = %(name)s
    """, {
        "completed_on": completed_on,
        "days_to_complete": days_to_complete,
        "allocated_days": allocated_days,
        "on_time": on_time,
        "overdue_days": overdue_days,
        "manager_review": manager_review or "",
        "quality_score": quality_score or "",
        "user": frappe.session.user,
        "name": task_name,
    })
    frappe.db.commit()

    doc.reload()
    recalculate_employee_kpi(doc.assigned_to)
    doc._notify("completed")

    frappe.msgprint(
        f"✅ Task '<b>{doc.task_title}</b>' closed and counted in KPI.",
        indicator="green"
    )
    return {"status": "closed"}


@frappe.whitelist()
def cancel_task(task_name, reason=None):
    """Manager cancels a task (draft or submitted)."""
    u = frappe.session.user
    if u != "Administrator" and "System Manager" not in frappe.get_roles(u):
        if not is_manager():
            frappe.throw(_("Only Managers can cancel tasks."))
    doc = frappe.get_doc("Employee Task", task_name)
    if doc.docstatus == 0:
        doc.status = "Cancelled"
        doc.save()
        frappe.msgprint("Task cancelled.", indicator="orange")
    elif doc.docstatus == 1:
        doc.cancel()
        frappe.msgprint("Task cancelled.", indicator="orange")
    else:
        frappe.throw(_("Task is already cancelled."))
    return {"status": "cancelled"}


@frappe.whitelist()
def add_progress_update(task_name, update_text, percentage=None):
    """Employee or manager adds a progress update. Works on submitted tasks."""
    doc = frappe.get_doc("Employee Task", task_name)
    if doc.docstatus == 2:
        frappe.throw(_("Cannot update a cancelled task."))
    if doc.status == "Completed":
        frappe.throw(_("Cannot update a closed task."))

    user = frappe.session.user
    emp = get_current_employee(user)
    if emp != doc.assigned_to and not is_manager(user):
        frappe.throw(_("You can only update your own tasks."))

    new_pct = float(percentage) if percentage is not None else doc.completion_percentage

    if doc.docstatus == 1:
        # Submitted doc — use direct DB inserts to bypass Frappe's version/submission lock
        child_name = frappe.generate_hash(length=10)
        frappe.db.sql("""
            INSERT INTO `tabTask Update`
                (name, parent, parenttype, parentfield, idx,
                 update_text, updated_by, update_date, update_time,
                 percentage_at_update, docstatus, creation, modified, modified_by, owner)
            VALUES
                (%(name)s, %(parent)s, 'Employee Task', 'task_updates',
                 (SELECT COALESCE(MAX(idx),0)+1 FROM `tabTask Update` t2 WHERE t2.parent=%(parent)s),
                 %(update_text)s, %(updated_by)s, %(update_date)s, %(update_time)s,
                 %(pct)s, 0, NOW(), NOW(), %(user)s, %(user)s)
        """, {
            "name": child_name,
            "parent": task_name,
            "update_text": update_text,
            "updated_by": user,
            "update_date": today(),
            "update_time": str(now_datetime().time())[:8],
            "pct": new_pct,
            "user": user,
        })

        # Update parent fields directly — no version conflict
        new_status = doc.status
        if doc.status == "Open" and new_pct > 0:
            new_status = "In Progress"

        frappe.db.sql("""
            UPDATE `tabEmployee Task`
            SET completion_percentage = %(pct)s,
                status = %(status)s,
                modified = NOW(),
                modified_by = %(user)s
            WHERE name = %(name)s
        """, {
            "pct": new_pct,
            "status": new_status,
            "user": user,
            "name": task_name,
        })
        frappe.db.commit()

    else:
        # Draft doc — normal save
        doc.append("task_updates", {
            "update_text": update_text,
            "updated_by": user,
            "update_date": today(),
            "update_time": str(now_datetime().time())[:8],
            "percentage_at_update": new_pct
        })
        if percentage is not None:
            doc.completion_percentage = new_pct
            if doc.status == "Open" and new_pct > 0:
                doc.status = "In Progress"
        doc.save(ignore_permissions=True)
        frappe.db.commit()

    return "Update added."


@frappe.whitelist()
def get_employees_for_manager(doctype, txt, searchfield, start, page_len, filters):
    """Link field search — returns employees visible to the current manager."""
    user = frappe.session.user
    roles = frappe.get_roles(user)
    emp = get_current_employee(user)

    if user == "Administrator" or "System Manager" in roles:
        condition = ""
    elif "Task General Manager" in roles and emp:
        dept = frappe.db.get_value("Employee", emp, "department")
        condition = f"AND e.department = '{dept}'" if dept else ""
    elif "Task Manager" in roles and emp:
        dept = frappe.db.get_value("Employee", emp, "department")
        condition = f"AND e.department = '{dept}'" if dept else ""
    else:
        condition = f"AND e.name = '{emp}'" if emp else "AND 1=0"

    return frappe.db.sql(f"""
        SELECT e.name, e.employee_name, e.department
        FROM `tabEmployee` e
        WHERE e.status = 'Active'
          AND (e.name LIKE %(txt)s OR e.employee_name LIKE %(txt)s)
          {condition}
        LIMIT %(page_len)s OFFSET %(start)s
    """, {"txt": f"%{txt}%", "page_len": page_len, "start": start})


@frappe.whitelist()
def get_department_task_overview(department=None):
    user = frappe.session.user
    roles = frappe.get_roles(user)

    if user == "Administrator" or "System Manager" in roles:
        pass
    else:
        emp = get_current_employee(user)
        if not department and emp:
            department = frappe.db.get_value("Employee", emp, "department")
    if not department and user != "Administrator":
        frappe.throw(_("Could not determine your department."))

    filters = {"docstatus": ["!=", 2]}
    if department:
        filters["assigned_to_department"] = department

    tasks = frappe.get_all("Employee Task", filters=filters,
                           fields=["assigned_to", "assigned_to_name", "status",
                                   "assigned_by_name", "manager_department",
                                   "docstatus", "assigned_to_department"])

    from collections import defaultdict
    summary = defaultdict(lambda: {"name": "", "dept": "", "total": 0,
                                   "open": 0, "in_progress": 0,
                                   "completed": 0, "overdue": 0})
    for t in tasks:
        e = t.assigned_to
        summary[e]["name"] = t.assigned_to_name
        summary[e]["dept"] = t.assigned_to_department or department
        summary[e]["total"] += 1
        if t.status == "Completed":
            summary[e]["completed"] += 1
        elif t.status == "In Progress":
            summary[e]["in_progress"] += 1
        elif t.status == "Open":
            summary[e]["open"] += 1
        elif t.is_overdue:
            summary[e]["overdue"] += 1

    return list(summary.values())


@frappe.whitelist()
def get_employee_task_summary(employee, from_date=None, to_date=None):
    """Compute KPI for one employee. Formula differs for Sales vs other depts."""
    total_filters = {"assigned_to": employee, "docstatus": ["!=", 2]}
    if from_date and to_date:
        total_filters["due_date"] = ["between", [from_date, to_date]]
    elif from_date:
        total_filters["due_date"] = [">=", from_date]
    elif to_date:
        total_filters["due_date"] = ["<=", to_date]

    total_count = frappe.db.count("Employee Task", total_filters)

    # Open tasks = submitted (docstatus=1) but status != Completed
    open_count = frappe.db.count("Employee Task", {
        "assigned_to": employee, "docstatus": 1,
        "status": ["in", ["Open", "In Progress", "Pending Review"]]
    })

    # Completed tasks = submitted (docstatus=1) AND status=Completed
    done_filters = {"assigned_to": employee, "docstatus": 1, "status": "Completed"}
    if from_date and to_date:
        done_filters["due_date"] = ["between", [from_date, to_date]]
    elif from_date:
        done_filters["due_date"] = [">=", from_date]
    elif to_date:
        done_filters["due_date"] = ["<=", to_date]

    completed_tasks = frappe.get_all("Employee Task", filters=done_filters,
        fields=["name", "task_title", "priority", "due_date", "completed_on",
                "on_time", "days_to_complete", "allocated_days",
                "quality_score", "is_overdue", "overdue_days"])

    overdue_count = frappe.db.count("Employee Task",
        {"assigned_to": employee, "docstatus": 1, "is_overdue": 1,
         "status": ["in", ["Open", "In Progress", "Pending Review"]]})

    completed = completed_tasks
    on_time_list = [t for t in completed if t.on_time]
    overdue_completed = [t for t in completed if not t.on_time]

    completion_rate = (len(completed) / total_count * 100) if total_count else 0
    on_time_rate = (len(on_time_list) / len(completed) * 100) if completed else 0

    rated = [t for t in completed if t.quality_score]
    if rated:
        avg_rating = sum(QUALITY_MAP.get(t.quality_score, 3) for t in rated) / len(rated)
        quality_score_100 = ((avg_rating - 1) / 4) * 100
    else:
        avg_rating = 0.0
        quality_score_100 = 0.0

    avg_days = (sum(t.days_to_complete or 0 for t in completed) / len(completed)) if completed else 0

    # Get employee department
    emp_dept = frappe.db.get_value("Employee", employee, "department") or ""

    # ── TASK KPI — same formula for ALL employees ────────────────────────────
    # Completion(40%) + OnTime(30%) + Quality(30%)  Max=100
    task_kpi_score = round(min(
        completion_rate   * 0.40 +
        on_time_rate      * 0.30 +
        quality_score_100 * 0.30,
        100
    ), 2)

    # ── SALES KPI — sales dept only ──────────────────────────────────────────
    is_sales = is_sales_department(emp_dept)
    sales_target = actual_sales = target_achievement = sales_kpi_score = 0.0

    if is_sales:
        user_id = frappe.db.get_value("Employee", employee, "user_id")
        period_target, actual_sales, period_achievement, annual_target, overall_actual, overall_achievement =             get_sales_target_achievement(employee, user_id, from_date, to_date)
        sales_target       = period_target
        target_achievement = period_achievement
        # Sales KPI = period achievement capped at 100
        sales_kpi_score = round(min(period_achievement, 100), 2)

    return {
        "total_tasks":          total_count,
        "open_tasks":           open_count,
        "completed":            len(completed),
        "on_time":              len(on_time_list),
        "overdue":              overdue_count,
        "overdue_completed":    len(overdue_completed),
        "completion_rate":      round(completion_rate, 1),
        "on_time_rate":         round(on_time_rate, 1),
        "avg_quality_rating":   round(avg_rating, 2),
        "quality_score_100":    round(quality_score_100, 1),
        "avg_days_to_complete": round(avg_days, 1),
        "is_sales":             is_sales,
        "sales_target":         sales_target,
        "actual_sales":         actual_sales,
        "target_achievement":   round(period_achievement, 1),
        "overall_actual":       overall_actual if is_sales else 0,
        "overall_achievement":  round(overall_achievement, 1) if is_sales else 0,
        "annual_target":        annual_target if is_sales else 0,
        # Task KPI
        "task_kpi_score":       task_kpi_score,
        "task_kpi_grade":       get_grade(task_kpi_score),
        "task_kpi_rating":      get_rating(task_kpi_score),
        # Sales KPI
        "sales_kpi_score":      sales_kpi_score,
        "sales_kpi_grade":      get_grade(sales_kpi_score) if is_sales else "",
        "sales_kpi_rating":     get_rating(sales_kpi_score) if is_sales else "",
        # Legacy (keep for compat)
        "kpi_score":            task_kpi_score,
        "kpi_rating":           get_rating(task_kpi_score),
        "kpi_grade":            get_grade(task_kpi_score),
        "tasks":                completed
    }


@frappe.whitelist()
def debug_sales_kpi(employee, from_date=None, to_date=None):
    """
    Debug helper — call from browser console:
    frappe.call('task_management.task_management.doctype.employee_task.employee_task.debug_sales_kpi',
        {employee: 'EMP-0001', from_date: '2025-01-01', to_date: '2025-12-31'},
        r => console.log(r.message))
    """
    out = {}
    try:
        # Step 1: Sales Person link
        emp_user = frappe.db.get_value("Employee", employee, "user_id") if employee else None
        sales_person = None
        if emp_user:
            sales_person = frappe.db.get_value("Sales Person", {"custom_user": emp_user}, "name")
        if not sales_person:
            sales_person = frappe.db.get_value("Sales Person", {"employee": employee}, "name")
        out["step1_sales_person"] = sales_person or "NOT FOUND — No Sales Person linked via custom_user or employee"
        if not sales_person:
            return out

        # Step 2: Fiscal year
        ref_date = from_date or frappe.utils.today()
        fy = frappe.db.sql("""
            SELECT name FROM `tabFiscal Year`
            WHERE %(d)s BETWEEN year_start_date AND year_end_date AND disabled=0 LIMIT 1
        """, {"d": ref_date}, as_dict=1)
        out["step2_fiscal_year"] = fy[0].name if fy else "NOT FOUND"

        # Step 3: Target Detail rows (all, without fiscal year filter)
        all_targets = frappe.db.get_all("Target Detail",
            filters={"parent": sales_person, "parenttype": "Sales Person"},
            fields=["fiscal_year", "target_amount", "distribution_id", "item_group"])
        out["step3_all_target_rows"] = all_targets or "NO TARGET ROWS FOUND"

        # Step 4: Target Detail rows filtered by fiscal year
        if fy:
            fy_targets = frappe.db.get_all("Target Detail",
                filters={"parent": sales_person, "parenttype": "Sales Person", "fiscal_year": fy[0].name},
                fields=["fiscal_year", "target_amount", "distribution_id"])
            out["step4_fy_target_rows"] = fy_targets or "NO ROWS FOR THIS FISCAL YEAR"

        # Step 5: Sales Team entries for this sales person
        so_args = {"sp": sales_person}
        date_cond = ""
        if from_date and to_date:
            date_cond = "AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s"
            so_args.update({"from_date": from_date, "to_date": to_date})

        so_rows = frappe.db.sql(f"""
            SELECT so.name, so.transaction_date, so.status, so.grand_total,
                   st.allocated_amount, st.sales_person
            FROM `tabSales Order` so
            INNER JOIN `tabSales Team` st ON st.parent = so.name AND st.parenttype = 'Sales Order'
            WHERE st.sales_person = %(sp)s AND so.docstatus = 1
            {date_cond}
            LIMIT 20
        """, so_args, as_dict=1)
        out["step5_sales_orders"] = so_rows or "NO SUBMITTED SO FOUND for this sales person"

        # Step 6: Check if SO exists at all for this person (any status)
        any_so = frappe.db.sql("""
            SELECT so.name, so.docstatus, so.status, st.sales_person
            FROM `tabSales Order` so
            INNER JOIN `tabSales Team` st ON st.parent = so.name
            WHERE st.sales_person = %(sp)s LIMIT 5
        """, {"sp": sales_person}, as_dict=1)
        out["step6_any_so_any_status"] = any_so or "NO SO AT ALL for this sales person in Sales Team"

    except Exception as e:
        out["error"] = str(e)
    return out


MONTH_NAMES = {
    1:"January",2:"February",3:"March",4:"April",5:"May",6:"June",
    7:"July",8:"August",9:"September",10:"October",11:"November",12:"December"
}

def _get_months_in_range(from_date, to_date):
    """Return list of month names covered by the date range."""
    from frappe.utils import getdate
    start = getdate(from_date)
    end   = getdate(to_date)
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(MONTH_NAMES[m])
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months

def _get_period_target(annual, distribution_id, from_date, to_date):
    """Sum monthly targets for each month in the date range."""
    months = _get_months_in_range(from_date, to_date)
    total  = 0.0
    for month_name in months:
        if distribution_id:
            dist = frappe.db.get_all(
                "Monthly Distribution Percentage",
                filters={"parent": distribution_id, "month": month_name},
                fields=["percentage_allocation"], limit=1
            )
            pct = float(dist[0].percentage_allocation or 8.333) / 100 if dist else (1/12)
        else:
            pct = 1 / 12
        total += annual * pct
    return total


def get_sales_target_achievement(employee, user_id, from_date=None, to_date=None):
    """
    Returns (period_target, actual_sales, period_achievement, annual_target, overall_actual, overall_achievement)

    Period Achievement  = actual sales in date range / sum of monthly targets for that range
    Overall Achievement = full fiscal year actual / annual target
    """
    try:
        # ── Find Sales Person ─────────────────────────────────────────────
        # Try custom_user first, then employee fallback
        sales_person = None
        if user_id:
            sales_person = frappe.db.get_value("Sales Person", {"custom_user": user_id}, "name")
        if not sales_person and employee:
            sales_person = frappe.db.get_value("Sales Person", {"employee": employee}, "name")
        if not sales_person and employee:
            emp_user = frappe.db.get_value("Employee", employee, "user_id")
            if emp_user:
                sales_person = frappe.db.get_value("Sales Person", {"custom_user": emp_user}, "name")
        if not sales_person:
            return 0, 0, 0, 0, 0, 0

        # ── Fiscal year ───────────────────────────────────────────────────
        ref_date = from_date or frappe.utils.today()
        fy_row = frappe.db.sql("""
            SELECT name, year_start_date, year_end_date
            FROM `tabFiscal Year`
            WHERE %(d)s BETWEEN year_start_date AND year_end_date AND disabled=0
            LIMIT 1
        """, {"d": ref_date}, as_dict=1)
        fy_name  = fy_row[0].name              if fy_row else None
        fy_start = str(fy_row[0].year_start_date) if fy_row else f"{frappe.utils.getdate(ref_date).year}-01-01"
        fy_end   = str(fy_row[0].year_end_date)   if fy_row else f"{frappe.utils.getdate(ref_date).year}-12-31"

        # ── Target rows ───────────────────────────────────────────────────
        t_filters = {"parent": sales_person, "parenttype": "Sales Person"}
        if fy_name:
            t_filters["fiscal_year"] = fy_name
        target_rows = frappe.db.get_all("Target Detail",
            filters=t_filters,
            fields=["target_amount", "distribution_id"])
        target_rows = [r for r in target_rows if float(r.target_amount or 0) > 0]

        annual_target = sum(float(r.target_amount or 0) for r in target_rows)

        # ── Period target — sum monthly targets for each month in range ───
        _fd = from_date or fy_start
        _td = to_date   or fy_end
        period_target = 0.0
        for row in target_rows:
            period_target += _get_period_target(float(row.target_amount or 0), row.distribution_id, _fd, _td)

        # ── Actual sales in period ────────────────────────────────────────
        period_res = frappe.db.sql("""
            SELECT COALESCE(SUM(st.allocated_amount), 0) AS total
            FROM `tabSales Order` so
            INNER JOIN `tabSales Team` st ON st.parent = so.name AND st.parenttype = 'Sales Order'
            WHERE st.sales_person = %(sp)s AND so.docstatus = 1
              AND so.transaction_date BETWEEN %(fd)s AND %(td)s
        """, {"sp": sales_person, "fd": _fd, "td": _td}, as_dict=1)
        actual_sales = float(period_res[0].total or 0) if period_res else 0

        # ── Overall actual (full fiscal year) ─────────────────────────────
        overall_res = frappe.db.sql("""
            SELECT COALESCE(SUM(st.allocated_amount), 0) AS total
            FROM `tabSales Order` so
            INNER JOIN `tabSales Team` st ON st.parent = so.name AND st.parenttype = 'Sales Order'
            WHERE st.sales_person = %(sp)s AND so.docstatus = 1
              AND so.transaction_date BETWEEN %(fy_start)s AND %(fy_end)s
        """, {"sp": sales_person, "fy_start": fy_start, "fy_end": fy_end}, as_dict=1)
        overall_actual = float(overall_res[0].total or 0) if overall_res else 0

        # ── Achievement % ─────────────────────────────────────────────────
        period_achievement  = round((actual_sales  / period_target  * 100), 2) if period_target  > 0 else 0.0
        overall_achievement = round((overall_actual / annual_target * 100), 2) if annual_target > 0 else 0.0

        return (
            round(period_target, 2),
            round(actual_sales, 2),
            round(period_achievement, 2),
            round(annual_target, 2),
            round(overall_actual, 2),
            round(overall_achievement, 2),
        )

    except Exception as e:
        frappe.log_error(f"Sales target fetch error for {employee}: {e}")
        return 0, 0, 0, 0, 0, 0


@frappe.whitelist()
def recalculate_employee_kpi(employee, period=None):
    import calendar
    if not period:
        period = today()[:7]
    year, month = period.split("-")
    from_date = f"{year}-{month}-01"
    last_day = calendar.monthrange(int(year), int(month))[1]
    to_date = f"{year}-{month}-{last_day:02d}"

    s = get_employee_task_summary(employee, from_date, to_date)
    emp_name = frappe.db.get_value("Employee", employee, "employee_name")
    existing = frappe.db.get_value("Task KPI Summary",
        {"employee": employee, "period": period}, "name")
    doc = frappe.get_doc("Task KPI Summary", existing) if existing else frappe.new_doc("Task KPI Summary")
    if not existing:
        doc.employee = employee
        doc.employee_name = emp_name
        doc.period = period

    # Set department on new records
    if not existing:
        doc.department = frappe.db.get_value("Employee", employee, "department") or ""

    # Task stats
    doc.total_tasks        = s["total_tasks"]
    doc.completed_tasks    = s["completed"]
    doc.on_time_tasks      = s["on_time"]
    doc.overdue_tasks      = s["overdue"]
    doc.completion_rate    = s["completion_rate"]
    doc.on_time_rate       = s["on_time_rate"]
    doc.avg_quality_rating = s["avg_quality_rating"]
    doc.quality_score_100  = s["quality_score_100"]
    # Task KPI
    doc.task_kpi_score     = s["task_kpi_score"]
    doc.task_kpi_grade     = s["task_kpi_grade"]
    doc.task_kpi_rating    = s["task_kpi_rating"]
    # Sales KPI
    doc.is_sales_dept      = 1 if s.get("is_sales") else 0
    doc.sales_target       = s.get("sales_target", 0)
    doc.actual_sales       = s.get("actual_sales", 0)
    doc.target_achievement = s.get("target_achievement", 0)
    doc.sales_kpi_score    = s.get("sales_kpi_score", 0)
    doc.sales_kpi_grade    = s.get("sales_kpi_grade", "")
    doc.sales_kpi_rating   = s.get("sales_kpi_rating", "")
    # Legacy (hidden field kept for compat)
    doc.kpi_score          = s["task_kpi_score"]
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_rating(score):
    if score >= 90: return "Outstanding"
    if score >= 75: return "Exceeds Expectations"
    if score >= 60: return "Meets Expectations"
    if score >= 40: return "Needs Improvement"
    return "Unsatisfactory"

def get_grade(score):
    if score >= 90: return "A+"
    if score >= 75: return "A"
    if score >= 60: return "B"
    if score >= 40: return "C"
    return "D"


# ---------------------------------------------------------------------------
# Permission system
# ---------------------------------------------------------------------------

def get_permission_query_conditions(user):
    if user == "Administrator":
        return ""
    roles = frappe.get_roles(user)
    if "System Manager" in roles:
        return ""
    emp = get_current_employee(user)
    if "Task General Manager" in roles:
        if emp:
            dept = frappe.db.get_value("Employee", emp, "department")
            if dept:
                return f"`tabEmployee Task`.assigned_to_department = '{dept}'"
        return ""
    if "Task Manager" in roles:
        if emp:
            return f"`tabEmployee Task`.assigned_by = '{emp}'"
        return "1=0"
    if emp:
        return f"`tabEmployee Task`.assigned_to = '{emp}'"
    return "1=0"


def has_permission(doc, ptype, user):
    if user == "Administrator":
        return True
    roles = frappe.get_roles(user)
    if "System Manager" in roles:
        return True
    emp = get_current_employee(user)
    if "Task General Manager" in roles:
        mgr_dept = frappe.db.get_value("Employee", emp, "department") if emp else None
        return (not mgr_dept) or (doc.assigned_to_department == mgr_dept)
    if "Task Manager" in roles:
        return doc.assigned_by == emp
    return doc.assigned_to == emp
