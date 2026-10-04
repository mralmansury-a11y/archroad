# -*- coding: utf-8 -*-
"""وحدة التوظيف: الوظائف الشاغرة، لوحة المرشحين بمراحل، والتعيين المباشر كموظف."""
from datetime import date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort

import db
from core import login_required, department_options, make_initials, next_employee_code

bp = Blueprint("recruitment", __name__, url_prefix="/recruitment")
STAGES = [("new", "جديد"), ("interview", "مقابلة"), ("offer", "عرض وظيفي"), ("hired", "تم التعيين"), ("rejected", "مرفوض")]
STAGE_KEYS = [s[0] for s in STAGES]


@bp.route("/")
@login_required
def index():
    conn = db.get_db()
    job = request.args.get("job", "")
    jobs = conn.execute(
        """SELECT j.*, d.name AS dept, (SELECT COUNT(*) FROM candidates c WHERE c.job_id=j.id) AS cand_count
           FROM job_postings j JOIN departments d ON d.id=j.department_id ORDER BY j.status ASC, j.id DESC""").fetchall()
    sql = "SELECT c.*, j.title AS job_title FROM candidates c JOIN job_postings j ON j.id=c.job_id"
    params = []
    if job.isdigit():
        sql += " WHERE c.job_id=?"
        params.append(int(job))
    cands = conn.execute(sql + " ORDER BY c.id DESC", params).fetchall()
    board = {k: [c for c in cands if c["stage"] == k] for k in STAGE_KEYS}
    return render_template("recruitment/index.html", jobs=jobs, board=board, stages=STAGES, job=job)


@bp.route("/jobs/new", methods=["GET", "POST"])
@login_required
def job_new():
    conn = db.get_db()
    form = {"openings": 1}
    if request.method == "POST":
        f = request.form
        form = {k: f.get(k, "").strip() for k in ("title", "department_id", "openings", "description")}
        if not form["title"] or not form["department_id"].isdigit():
            flash("عنوان الوظيفة والقسم مطلوبان", "error")
        else:
            n = int(form["openings"]) if form["openings"].isdigit() and int(form["openings"]) > 0 else 1
            conn.execute("INSERT INTO job_postings (title, department_id, openings, description, created_at) VALUES (?,?,?,?,?)",
                         (form["title"], int(form["department_id"]), n, form["description"], date.today().isoformat()))
            conn.commit()
            flash("تم نشر الوظيفة", "success")
            return redirect(url_for("recruitment.index"))
    return render_template("recruitment/job_form.html", form=form, departments=department_options(conn))


@bp.route("/jobs/<int:jid>/toggle", methods=["POST"])
@login_required
def job_toggle(jid):
    conn = db.get_db()
    conn.execute("UPDATE job_postings SET status = CASE status WHEN 'open' THEN 'closed' ELSE 'open' END WHERE id=?", (jid,))
    conn.commit()
    return redirect(url_for("recruitment.index"))


@bp.route("/jobs/<int:jid>/delete", methods=["POST"])
@login_required
def job_delete(jid):
    conn = db.get_db()
    if conn.execute("SELECT COUNT(*) AS c FROM candidates WHERE job_id=?", (jid,)).fetchone()["c"]:
        flash("لا يمكن حذف وظيفة لها مرشحون؛ أغلقها بدلاً من ذلك", "error")
    else:
        conn.execute("DELETE FROM job_postings WHERE id=?", (jid,))
        conn.commit()
        flash("تم حذف الوظيفة", "success")
    return redirect(url_for("recruitment.index"))


@bp.route("/candidates/new", methods=["GET", "POST"])
@login_required
def cand_new():
    conn = db.get_db()
    jobs = [(j["id"], j["title"]) for j in conn.execute("SELECT id, title FROM job_postings WHERE status='open' ORDER BY title")]
    form = {"job_id": request.args.get("job", "")}
    if request.method == "POST":
        f = request.form
        form = {k: f.get(k, "").strip() for k in ("job_id", "full_name", "phone", "email", "notes")}
        if not form["full_name"] or not form["job_id"].isdigit():
            flash("اسم المرشح والوظيفة مطلوبان", "error")
        else:
            conn.execute("INSERT INTO candidates (job_id, full_name, phone, email, notes, created_at) VALUES (?,?,?,?,?,?)",
                         (int(form["job_id"]), form["full_name"], form["phone"], form["email"], form["notes"], date.today().isoformat()))
            conn.commit()
            flash("تمت إضافة المرشح", "success")
            return redirect(url_for("recruitment.index"))
    return render_template("recruitment/candidate_form.html", form=form, jobs=jobs)


@bp.route("/candidates/<int:cid>/stage", methods=["POST"])
@login_required
def cand_stage(cid):
    conn = db.get_db()
    stage = request.form.get("stage", "")
    c = conn.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone()
    if not c or stage not in STAGE_KEYS:
        abort(404)
    conn.execute("UPDATE candidates SET stage=? WHERE id=?", (stage, cid))
    msg = "تم نقل المرشح"
    if stage == "hired" and not c["employee_id"]:
        job = conn.execute("SELECT * FROM job_postings WHERE id=?", (c["job_id"],)).fetchone()
        code = next_employee_code(conn)
        today = date.today()
        cur = conn.execute(
            """INSERT INTO employees (employee_code, full_name, initials, department_id, position, hire_date,
               contract_type, contract_end_date, status, phone, email) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (code, c["full_name"], make_initials(c["full_name"]), job["department_id"], job["title"],
             today.isoformat(), "تجربة", (today + timedelta(days=90)).isoformat(), "نشط", c["phone"], c["email"]))
        conn.execute("UPDATE candidates SET employee_id=? WHERE id=?", (cur.lastrowid, cid))
        msg = "تم التعيين وإنشاء ملف الموظف %s (عقد تجربة 90 يوماً) — أكمل الراتب من ملفه" % code
    conn.commit()
    flash(msg, "success")
    return redirect(url_for("recruitment.index", job=request.form.get("job", "")))


@bp.route("/candidates/<int:cid>/delete", methods=["POST"])
@login_required
def cand_delete(cid):
    conn = db.get_db()
    conn.execute("DELETE FROM candidates WHERE id=?", (cid,))
    conn.commit()
    flash("تم حذف المرشح", "success")
    return redirect(url_for("recruitment.index"))
