# -*- coding: utf-8 -*-
"""وحدة المستخدمين (للمسؤول) + صفحة حسابي (تغيير كلمة المرور لأي مستخدم)."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

import db
from core import login_required, role_required, employees_options

bp = Blueprint("users", __name__)
ROLES = [("hr", "موارد بشرية"), ("admin", "مسؤول نظام")]


@bp.route("/users")
@role_required("admin")
def index():
    rows = db.get_db().execute(
        "SELECT u.*, e.full_name FROM users u LEFT JOIN employees e ON e.id=u.employee_id ORDER BY u.id").fetchall()
    return render_template("users/index.html", rows=rows, roles=dict(ROLES))


@bp.route("/users/new", methods=["GET", "POST"])
@role_required("admin")
def new():
    conn = db.get_db()
    form = {"role": "hr"}
    if request.method == "POST":
        f = request.form
        form = {k: f.get(k, "").strip() for k in ("username", "role", "employee_id")}
        pw = f.get("password", "")
        if len(form["username"]) < 3 or form["role"] not in dict(ROLES):
            flash("اسم المستخدم (3 أحرف على الأقل) والدور مطلوبان", "error")
        elif len(pw) < 8:
            flash("كلمة المرور يجب ألا تقل عن 8 أحرف", "error")
        elif conn.execute("SELECT 1 FROM users WHERE username=?", (form["username"],)).fetchone():
            flash("اسم المستخدم مستخدم مسبقاً", "error")
        else:
            conn.execute("INSERT INTO users (username, password_hash, role, employee_id) VALUES (?,?,?,?)",
                         (form["username"], generate_password_hash(pw), form["role"],
                          int(form["employee_id"]) if form["employee_id"].isdigit() else None))
            conn.commit()
            flash("تم إنشاء المستخدم", "success")
            return redirect(url_for("users.index"))
    return render_template("users/form.html", form=form, roles=ROLES, emps=employees_options(conn))


@bp.route("/users/<int:uid>/reset", methods=["POST"])
@role_required("admin")
def reset(uid):
    pw = request.form.get("password", "")
    if len(pw) < 8:
        flash("كلمة المرور يجب ألا تقل عن 8 أحرف", "error")
    else:
        conn = db.get_db()
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(pw), uid))
        conn.commit()
        flash("تم تعيين كلمة مرور جديدة", "success")
    return redirect(url_for("users.index"))


@bp.route("/users/<int:uid>/delete", methods=["POST"])
@role_required("admin")
def delete(uid):
    if uid == session.get("user_id"):
        flash("لا يمكنك حذف حسابك الحالي", "error")
    else:
        conn = db.get_db()
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
        conn.commit()
        flash("تم حذف المستخدم", "success")
    return redirect(url_for("users.index"))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        conn = db.get_db()
        u = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        old, new, again = (request.form.get(k, "") for k in ("old", "new", "again"))
        if not check_password_hash(u["password_hash"], old):
            flash("كلمة المرور الحالية غير صحيحة", "error")
        elif len(new) < 8:
            flash("كلمة المرور الجديدة يجب ألا تقل عن 8 أحرف", "error")
        elif new != again:
            flash("كلمتا المرور غير متطابقتين", "error")
        else:
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), u["id"]))
            conn.commit()
            flash("تم تغيير كلمة المرور", "success")
            return redirect(url_for("users.account"))
    return render_template("users/account.html")
