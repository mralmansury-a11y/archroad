# -*- coding: utf-8 -*-
"""وحدة الموظفين: بحث/فلترة، إضافة، تعديل، ملف الموظف، حذف."""
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort

import db
from modules.documents import DOC_TYPES, purge_employee_files
from core import (login_required, role_required, safe_date, to_float, make_initials,
                  next_employee_code, department_options, annual_used, ANNUAL_QUOTA)

bp = Blueprint("employees", __name__, url_prefix="/employees")
CONTRACTS = ["دائم", "مؤقت", "تجربة", "عقد خدمة"]
STATUSES = ["نشط", "إجازة", "موقوف", "منتهي"]


def _form():
    f = request.form
    d = {
        "full_name": f.get("full_name", "").strip(),
        "department_id": f.get("department_id", "").strip(),
        "position": f.get("position", "").strip(),
        "hire_date": f.get("hire_date", "").strip(),
        "contract_type": f.get("contract_type", "دائم"),
        "contract_end_date": f.get("contract_end_date", "").strip() or None,
        "status": f.get("status", "نشط"),
        "phone": f.get("phone", "").strip(),
        "email": f.get("email", "").strip(),
        "base_salary": to_float(f.get("base_salary")),
        "allowance": to_float(f.get("allowance")),
    }
    errors = []
    if not d["full_name"]:
        errors.append("الاسم الكامل مطلوب")
    if not d["department_id"].isdigit():
        errors.append("اختر القسم")
    if not d["position"]:
        errors.append("المسمى الوظيفي مطلوب")
    if not safe_date(d["hire_date"]):
        errors.append("تاريخ التعيين غير صالح")
    if d["contract_end_date"] and not safe_date(d["contract_end_date"]):
        errors.append("تاريخ انتهاء العقد غير صالح")
    if d["contract_type"] not in CONTRACTS:
        errors.append("نوع العقد غير صالح")
    if d["status"] not in STATUSES:
        errors.append("الحالة غير صالحة")
    return d, errors


