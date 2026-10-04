# -*- coding: utf-8 -*-
"""وحدة مستندات الموظفين: رفع (PDF / JPG / JPEG / PNG)، عرض وتنزيل، حذف.

الملفات تُحفظ خارج مجلد static داخل instance/uploads/<رقم الموظف>/ بأسماء عشوائية،
ولا تُقدَّم إلا عبر مسار يتطلب تسجيل الدخول. يُتحقق من الامتداد ومن محتوى الملف الفعلي.
"""
import os
import re
import secrets
import shutil
from datetime import datetime

from flask import Blueprint, request, redirect, url_for, flash, abort, send_from_directory, session

import db
from core import login_required

bp = Blueprint("documents", __name__, url_prefix="/employees/<int:emp_id>/documents")

UPLOAD_DIR = os.path.join(os.path.dirname(db.DB_PATH), "uploads")
DOC_TYPES = [("passport", "جواز السفر"), ("national_id", "الرقم الوطني"),
             ("photo", "صورة شخصية"), ("contract", "عقد العمل")]
TYPE_KEYS = [k for k, _ in DOC_TYPES]
ALLOWED_EXT = {"pdf": "pdf", "jpg": "jpg", "jpeg": "jpg", "png": "png"}
MIME = {"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png"}
MAX_BYTES = 5 * 1024 * 1024
IMAGE_KINDS = ("jpg", "png")


def _sniff(head):
    """نوع الملف الحقيقي من أول بايتات المحتوى."""
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    return None


def _clean_name(name):
    name = os.path.basename((name or "").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:120] or "ملف"


def _folder(emp_id):
    return os.path.join(UPLOAD_DIR, str(int(emp_id)))


def purge_employee_files(emp_id):
    shutil.rmtree(_folder(emp_id), ignore_errors=True)


@bp.route("/upload", methods=["POST"])
@login_required
def upload(emp_id):
    conn = db.get_db()
    if not conn.execute("SELECT 1 FROM employees WHERE id=?", (emp_id,)).fetchone():
        abort(404)
    back = redirect(url_for("employees.view", emp_id=emp_id) + "#documents")
    dtype = request.form.get("doc_type", "")
    if dtype not in TYPE_KEYS:
        flash("اختر نوع المستند", "error")
        return back
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files:
        flash("اختر ملفاً واحداً على الأقل", "error")
        return back

    os.makedirs(_folder(emp_id), exist_ok=True)
    saved = 0
    for f in files:
        orig = _clean_name(f.filename)
        ext = orig.rsplit(".", 1)[-1].lower() if "." in orig else ""
        if ext not in ALLOWED_EXT:
            flash("«%s»: الصيغة غير مسموحة (المسموح: PDF, JPG, JPEG, PNG)" % orig, "error")
            continue
        data = f.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            flash("«%s»: حجم الملف يتجاوز 5 ميجابايت" % orig, "error")
            continue
        if not data:
            flash("«%s»: الملف فارغ" % orig, "error")
            continue
        kind = _sniff(data[:16])
        if kind is None or kind != ALLOWED_EXT[ext]:
            flash("«%s»: محتوى الملف لا يطابق صيغته" % orig, "error")
            continue
        if dtype == "photo" and kind not in IMAGE_KINDS:
            flash("«%s»: الصورة الشخصية يجب أن تكون JPG أو PNG" % orig, "error")
            continue
        stored = "%s.%s" % (secrets.token_hex(16), kind)
        with open(os.path.join(_folder(emp_id), stored), "wb") as out:
            out.write(data)
        conn.execute(
            "INSERT INTO employee_documents (employee_id, doc_type, original_name, stored_name, kind, size, uploaded_at, uploaded_by) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (emp_id, dtype, orig, stored, kind, len(data),
             datetime.now().strftime("%Y-%m-%d %H:%M"), session.get("username")))
        saved += 1
    conn.commit()
    if saved:
        flash("تم رفع %d مستند بنجاح" % saved, "success")
    return back


@bp.route("/<int:doc_id>")
@login_required
def file(emp_id, doc_id):
    d = db.get_db().execute("SELECT * FROM employee_documents WHERE id=? AND employee_id=?", (doc_id, emp_id)).fetchone()
    if not d or not os.path.isfile(os.path.join(_folder(emp_id), d["stored_name"])):
        abort(404)
    resp = send_from_directory(_folder(emp_id), d["stored_name"], mimetype=MIME[d["kind"]],
                               as_attachment=request.args.get("dl") == "1", download_name=d["original_name"])
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
    return resp


@bp.route("/<int:doc_id>/delete", methods=["POST"])
@login_required
def delete(emp_id, doc_id):
    conn = db.get_db()
    d = conn.execute("SELECT * FROM employee_documents WHERE id=? AND employee_id=?", (doc_id, emp_id)).fetchone()
    if not d:
        abort(404)
    conn.execute("DELETE FROM employee_documents WHERE id=?", (doc_id,))
    conn.commit()
    try:
        os.remove(os.path.join(_folder(emp_id), d["stored_name"]))
    except OSError:
        pass
    flash("تم حذف المستند", "success")
    return redirect(url_for("employees.view", emp_id=emp_id) + "#documents")
