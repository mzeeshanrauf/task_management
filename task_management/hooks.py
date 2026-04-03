app_name = "task_management"
app_title = "Task Management"
app_publisher = "Your Company"
app_description = "Department-wise Task Management with KPI Evaluation for ERPNext"
app_email = "info@yourcompany.com"
app_license = "MIT"
app_version = "1.0.0"

app_include_js = "/assets/task_management/js/task_management.js"
app_include_css = "/assets/task_management/css/task_management.css"

scheduler_events = {
    "daily": [
        "task_management.task_management.tasks.mark_overdue_tasks",
        "task_management.task_management.tasks.send_deadline_reminders"
    ],
    "monthly": [
        "task_management.task_management.tasks.generate_monthly_kpi_summary"
    ]
}

# Row-level permission — department/hierarchy aware
permission_query_conditions = {
    "Employee Task": "task_management.task_management.doctype.employee_task.employee_task.get_permission_query_conditions",
    "Sales Person": "task_management.task_management.permission.sales_person_conditions",
}

has_permission = {
    "Employee Task": "task_management.task_management.doctype.employee_task.employee_task.has_permission",
}

after_install = "task_management.task_management.install.after_install"

# ---------------------------------------------------------------------------
# Fixtures — custom fields installed with the app
# ---------------------------------------------------------------------------
fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [["module", "=", "Task Management"]]
    }
]
