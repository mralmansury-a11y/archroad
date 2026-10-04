# -*- coding: utf-8 -*-
"""وحدة الرواتب: إنشاء كشف شهري، مكافآت/خصومات، اعتماد الدفع، قسيمة راتب، تصدير CSV."""
import csv
import io
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, Response

import db
from core import role_required, valid_month, to_float

bp = Blueprint("payroll", __name__, url_prefix="/payroll")

SELECT = ("SELECT p.*, e.full_name, e.initials, e.employee_code, e.position, d.name AS dept "
          "FROM payroll p JOIN employees e ON e.id=p.employee_id JOIN departments d ON d.id=e.department_id ")


def _net(base, allow, bonus, ded):
    return round(base + allow + bonus - ded, 2)


@bp.route("/")
@role_required("admin", "hr")
def index():
    conn = db.get_db()
    month = valid_month(request.args.get("month"))
    rows = conn.execute(SELECT + "WHERE p.month=? ORDER BY e.full_name", (month,)).fetchall()
    totals = {"base": 0, "allow": 0, "bonus": 0, "ded": 0, "net": 0, "paid": 0}
    for r in rows:
        totals["base"] += r["base_salary"]; totals["allow"] += r["allowance"]
        totals["bonus"] += r["bonus"]; totals["ded"] += r["deductions"]; totals["net"] += r["net"]
        if r["status"] == "paid":
            totals["paid"] += 1
    return render_template("payroll/index.html", rows=rows, month=month, totals=totals)


@bp.route("/generate", methods=["POST"])
@role_required("admin", "hr")
def generate():
    conn = db.get_db()
    month = valid_month(request.form.get("month"))
    emps = conn.execute(
        "SELECT id, base_salary, allowance FROM employees WHERE status != 'منتهي' AND id NOT IN "
        "(SELECT employee_id FROM payroll WHERE month=?)", (month,)).fetchall()
    for e in emps:
        absent = conn.execute("SELECT COUNT(*) AS c FROM attendance WHERE employee_id=? AND status='absent' AND day LIKE ?",
                              (e["id"], month + "-%")).fetchone()["c"]
        unpaid = conn.execute("SELECT COALESCE(SUM(days),0) AS s FROM leave_requests WHERE employee_id=? AND "
                              "leave_type='بدون راتب' AND status='approved' AND start_date LIKE ?",
                              (e["id"], month + "-%")).fetchone()["s"]
        ded = round((absent + unpaid) * (e["base_salary"] / 30.0), 2)
        conn.execute(
            "INSERT INTO payroll (employee_id, month, base_salary, allowance, bonus, deductions, net) VALUES (?,?,?,?,0,?,?)",
            (e["id"], month, e["base_salary"], e["allowance"], ded, _net(e["base_salary"], e["allowance"], 0, ded)))
    conn.commit()
    flash("تم إنشاء %d قسيمة راتب لشهر %s" % (len(emps), month) if emps else "كشف هذا الشهر مكتمل مسبقاً",
          "success" if emps else "error")
    return redirect(url_for("payroll.index", month=month))


@bp.route("/<int:pid>/update", methods=["POST"])
@role_required("admin", "hr")
def update(pid):
    conn = db.get_db()
    p = conn.execute("SELECT * FROM payroll WHERE id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    if p["status"] == "paid":
        flash("لا يمكن تعديل قسيمة مدفوعة", "error")
    else:
        bonus, ded = to_float(request.form.get("bonus")), to_float(request.form.get("deductions"))
        conn.execute("UPDATE payroll SET bonus=?, deductions=?, net=? WHERE id=?",
                     (bonus, ded, _net(p["base_salary"], p["allowance"], bonus, ded), pid))
        conn.commit()
        flash("تم تحديث القسيمة", "success")
    return redirect(url_for("payroll.index", month=p["month"]))


@bp.route("/<int:pid>/pay", methods=["POST"])
@role_required("admin", "hr")
def pay(pid):
    conn = db.get_db()
    p = conn.execute("SELECT month FROM payroll WHERE id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    conn.execute("UPDATE payroll SET status='paid', paid_at=? WHERE id=? AND status='draft'",
                 (datetime.now().strftime("%Y-%m-%d %H:%M"), pid))
    conn.commit()
    flash("تم اعتماد الدفع", "success")
    return redirect(url_for("payroll.index", month=p["month"]))


@bp.route("/pay-all", methods=["POST"])
@role_required("admin", "hr")
def pay_all():
    conn = db.get_db()
    month = valid_month(request.form.get("month"))
    cur = conn.execute("UPDATE payroll SET status='paid', paid_at=? WHERE month=? AND status='draft'",
                       (datetime.now().strftime("%Y-%m-%d %H:%M"), month))
    conn.commit()
    flash("تم اعتماد دفع %d قسيمة" % cur.rowcount, "success")
    return redirect(url_for("payroll.index", month=month))


@bp.route("/<int:pid>/delete", methods=["POST"])
@role_required("admin", "hr")
def delete(pid):
    conn = db.get_db()
    p = conn.execute("SELECT month FROM payroll WHERE id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    conn.execute("DELETE FROM payroll WHERE id=? AND status='draft'", (pid,))
    conn.commit()
    flash("تم حذف المسودة (يمكن إعادة إنشائها)", "success")
    return redirect(url_for("payroll.index", month=p["month"]))


@bp.route("/<int:pid>/slip")
@role_required("admin", "hr")
def slip(pid):
    p = db.get_db().execute(SELECT + "WHERE p.id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    return render_template("payroll/slip.html", p=p)


@bp.route("/export.csv")
@role_required("admin", "hr")
def export():
    month = valid_month(request.args.get("month"))
    rows = db.get_db().execute(SELECT + "WHERE p.month=? ORDER BY e.full_name", (month,)).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["الرقم الوظيفي", "الموظف", "القسم", "الأساسي", "البدلات", "المكافآت", "الخصومات", "الصافي", "الحالة"])
    for r in rows:
        w.writerow([r["employee_code"], r["full_name"], r["dept"], r["base_salary"], r["allowance"], r["bonus"],
                    r["deductions"], r["net"], "مدفوع" if r["status"] == "paid" else "مسودة"])
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=payroll-%s.csv" % month})
