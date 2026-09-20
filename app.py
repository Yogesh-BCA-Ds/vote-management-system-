from flask import *

app = Flask("__name__")

@app.route("/")
def home_page():
    return render_template("index.html")

@app.route("/register")
def register_page():
    return render_template("register.html")

@app.route("/data",methods=["POST"])
def data():
    fist_name = request.form["first name"]
    last_name = request.form["last name"]
    username = request.form["username"]
    email = request.form["email"]
    password = request.form["password"]
    role = request.form["option"]
    return jsonify({"message":"successfull",
                    "fname":first_name,
                    "lname":last_name,
                    "user_name":username,
                    "email":email,
                    "password":password,
                    "role":role})
if __name__ == '__main__':
    app.run(debug=True)
