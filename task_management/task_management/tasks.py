import frappe
from frappe.utils import today, getdate, date_diff, add_days


def mark_overdue_tasks():
    """Daily job: auto-mark tasks as Overdue if past due date"""
    overdue_tasks = frappe.get_all("Employee Task",
        filters={
            "status": ["in", ["Open", "In Progress", "Pending Review"]],
            "due_date": ["<", today()]
        },
        fields=["name", "due_date"]
    )
    for task in overdue_tasks:
        frappe.db.set_value("Employee Task", task.name, {
            "is_overdue": 1,
            "overdue_days": date_diff(today(), task.due_date),
            "status": "Overdue"
        })
    if overdue_tasks:
        frappe.db.commit()
        frappe.logger().info(f"[Task Management] Marked {len(overdue_tasks)} tasks as Overdue.")


def send_deadline_reminders():
    """Daily job: send reminder for tasks due in 1-2 days"""
    tomorrow = add_days(today(), 1)
    day_after = add_days(today(), 2)

    upcoming = frappe.get_all("Employee Task",
        filters={
            "status": ["in", ["Open", "In Progress"]],
            "due_date": ["between", [tomorrow, day_after]]
        },
        fields=["name", "task_title", "assigned_to", "assigned_to_name", "due_date", "assigned_by_name"]
    )

    for task in upcoming:
        try:
            emp = frappe.get_doc("Employee", task.assigned_to)
            if emp.user_id:
                days_left = date_diff(task.due_date, today())
                frappe.sendmail(
                    recipients=[emp.user_id],
                    subject=f"⏰ Reminder: Task '{task.task_title}' due in {days_left} day(s)",
                    message=f"""
                        Dear {task.assigned_to_name},<br><br>
                        This is a reminder that your task <b>{task.task_title}</b> is due on <b>{task.due_date}</b> ({days_left} day(s) remaining).<br>
                        Assigned by: {task.assigned_by_name}<br><br>
                        Please update your progress in ERPNext.<br><br>
                        Regards,<br>Task Management System
                    """
                )
        except Exception as e:
            frappe.logger().error(f"[Task Management] Reminder error for {task.name}: {e}")


def generate_monthly_kpi_summary():
    """Monthly job: auto-generate KPI summary for all employees with tasks"""
    from frappe.utils import get_first_day, get_last_day
    import calendar

    # Previous month
    import datetime
    today_date = datetime.date.today()
    first_of_this_month = today_date.replace(day=1)
    last_month = first_of_this_month - datetime.timedelta(days=1)
    period = last_month.strftime("%Y-%m")

    employees = frappe.db.sql("""
        SELECT DISTINCT assigned_to FROM `tabEmployee Task`
        WHERE SUBSTRING(due_date, 1, 7) = %s
    """, period, as_dict=1)

    from task_management.task_management.doctype.employee_task.employee_task import recalculate_employee_kpi
    for emp in employees:
        try:
            recalculate_employee_kpi(emp.assigned_to, period)
        except Exception as e:
            frappe.logger().error(f"[Task Management] KPI gen error for {emp.assigned_to}: {e}")

    frappe.logger().info(f"[Task Management] Monthly KPI summary generated for {len(employees)} employees for period {period}.")
