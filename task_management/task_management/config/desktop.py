from frappe import _

def get_data():
    return [
        {
            "module_name": "Task Management",
            "category": "Modules",
            "label": _("Task Management"),
            "color": "#1565C0",
            "icon": "octicon octicon-tasklist",
            "type": "module",
            "description": "Assign tasks, track progress, and evaluate KPIs."
        }
    ]
