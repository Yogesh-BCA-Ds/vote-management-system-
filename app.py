from flask import *
from datetime import datetime
import sqlite3
import re 

app = Flask("__name__")
app.secret_key = "8k4kYOYOYOYO"

def valid_name(value):
    return bool(value and re.fullmatch(r"[A-Za-z][A-Za-z '\-]*", value))


def valid_email(value):
    return bool(
        len(value) <= 254
        and re.fullmatch(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            value
        )
    )


def get_username():
    user_id = session.get("user_id")

    if not user_id:
        return None

    conn = sqlite3.connect("database/vote_man.db")
    row = conn.execute(
        "SELECT username FROM newuser WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    conn.close()

    return row[0] if row else None
    
@app.route("/")
def home_page():
    return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():

    print("login route called")

    username = request.form["username"]
    password = request.form["password"]

    conn = sqlite3.connect("database/vote_man.db")

    user = conn.execute(
        """
        SELECT user_id, ROLE
        FROM newuser
        WHERE username=? AND password=?
        """,
        (username, password)
    ).fetchone()

    if not user:
        conn.close()
        return "invalid username or password"

    user_id = user[0]
    role = user[1]

    session["user_id"] = user_id
    session["role"] = role

    conn.execute(
        """
        UPDATE newuser
        SET last_login=CURRENT_TIMESTAMP
        WHERE user_id=?
        """,
        (user_id,)
    )
    conn.commit()

    if role == "voter":

        voter_profile = conn.execute(
            """
            SELECT profile_id
            FROM voters
            WHERE user_id=?
            """,
            (user_id,)
        ).fetchone()

        conn.close()

        if voter_profile:
            return redirect(url_for("voter_dashboard"))

        return render_template(
            "voter.html",
            username=username
        )

    conn.close()

    if role == "admin":
        return render_template(
            "manager.html",
            username=username
        )

    if role == "candidate":
        return redirect(url_for("candidate"))

    return "invalid role"
            
@app.route("/voter",methods=["POST"])
def voter():
    user_id = session['user_id']
    phone = request.form["phone"]
    city = request.form["city"]
    address = request.form["address"]
    state = request.form["state"]
    country = request.form["country"]
    conn = sqlite3.connect("database/vote_man.db")
    conn.execute("""
    INSERT INTO voters (user_id, phone, adress, city, state, country)
    VALUES (?, ?, ?, ?, ?, ?)""", (user_id, phone, address, city, state, country))
    conn.commit()
    conn.close()
    return render_template("status.html",title="Profile Updated",
                            message="your voter profile has been saved successfully.",
                            link_url=url_for("voter_dashboard"),
                            link_text="Go to Dashboard")

@app.route("/admin",methods=['POST'])
def admin():
    conn = sqlite3.connect("database/vote_man.db")
    title = request.form['title']
    start_date = request.form['start_date']
    end_date = request.form['end_date']
    des = request.form['des']
    elg = request.form['elg']
    result_date = request.form['result_date']
    start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M")
    end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M")
    option = request.form['option']
    now = datetime.now()
    status = ""
    if now < start_date:
        status = "upcoming"
    elif now <= end_date:
        status = "ongoing"
    else:
        status = "completed"
    conn.execute("insert into election(title,start_date,end_date,des,elg,result_date,status,election_type) values (?,?,?,?,?,?,?,?)",
                     (title,start_date,end_date,des,elg,result_date,status,option))
    conn.commit()
    conn.close()
    return render_template("status.html",
                            title = "Election Created",
                            message = "The election has been created successfully",
                            link_url = url_for("home_page"),
                            link_text = "Return to home")

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
    # Check whether username already exists
    existing_user = conn.execute(
        "SELECT user_id FROM newuser WHERE username = ?",
        (username,)
    ).fetchone()

    if existing_user:
        conn.close()
        return render_template(
            "register.html",
            error="Username already exists. Please choose another."
        )
    conn.execute("""insert into newuser ("first_name","last_name","username","email","password","ROLE")values (?,?,?,?,?,?)""",
              (first_name,last_name,username,email,password,role)) 
    conn.commit()
    voter  = conn.execute("select * from newuser").fetchall()
    conn.close()
    return render_template("status.html",
                           title="Registration Successful",
                           message="Your account has been created successfully. You can now sign in.",
                           link_url=url_for("home_page"),
                           link_text="Sign In")

@app.route("/candidate", methods=["GET", "POST"])
def candidate():
    conn = sqlite3.connect("database/vote_man.db")
    conn.row_factory = sqlite3.Row

    if request.method == "GET":

        elections = conn.execute("""
            SELECT election_id, title
            FROM election
            ORDER BY election_id DESC
        """).fetchall()

        conn.close()

        return render_template(
            "candidate.html",
            elections=elections
        )

    election_id = request.form["election_id"]
    name = request.form["name"]
    party = request.form["party"]
    manifesto = request.form["manifesto"]

    conn.execute("""
        INSERT INTO candidate
        (election_id, name, party, manifesto)
        VALUES (?, ?, ?, ?)
    """, (
        election_id,
        name,
        party,
        manifesto
    ))

    conn.commit()
    conn.close()

    return render_template("status.html",
                           title = "Candidate added",
                           message = "The candidate has been added successfully.",
                           link_url = url_for("candidate"),
                           link_text = "add another candidate")

@app.route("/voter/dashboard")
def voter_dashboard():
    conn = sqlite3.connect("database/vote_man.db")
    conn.row_factory = sqlite3.Row

    elections = conn.execute("""
        SELECT *
        FROM election
        WHERE status = 'ongoing'
    """).fetchall()

    conn.close()

    return render_template(
        "voter_dashboard.html",
        elections=elections
    )

@app.route("/view_election", methods=["POST"])
def view_election():

    election_id = request.form["election_id"]

    conn = sqlite3.connect("database/vote_man.db")
    conn.row_factory = sqlite3.Row

    election = conn.execute("""
        SELECT *
        FROM election
        WHERE election_id = ?
    """, (election_id,)).fetchone()

    candidates = conn.execute("""
        SELECT *
        FROM candidate
        WHERE election_id = ?
    """, (election_id,)).fetchall()

    conn.close()

    return render_template(
        "view_election.html",
        election=election,
        candidates=candidates
    )

if __name__ == '__main__':
    app.run(debug=True)