@bp.route("/")
@login_required
def index():
    conn = db.get_db()
    q = request.args.get("q", "").strip()
    dept = request.args.get("dept", "")
    status = request.args.get("status", "")
    sql = ("SELECT e.*, d.name AS department_name FROM employees e "
           "JOIN departments d ON d.id = e.department_id WHERE 1=1")
    params = []
    if q:
        sql += " AND (e.full_name LIKE ? OR e.employee_code LIKE ? OR e.position LIKE ?)"
        params += ["%" + q + "%"] * 3
    if dept.isdigit():
        sql += " AND e.department_id = ?"
        params.append(int(dept))
    if status in STATUSES:
        sql += " AND e.status = ?"
        params.append(status)
    sql += " ORDER BY e.full_name"
    rows = conn.execute(sql, params).fetchall()
    return render_template("employees/list.html", rows=rows, q=q, dept=dept, status=status,
                           departments=department_options(conn), statuses=STATUSES)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    conn = db.get_db()
    if request.method == "POST":
        d, errors = _form()
        if not errors:
            code = next_employee_code(conn)
            cur = conn.execute(
                """INSERT INTO employees (employee_code, full_name, initials, department_id, position,
                   hire_date, contract_type, contract_end_date, status, phone, email, base_salary, allowance)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (code, d["full_name"], make_initials(d["full_name"]), int(d["department_id"]), d["position"],
                 d["hire_date"], d["contract_type"], d["contract_end_date"], d["status"], d["phone"],
                 d["email"], d["base_salary"], d["allowance"]))
            conn.commit()
            flash("تمت إضافة الموظف (%s) بنجاح" % code, "success")
            return redirect(url_for("employees.view", emp_id=cur.lastrowid))
        for e in errors:
            flash(e, "error")
        emp = d
    else:
        emp = {"hire_date": date.today().isoformat(), "contract_type": "دائم", "status": "نشط"}
    return render_template("employees/form.html", emp=emp, departments=department_options(conn),
                           contracts=CONTRACTS, statuses=STATUSES, editing=False)


@bp.route("/<int:emp_id>")
@login_required
def view(emp_id):
    conn = db.get_db()
    emp = conn.execute(
        "SELECT e.*, d.name AS department_name FROM employees e JOIN departments d ON d.id=e.department_id WHERE e.id=?",
        (emp_id,)).fetchone()
    if not emp:
        abort(404)
    leaves = conn.execute("SELECT * FROM leave_requests WHERE employee_id=? ORDER BY start_date DESC LIMIT 8", (emp_id,)).fetchall()
    att = conn.execute("SELECT * FROM attendance WHERE employee_id=? ORDER BY day DESC LIMIT 10", (emp_id,)).fetchall()
    reviews = conn.execute("SELECT * FROM performance_reviews WHERE employee_id=? ORDER BY id DESC LIMIT 5", (emp_id,)).fetchall()
    slips = conn.execute("SELECT * FROM payroll WHERE employee_id=? ORDER BY month DESC LIMIT 6", (emp_id,)).fetchall()
    trainings = conn.execute(
        "SELECT t.title, t.start_date, te.status FROM training_enrollments te JOIN trainings t ON t.id=te.training_id "
        "WHERE te.employee_id=? ORDER BY t.start_date DESC", (emp_id,)).fetchall()
    used = annual_used(conn, emp_id)
    docs = conn.execute("SELECT * FROM employee_documents WHERE employee_id=? ORDER BY id DESC", (emp_id,)).fetchall()
    photo = next((d for d in docs if d["doc_type"] == "photo"), None)
    have = {d["doc_type"] for d in docs}
    return render_template("employees/view.html", emp=emp, leaves=leaves, att=att, reviews=reviews,
                           slips=slips, trainings=trainings, used=used, quota=ANNUAL_QUOTA,
                           docs=docs, doc_types=DOC_TYPES, photo=photo,
                           docs_done=sum(1 for k, _ in DOC_TYPES if k in have))


@bp.route("/<int:emp_id>/edit", methods=["GET", "POST"])
@login_required
def edit(emp_id):
    conn = db.get_db()
    emp = conn.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
    if not emp:
        abort(404)
    if request.method == "POST":
        d, errors = _form()
        if not errors:
            conn.execute(
                """UPDATE employees SET full_name=?, initials=?, department_id=?, position=?, hire_date=?,
                   contract_type=?, contract_end_date=?, status=?, phone=?, email=?, base_salary=?, allowance=?
                   WHERE id=?""",
                (d["full_name"], make_initials(d["full_name"]), int(d["department_id"]), d["position"],
                 d["hire_date"], d["contract_type"], d["contract_end_date"], d["status"], d["phone"],
                 d["email"], d["base_salary"], d["allowance"], emp_id))
            conn.commit()
            flash("تم حفظ التعديلات", "success")
            return redirect(url_for("employees.view", emp_id=emp_id))
        for e in errors:
            flash(e, "error")
        emp = dict(d, id=emp_id, employee_code=emp["employee_code"])
    return render_template("employees/form.html", emp=emp, departments=department_options(conn),
                           contracts=CONTRACTS, statuses=STATUSES, editing=True)


@bp.route("/<int:emp_id>/delete", methods=["POST"])
@role_required("admin")
def delete(emp_id):
    conn = db.get_db()
    if not conn.execute("SELECT 1 FROM employees WHERE id=?", (emp_id,)).fetchone():
        abort(404)
    for t in ("attendance", "leave_requests", "payroll", "performance_reviews", "training_enrollments", "employee_documents"):
        conn.execute("DELETE FROM %s WHERE employee_id=?" % t, (emp_id,))
    conn.execute("UPDATE users SET employee_id=NULL WHERE employee_id=?", (emp_id,))
    conn.execute("UPDATE candidates SET employee_id=NULL WHERE employee_id=?", (emp_id,))
    conn.execute("DELETE FROM employees WHERE id=?", (emp_id,))
    conn.commit()
    purge_employee_files(emp_id)
    flash("تم حذف الموظف وكل سجلاته", "success")
    return redirect(url_for("employees.index"))
