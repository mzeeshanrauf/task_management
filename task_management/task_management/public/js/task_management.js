frappe.provide("task_management");

task_management = {
    get_kpi_grade_badge: function(grade) {
        const colors = {"A+": "#2e7d32", "A": "#388e3c", "B": "#1976d2",
                        "C": "#f57c00", "D": "#e64a19", "F": "#c62828"};
        const color = colors[grade] || "#666";
        return `<span style="background:${color};color:#fff;padding:2px 8px;border-radius:10px;font-weight:600">${grade}</span>`;
    },

    get_priority_badge: function(priority) {
        const colors = {"Critical": "#c62828", "High": "#e64a19", "Medium": "#1976d2", "Low": "#616161"};
        const color = colors[priority] || "#616161";
        return `<span style="color:${color};font-weight:600">● ${priority}</span>`;
    },

    open_kpi_dialog: function(employee) {
        frappe.call({
            method: "task_management.task_management.doctype.employee_task.employee_task.get_employee_task_summary",
            args: {employee: employee},
            callback: function(r) {
                const d = r.message;
                const dialog = new frappe.ui.Dialog({
                    title: `KPI Summary — ${employee}`,
                    fields: [{fieldtype: "HTML", fieldname: "summary_html"}]
                });
                dialog.fields_dict.summary_html.$wrapper.html(`
                    <div style="padding:16px">
                        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px">
                            ${kpi_card("📋 Total Tasks", d.total_tasks, "#1565C0")}
                            ${kpi_card("✅ Completed", d.completed, "#2e7d32")}
                            ${kpi_card("⏰ On Time", d.on_time, "#6a1b9a")}
                            ${kpi_card("⚠️ Overdue", d.overdue, "#c62828")}
                            ${kpi_card("Completion Rate", d.completion_rate + "%", "#0277bd")}
                            ${kpi_card("On-Time Rate", d.on_time_rate + "%", "#558b2f")}
                            ${kpi_card("KPI Points", d.total_kpi_points, "#e65100")}
                            ${kpi_card("Quality Score", d.quality_score_100, "#4527a0")}
                        </div>
                    </div>
                `);
                dialog.show();
            }
        });

        function kpi_card(label, value, color) {
            return `<div style="background:#f5f5f5;border-left:4px solid ${color};padding:12px;border-radius:4px">
                <div style="font-size:11px;color:#666">${label}</div>
                <div style="font-size:22px;font-weight:700;color:${color}">${value}</div>
            </div>`;
        }
    }
};
