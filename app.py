from flask import *
import sqlite3

app = Flask("__name__")
app.secret_key = "8k4kYOYOYOYO"

@app.route("/")
def home_page():
    return render_template("index.html")

@app.route("/login",methods=["POST"])
def login():
    print("login route called")
    username = request.form['username']
    password = request.form['password']
    conn = sqlite3.connect("database/vote_man.db")
    user  = conn.execute("select user_id,ROLE from newuser where username=? and password=?",(username,password)).fetchone() 

    if user:
        user_id = user[0]
        role = user[1]
        session['user_id'] = user_id
        session['role'] = role
        conn.execute("update newuser set last_login=CURRENT_TIMESTAMP where user_id=?",(user_id,))
        conn.commit()
    conn.close()
    if user and role == "voter":
        return render_template("voter.html",username=username)
    return "invalid username or password"

@app.route("/voter",methods=["POST"])
def voter():
    user_id = session['user_id']
    phone = request.form["phone"]
    city = request.form["city"]
    address = request.form["address"]
    state = request.form["state"]
    country = request.form["country"]
    conn = sqlite3.connect("database/voter.db")
    conn.execute("""
    INSERT INTO voters (user_id, phone, adress, city, state, country)
    VALUES (?, ?, ?, ?, ?, ?)""", (user_id, phone, address, city, state, country))
    return jsonify({"message":"updated info"})

@app.route("/register")
def register_page():
    return render_template("register.html")

@app.route("/register/data",methods=["POST"])
def data():
    conn = sqlite3.connect("database/vote_man.db")
    conn.row_factory = sqlite3.Row
    first_name = request.form["first name"]
    last_name = request.form["last name"]
    username = request.form["username"]
    email = request.form["email"]
    password = request.form["password"]
    role = request.form["option"]
    conn.execute("""insert into newuser ("first_name","last_name","username","email","password","ROLE")values (?,?,?,?,?,?)""",(first_name,last_name,username,email,password,role)) 
    conn.commit()
    voter  = conn.execute("select * from newuser").fetchall()
    conn.close()
    l = []
    for i in voter:
        l.append({  "fname":i['first_name'],
                    "lname":i['last_name'],
                    "user_name":i['username'],
                    "email":i['email'],
                    "password":i['password'],
                    "role":i['ROLE'],
                    "register date":i['date_joined'],
                    "login date":i['last_login']})

    return jsonify({"message":"data added successfully",
                    "data":l})


if __name__ == '__main__':
    print(app.url_map)
    app.run(debug=True)



