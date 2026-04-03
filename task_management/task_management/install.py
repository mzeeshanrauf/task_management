import frappe

def after_install():
    create_roles()
    create_default_categories()

def create_roles():
    roles = [
        ("Task General Manager",
         "Sees all tasks in their department. Can assign, complete, cancel any task."),
        ("Task Manager",
         "Division-level manager. Sees and manages only tasks they assigned."),
        ("Task Employee",
         "Regular employee. Can view own tasks and add progress updates only."),
    ]
    for role_name, desc in roles:
        if not frappe.db.exists("Role", role_name):
            frappe.get_doc({
                "doctype": "Role",
                "role_name": role_name,
                "desk_access": 1,
                "home_page": "",
                "role_rank": 0,
            }).insert(ignore_permissions=True)
    frappe.db.commit()

def create_default_categories():
    defaults = [
        {"category_name": "Development", "color": "#4CAF50", "icon": "💻"},
        {"category_name": "Design",      "color": "#2196F3", "icon": "🎨"},
        {"category_name": "Operations",  "color": "#FF9800", "icon": "⚙️"},
        {"category_name": "Sales",       "color": "#E91E63", "icon": "📈"},
        {"category_name": "Support",     "color": "#9C27B0", "icon": "🛟"},
        {"category_name": "HR",          "color": "#00BCD4", "icon": "👥"},
        {"category_name": "Finance",     "color": "#607D8B", "icon": "💰"},
        {"category_name": "Marketing",   "color": "#FF5722", "icon": "📣"},
        {"category_name": "General",     "color": "#795548", "icon": "📋"},
        {"category_name": "IT",          "color": "#0097A7", "icon": "🖥️"},
        {"category_name": "Accounts",    "color": "#388E3C", "icon": "🧾"},
    ]
    for cat in defaults:
        if not frappe.db.exists("Task Category", cat["category_name"]):
            frappe.get_doc({"doctype": "Task Category", **cat}).insert(ignore_permissions=True)
    frappe.db.commit()
