# -*- coding: utf-8 -*-
"""وحدة الإجازات: الطلبات، أرصدة الإجازة السنوية، القبول/الرفض، الإلغاء."""
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash

import db
import core
from core import login_required, safe_date, employees_options, annual_used, ANNUAL_QUOTA

bp = Blueprint("leaves", __name__, url_prefix="/leaves")
TYPES = ["سنوية", "مرضية", "طارئة", "بدون راتب", "أمومة", "دراسية"]


@bp.route("/")
@login_required
def index():
    conn = db.get_db()
    status = request.args.get("status", "")
    sql = ("SELECT lr.*, e.full_name, e.initials FROM leave_requests lr "
           "JOIN employees e ON e.id = lr.employee_id WHERE 1=1")
    params = []
    if status in ("pending", "approved", "rejected"):
        sql += " AND lr.status = ?"
        params.append(status)
    sql += " ORDER BY CASE lr.status WHEN 'pending' THEN 0 ELSE 1 END, lr.created_at DESC, lr.id DESC"
    rows = conn.execute(sql, params).fetchall()
    balances = []
    for e in conn.execute("SELECT id, full_name, initials FROM employees WHERE status != 'منتهي' ORDER BY full_name"):
        used = annual_used(conn, e["id"])
        balances.append({"id": e["id"], "full_name": e["full_name"], "initials": e["initials"],
                         "used": used, "left": ANNUAL_QUOTA - used})
    return render_template("leaves/index.html", rows=rows, status=status, balances=balances, quota=ANNUAL_QUOTA)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    conn = db.get_db()
    form = {"leave_type": "سنوية", "start_date": date.today().isoformat(), "end_date": date.today().isoformat()}
    if request.method == "POST":
        f = request.form
        form = {k: f.get(k, "").strip() for k in ("employee_id", "leave_type", "start_date", "end_date", "reason")}
        errors = []
        s, e = safe_date(form["start_date"]), safe_date(form["end_date"])
        if not form["employee_id"].isdigit():
            errors.append("اختر الموظف")
        if form["leave_type"] not in TYPES:
            errors.append("نوع الإجازة غير صالح")
        if not s or not e:
            errors.append("التواريخ غير صالحة")
        elif e < s:
            errors.append("تاريخ النهاية يجب أن يكون بعد تاريخ البداية")
        if not errors:
            days = (e - s).days + 1
            if form["leave_type"] == "سنوية":
                left = ANNUAL_QUOTA - annual_used(conn, int(form["employee_id"]), s.year)
                if days > left:
                    errors.append("الرصيد السنوي المتبقي (%d يوم) لا يكفي لهذا الطلب (%d يوم)" % (left, days))
        if not errors:
            conn.execute(
                "INSERT INTO leave_requests (employee_id, leave_type, start_date, end_date, days, status, created_at, reason) "
                "VALUES (?,?,?,?,?,'pending',?,?)",
                (int(form["employee_id"]), form["leave_type"], form["start_date"], form["end_date"], days,
                 date.today().isoformat(), form["reason"]))
            conn.commit()
            flash("تم تقديم طلب الإجازة (%d يوم)" % days, "success")
            return redirect(url_for("leaves.index"))
        for m in errors:
            flash(m, "error")
    return render_template("leaves/form.html", form=form, types=TYPES, emps=employees_options(conn))


@bp.route("/<int:rid>/<string:decision>", methods=["POST"])
@login_required
def decide(rid, decision):
    if decision not in ("approve", "reject"):
        flash("إجراء غير معروف", "error")
    elif core.decide_leave(db.get_db(), rid, decision):
        flash("تم تحديث حالة الطلب", "success")
    else:
        flash("الطلب غير موجود أو تمت معالجته مسبقاً", "error")
    return redirect(url_for("leaves.index", status=request.form.get("status", "")))


@bp.route("/<int:rid>/delete", methods=["POST"])
@login_required
def delete(rid):
    conn = db.get_db()
    cur = conn.execute("DELETE FROM leave_requests WHERE id=? AND status='pending'", (rid,))
    conn.commit()
    flash("تم إلغاء الطلب" if cur.rowcount else "يمكن إلغاء الطلبات المعلّقة فقط", "success" if cur.rowcount else "error")
    return redirect(url_for("leaves.index"))
