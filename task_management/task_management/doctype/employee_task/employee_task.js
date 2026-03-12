// ============================================================
// Employee Task — Client Script
// WORKFLOW:
//   1. Manager creates task (Draft) — no notification yet
//   2. Manager submits → employee notified, progress starts at 0%
//   3. Employee adds progress updates (updates %)
//   4. Manager closes task → KPI calculated, employee notified
//
// "✅ Submitted — Task is locked and counted in KPI."
//   shown ONLY after Close Task (status=Completed)
// ============================================================

const TM = {
    isManager() {
        return frappe.user_roles.includes("Task Manager")
            || frappe.user_roles.includes("Task General Manager")
            || frappe.user_roles.includes("Administrator")
            || frappe.user_roles.includes("System Manager");
    }
};

frappe.ui.form.on('Employee Task', {

    onload(frm) {
        if (frm.is_new() && TM.isManager()) {
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'Employee',
                    filters: { user_id: frappe.session.user, status: 'Active' },
                    fieldname: ['name', 'employee_name', 'department']
                },
                callback(r) {
                    if (r.message) {
                        frm.set_value('assigned_by', r.message.name);
                        frm.set_value('assigned_by_name', r.message.employee_name);
                        frm.set_value('manager_department', r.message.department);
                    }
                }
            });
        }
        if (TM.isManager()) {
            frm.set_query('assigned_to', () => ({
                query: 'task_management.task_management.doctype.employee_task.employee_task.get_employees_for_manager',
                filters: {}
            }));
        }
    },

    refresh(frm) {
        frm.trigger('toggle_sections');
        frm.trigger('render_status_badge');
        frm.trigger('render_progress_bar');
        frm.trigger('setup_buttons');
        frm.trigger('lock_employee_fields');
        frm.trigger('show_banners');
    },

    toggle_sections(frm) {
        // Status & Progress only after save
        const saved = !frm.is_new();
        frm.toggle_display('section_break_status', saved);
        frm.toggle_display('status', saved);
        frm.toggle_display('completion_percentage', saved);
        frm.toggle_display('column_break_status', saved);
        frm.toggle_display('on_time', saved);
        frm.toggle_display('overdue_days', saved);

        // Manager Review only for managers, only after save
        const showReview = saved && TM.isManager();
        frm.toggle_display('section_break_review', showReview);
        frm.toggle_display('manager_review', showReview);
        frm.toggle_display('column_break_review', showReview);
        frm.toggle_display('quality_score', showReview);
    },

    render_status_badge(frm) {
        const colors = {
            'Open': 'grey', 'In Progress': 'blue', 'Pending Review': 'yellow',
            'Completed': 'green', 'Cancelled': 'red', 'Overdue': 'orange'
        };
        if (frm.doc.status) {
            frm.page.set_indicator(frm.doc.status, colors[frm.doc.status] || 'grey');
        }
    },

    show_banners(frm) {
        frm.dashboard.reset();

        // ── Draft state banner ─────────────────────────────────────────────
        if (frm.doc.docstatus === 0 && !frm.is_new()) {
            frm.dashboard.add_comment(
                '📋 <b>Draft</b> — Task not yet sent to employee. Submit to notify them.',
                'yellow', true
            );
        }

        // ── Submitted (assigned) — NOT completed yet ───────────────────────
        if (frm.doc.docstatus === 1 && frm.doc.status !== 'Completed') {
            frm.dashboard.add_comment(
                '📤 <b>Assigned</b> — Employee has been notified. Waiting for completion.',
                'blue', true
            );
        }

        // ── Closed/Completed — show KPI banner ────────────────────────────
        if (frm.doc.docstatus === 1 && frm.doc.status === 'Completed') {
            const onTime = frm.doc.on_time
                ? '✅ <b>On Time</b>'
                : `⚠️ <b>Overdue by ${frm.doc.overdue_days} day(s)</b>`;
            frm.dashboard.add_comment(
                `✅ <b>Task Closed & Counted in KPI</b> — ${onTime} | Quality: ${frm.doc.quality_score || 'N/A'}`,
                'green', true
            );
        }

        // ── Overdue warning ───────────────────────────────────────────────
        if (frm.doc.is_overdue && frm.doc.docstatus === 1 && frm.doc.status !== 'Completed') {
            frm.dashboard.add_comment(
                `⚠️ <b>Overdue by ${frm.doc.overdue_days} day(s)</b> — Due: ${frm.doc.due_date}`,
                'red', true
            );
        }
    },

    setup_buttons(frm) {
        frm.clear_custom_buttons();
        const draft = frm.doc.docstatus === 0;
        const submitted = frm.doc.docstatus === 1;
        const notNew = !frm.is_new();
        const isClosed = frm.doc.status === 'Completed';

        // ── MANAGER BUTTONS ──────────────────────────────────────────────
        if (TM.isManager() && notNew) {

            // Close Task — only on submitted, not yet completed
            if (submitted && !isClosed) {
                frm.add_custom_button(__('✅ Close Task'), () => {
                    frappe.prompt([
                        {
                            label: 'Manager Review / Comments',
                            fieldname: 'manager_review',
                            fieldtype: 'Text Editor'
                        },
                        {
                            label: 'Quality Score',
                            fieldname: 'quality_score',
                            fieldtype: 'Select',
                            options: '\n5 - Excellent\n4 - Good\n3 - Average\n2 - Below Average\n1 - Poor',
                            reqd: 1,
                            description: 'Used in KPI calculation (20% weight)'
                        }
                    ], (vals) => {
                        frappe.confirm(
                            `Close this task?<br><br>
                            It will be <b>locked in KPI</b> and the employee will be notified.`,
                            () => {
                                frappe.call({
                                    method: 'task_management.task_management.doctype.employee_task.employee_task.close_task',
                                    args: {
                                        task_name: frm.doc.name,
                                        manager_review: vals.manager_review,
                                        quality_score: vals.quality_score
                                    },
                                    callback: () => frm.reload_doc()
                                });
                            }
                        );
                    }, 'Close Task', 'Close & Count in KPI');
                }, 'Actions');
            }

            // Cancel draft task
            if (draft) {
                frm.add_custom_button(__('🚫 Cancel Task'), () => {
                    frappe.confirm('Cancel this task? It will not count in KPI.', () => {
                        frappe.call({
                            method: 'task_management.task_management.doctype.employee_task.employee_task.cancel_task',
                            args: { task_name: frm.doc.name },
                            callback: () => frm.reload_doc()
                        });
                    });
                }, 'Actions');
            }

            // Cancel submitted (open) task
            if (submitted && !isClosed) {
                frm.add_custom_button(__('🚫 Cancel Task'), () => {
                    frappe.confirm('Cancel this assigned task? Employee will be notified.', () => {
                        frappe.call({
                            method: 'task_management.task_management.doctype.employee_task.employee_task.cancel_task',
                            args: { task_name: frm.doc.name },
                            callback: () => frm.reload_doc()
                        });
                    });
                }, 'Actions');
            }
        }

        // ── PROGRESS UPDATE — employees & managers on active submitted tasks ──
        if (notNew && submitted && !isClosed) {
            frm.add_custom_button(__('📝 Add Progress Update'), () => {
                frappe.prompt([
                    {
                        label: 'Progress Note',
                        fieldname: 'update_text',
                        fieldtype: 'Text Editor',
                        reqd: 1
                    },
                    {
                        label: 'Progress %',
                        fieldname: 'percentage',
                        fieldtype: 'Percent',
                        default: frm.doc.completion_percentage || 0,
                        description: 'Update your progress percentage'
                    }
                ], (vals) => {
                    frappe.call({
                        method: 'task_management.task_management.doctype.employee_task.employee_task.add_progress_update',
                        args: {
                            task_name: frm.doc.name,
                            update_text: vals.update_text,
                            percentage: vals.percentage
                        },
                        callback() {
                            frm.reload_doc();
                            frappe.show_alert({ message: '✅ Progress updated', indicator: 'blue' });
                        }
                    });
                }, 'Progress Update', 'Save Update');
            });
        }

        // ── KPI DASHBOARD button ─────────────────────────────────────────
        if (frm.doc.assigned_to && notNew && TM.isManager()) {
            frm.add_custom_button(__('📊 View KPI'), () => {
                frappe.call({
                    method: 'task_management.task_management.doctype.employee_task.employee_task.get_employee_task_summary',
                    args: { employee: frm.doc.assigned_to },
                    callback(r) {
                        const d = r.message;
                        const card = (lbl, val, c) =>
                            `<div style="background:#f5f5f5;border-left:4px solid ${c};
                                padding:10px 14px;border-radius:4px;margin-bottom:6px">
                             <div style="font-size:11px;color:#666">${lbl}</div>
                             <div style="font-size:20px;font-weight:700;color:${c}">${val}</div></div>`;

                        // Task KPI score & color
                        const taskScore  = d.task_kpi_score || 0;
                        const taskGrade  = d.task_kpi_grade || '—';
                        const taskRating = d.task_kpi_rating || '—';
                        const taskColor  = taskScore >= 90 ? '#2e7d32' : taskScore >= 75 ? '#1565C0'
                                         : taskScore >= 60 ? '#f57c00' : '#c62828';

                        // Sales KPI section (only for sales dept)
                        let salesSection = '';
                        if (d.is_sales) {
                            const sScore = d.sales_kpi_score || 0;
                            const sColor = sScore >= 90 ? '#2e7d32' : sScore >= 75 ? '#1565C0'
                                         : sScore >= 60 ? '#f57c00' : '#c62828';
                            salesSection = `
                            <h5 style="margin:16px 0 8px;color:#ff6f00">🎯 Sales KPI</h5>
                            <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:10px">
                                <thead><tr style="background:#fff8e1">
                                    <th style="padding:8px;text-align:left">Metric</th>
                                    <th style="padding:8px;text-align:center">Value</th>
                                    <th style="padding:8px;text-align:center">KPI Score</th>
                                </tr></thead>
                                <tbody>
                                    <tr>
                                        <td style="padding:8px">Sales Target (Period)</td>
                                        <td style="text-align:center">${frappe.format(d.sales_target, {fieldtype:'Currency'})}</td>
                                        <td style="text-align:center" rowspan="3" style="vertical-align:middle">
                                            <span style="font-size:28px;font-weight:700;color:${sColor}">${sScore.toFixed(1)}</span>
                                        </td>
                                    </tr>
                                    <tr style="background:#fafafa">
                                        <td style="padding:8px">Actual Sales (submitted SOs)</td>
                                        <td style="text-align:center">${frappe.format(d.actual_sales, {fieldtype:'Currency'})}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding:8px">Achievement %</td>
                                        <td style="text-align:center"><b>${(d.target_achievement||0).toFixed(1)}%</b></td>
                                    </tr>
                                </tbody>
                                <tfoot><tr style="border-top:2px solid #ffe082">
                                    <td colspan="2" style="padding:8px;font-weight:700">Sales KPI Score (= Achievement %)</td>
                                    <td style="padding:8px;text-align:center;font-size:20px;font-weight:700;color:${sColor}">${sScore.toFixed(1)}</td>
                                </tr></tfoot>
                            </table>
                            <div style="text-align:center;margin-bottom:12px">
                                <span style="background:${sColor};color:#fff;padding:4px 18px;
                                    border-radius:14px;font-weight:600;font-size:13px">
                                    Sales: ${d.sales_kpi_grade} — ${d.sales_kpi_rating}</span>
                            </div>`;
                        }

                        frappe.msgprint(`
                        <h4 style="margin-bottom:12px">${frm.doc.assigned_to_name} — KPI Scorecard
                            ${d.is_sales ? '<span style="background:#ff6f00;color:#fff;font-size:11px;padding:2px 8px;border-radius:10px;margin-left:8px">Sales Team</span>' : ''}
                        </h4>
                        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px">
                            ${card('Total Tasks', d.total_tasks, '#3b5bdb')}
                            ${card('Open', d.open_tasks, '#1565C0')}
                            ${card('Completed', d.completed, '#2e7d32')}
                            ${card('On Time', d.on_time, '#6a1b9a')}
                            ${card('Overdue', d.overdue, '#c62828')}
                            ${card('Late Completed', d.overdue_completed, '#e65100')}
                        </div>

                        <h5 style="margin:0 0 8px;color:#1565C0">📋 Task KPI</h5>
                        <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:10px">
                            <thead><tr style="background:#e3f2fd">
                                <th style="padding:8px;text-align:left">Metric</th>
                                <th style="padding:8px;text-align:center">Score</th>
                                <th style="padding:8px;text-align:center">Weight</th>
                                <th style="padding:8px;text-align:center">Points</th>
                            </tr></thead>
                            <tbody>
                                <tr>
                                    <td style="padding:8px">📋 Completion Rate</td>
                                    <td style="text-align:center">${d.completion_rate}%</td>
                                    <td style="text-align:center">40%</td>
                                    <td style="text-align:center"><b>${(d.completion_rate * 0.40).toFixed(1)}</b></td>
                                </tr>
                                <tr style="background:#fafafa">
                                    <td style="padding:8px">⏱️ On-Time Rate</td>
                                    <td style="text-align:center">${d.on_time_rate}%</td>
                                    <td style="text-align:center">30%</td>
                                    <td style="text-align:center"><b>${(d.on_time_rate * 0.30).toFixed(1)}</b></td>
                                </tr>
                                <tr>
                                    <td style="padding:8px">⭐ Quality Score <small>(avg ${d.avg_quality_rating}/5)</small></td>
                                    <td style="text-align:center">${d.quality_score_100}</td>
                                    <td style="text-align:center">30%</td>
                                    <td style="text-align:center"><b>${(d.quality_score_100 * 0.30).toFixed(1)}</b></td>
                                </tr>
                            </tbody>
                            <tfoot><tr style="border-top:2px solid #90caf9">
                                <td colspan="3" style="padding:8px;font-weight:700">Task KPI Score</td>
                                <td style="padding:8px;text-align:center;font-size:20px;font-weight:700;color:${taskColor}">${taskScore.toFixed(1)}</td>
                            </tr></tfoot>
                        </table>
                        <div style="text-align:center;margin-bottom:14px">
                            <span style="background:${taskColor};color:#fff;padding:4px 18px;
                                border-radius:14px;font-weight:600;font-size:13px">
                                Task: ${taskGrade} — ${taskRating}</span>
                        </div>

                        ${salesSection}
                        `, __('KPI Dashboard'));
                    }
                });
            });
        }
    },

    lock_employee_fields(frm) {
        const submitted = frm.doc.docstatus === 1;
        if (!TM.isManager()) {
            ['task_title','category','priority','assigned_to','assigned_to_name',
             'assigned_to_department','assigned_by','assigned_by_name','manager_department',
             'start_date','due_date','description',
             'quality_score','manager_review','status'].forEach(f => {
                frm.set_df_property(f, 'read_only', 1);
            });
        }
        // Always read-only
        ['assigned_by','assigned_by_name','manager_department',
         'completed_on','days_to_complete','allocated_days',
         'is_overdue','on_time','overdue_days'].forEach(f => {
            frm.set_df_property(f, 'read_only', 1);
        });
        // Lock completion_percentage — only updated via progress button
        frm.set_df_property('completion_percentage', 'read_only', 1);
    },

    render_progress_bar(frm) {
        const pct = Math.min(frm.doc.completion_percentage || 0, 100);
        const color = pct >= 100 ? '#2e7d32' : pct >= 60 ? '#1565C0'
                    : pct >= 30 ? '#f57c00' : '#c62828';
        const $f = frm.get_field('completion_percentage');
        if ($f && !frm.is_new()) {
            setTimeout(() => {
                $f.$wrapper.find('.control-value').html(
                    `<div style="margin:4px 0">
                        <span style="font-size:13px;font-weight:600">${pct}%</span>
                        <div style="background:#e9ecef;border-radius:6px;height:10px;margin-top:4px;overflow:hidden">
                            <div style="width:${pct}%;background:${color};height:100%;border-radius:6px;
                                transition:width 0.4s ease"></div>
                        </div>
                    </div>`
                );
            }, 200);
        }
    }
});
