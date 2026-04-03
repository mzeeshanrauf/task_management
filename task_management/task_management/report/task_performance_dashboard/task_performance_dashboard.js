frappe.query_reports["Task Performance Dashboard"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department",
        },
        {
            fieldname: "employee",
            label: __("Employee"),
            fieldtype: "Link",
            options: "Employee",
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nOpen\nIn Progress\nPending Review\nCompleted\nCancelled\nOverdue",
        },
        {
            fieldname: "priority",
            label: __("Priority"),
            fieldtype: "Select",
            options: "\nLow\nMedium\nHigh\nCritical",
        },
        {
            fieldname: "category",
            label: __("Category"),
            fieldtype: "Link",
            options: "Task Category",
        },
    ],
    onload(report) {
        report.page.add_inner_button(__("Refresh"), () => report.refresh());
    },
};
