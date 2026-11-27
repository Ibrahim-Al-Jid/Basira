import os, pickle, subprocess, random, sqlite3, yaml
import requests
from flask import Flask, request, redirect, render_template_string, make_response, send_file

app = Flask(__name__)

@app.route("/user")
def user():
    uid = request.args.get("id")
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE id = '%s'" % uid)
    cur.execute(f"SELECT * FROM users WHERE name = '{request.args['name']}'")
    return "<h1>Hello " + request.args.get("name") + "</h1>"

@app.route("/ping")
def ping():
    host = request.form["host"]
    os.system("ping -c 1 " + host)
    subprocess.run(f"nslookup {host}", shell=True)

@app.route("/go")
def go():
    return redirect(request.args.get("next"))

@app.route("/file")
def file():
    name = request.args["f"]
    return send_file(os.path.join("/srv", name))

@app.route("/fetch")
def fetch():
    return requests.get(request.args.get("url")).text

@app.route("/load", methods=["POST"])
def load():
    obj = pickle.loads(request.data)
    cfg = yaml.load(request.data)
    tpl = render_template_string("Hi " + request.args.get("n"))
    eval(request.args["expr"])

@app.route("/up", methods=["POST"])
def up():
    f = request.files["file"]
    f.save("/uploads/" + f.filename)

def make_token():
    token = str(random.randint(0, 999999))
    return token

def cookie():
    resp = make_response("x")
    resp.set_cookie("session", "abc")
    requests.get("https://x", verify=False)
    return resp
