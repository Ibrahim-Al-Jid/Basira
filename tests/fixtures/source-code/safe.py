import os, secrets, subprocess, shlex, html
from flask import Flask, request, redirect, url_for, abort
from werkzeug.utils import secure_filename
from markupsafe import escape
app = Flask(__name__)

@app.route("/user")
def user():
    uid = int(request.args.get("id"))
    cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
    return "<h1>Hello " + escape(request.args.get("name")) + "</h1>"

@app.route("/ping")
def ping():
    host = request.form["host"]
    if host not in ("a.example", "b.example"):
        abort(400)
    subprocess.run(["ping", "-c", "1", host])
    os.system("ping " + shlex.quote(request.form["x"]))

@app.route("/go")
def go():
    nxt = request.args.get("next")
    if nxt not in ALLOWED:
        abort(400)
    return redirect(nxt)

def tok():
    return secrets.token_hex(16)

@app.route("/up", methods=["POST"])
def up():
    f = request.files["file"]
    if not f.filename.endswith(".png"):
        abort(400)
    f.save("/uploads/" + secure_filename(f.filename))

def cookie(resp):
    resp.set_cookie("session", "abc", secure=True, httponly=True)
