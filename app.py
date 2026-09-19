from flask import *

app = Flask("__name__")

@app.route("/register",method=["POST"])
def user_based_page():
    fist_name = request.form["first name"]
    last_name = request.form["last name"]
    username = request.form["email"]
    password = request.form["password"]
    role = request.form["option"]
       
