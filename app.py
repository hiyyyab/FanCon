from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import certifi
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

client = MongoClient(os.getenv("MONGO_URI"), tlsCAFile=certifi.where())
db = client["fancon"]

users_collection = db["users"]
spaces_collection = db["spaces"]
posts_collection = db["posts"]
comments_collection = db["comments"]
boards_collection = db["boards"]
saved_posts_collection = db["saved_posts"]


def seed_spaces():
    if spaces_collection.count_documents({}) == 0:
        spaces_collection.insert_many([
            {
                "name": "Manchester United",
                "description": "Posts, memories, and discussions for United fans."
            },
            {
                "name": "Books",
                "description": "Quotes, characters, reading eras, and fandom conversations."
            },
            {
                "name": "Music",
                "description": "Fan discussions, favorite eras, and saved moments."
            }
        ])


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"].strip()

        existing_user = users_collection.find_one({
            "$or": [
                {"email": email},
                {"username": username}
            ]
        })

        if existing_user:
            flash("User already exists.")
            return redirect(url_for("signup"))

        password_hash = generate_password_hash(password)

        user = {
            "username": username,
            "email": email,
            "password_hash": password_hash,
            "created_at": datetime.utcnow()
        }

        result = users_collection.insert_one(user)

        session["user_id"] = str(result.inserted_id)
        session["username"] = username

        return redirect(url_for("index"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"].strip()

        user = users_collection.find_one({"email": email})

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = str(user["_id"])
            session["username"] = user["username"]
            return redirect(url_for("index"))

        flash("Invalid login.")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/spaces")
def spaces_page():
    spaces = list(spaces_collection.find())
    return render_template("spaces.html", spaces=spaces)


@app.route("/spaces/create", methods=["GET", "POST"])
def create_space():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"].strip()
        description = request.form["description"].strip()

        space = {
            "name": name,
            "description": description,
            "created_by": ObjectId(session["user_id"]),
            "created_at": datetime.utcnow()
        }

        spaces_collection.insert_one(space)
        return redirect(url_for("spaces_page"))

    return render_template("create_space.html")


@app.route("/spaces/<space_id>")
def space_detail(space_id):
    space = spaces_collection.find_one({"_id": ObjectId(space_id)})
    if not space:
        return "Space not found", 404

    space_posts = list(
        posts_collection.find({"space_id": ObjectId(space_id)}).sort("created_at", -1)
    )

    return render_template("space_detail.html", space=space, space_posts=space_posts)


@app.route("/spaces/<space_id>/posts/create", methods=["GET", "POST"])
def create_post(space_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    space = spaces_collection.find_one({"_id": ObjectId(space_id)})
    if not space:
        return "Space not found", 404

    if request.method == "POST":
        title = request.form["title"].strip()
        content = request.form["content"].strip()
        image_url = request.form.get("image_url", "").strip()

        post = {
            "space_id": ObjectId(space_id),
            "user_id": ObjectId(session["user_id"]),
            "username": session["username"],
            "title": title,
            "content": content,
            "image_url": image_url,
            "created_at": datetime.utcnow()
        }

        posts_collection.insert_one(post)
        return redirect(url_for("space_detail", space_id=space_id))

    return render_template("create_post.html", space=space)


@app.route("/posts/<post_id>", methods=["GET", "POST"])
def post_detail(post_id):
    post = posts_collection.find_one({"_id": ObjectId(post_id)})
    if not post:
        return "Post not found", 404

    if request.method == "POST":
        if "user_id" not in session:
            return redirect(url_for("login"))

        content = request.form["content"].strip()

        comment = {
            "post_id": ObjectId(post_id),
            "user_id": ObjectId(session["user_id"]),
            "username": session["username"],
            "content": content,
            "created_at": datetime.utcnow()
        }

        comments_collection.insert_one(comment)
        return redirect(url_for("post_detail", post_id=post_id))

    post_comments = list(
        comments_collection.find({"post_id": ObjectId(post_id)}).sort("created_at", 1)
    )

    user_boards = []
    if "user_id" in session:
        user_boards = list(
            boards_collection.find({"user_id": ObjectId(session["user_id"])}).sort("created_at", -1)
        )

    return render_template(
        "post_detail.html",
        post=post,
        post_comments=post_comments,
        user_boards=user_boards
    )


@app.route("/boards")
def boards_page():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_boards = list(
        boards_collection.find({"user_id": ObjectId(session["user_id"])}).sort("created_at", -1)
    )
    return render_template("boards.html", boards=user_boards)


@app.route("/boards/create", methods=["GET", "POST"])
def create_board():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        title = request.form["title"].strip()
        description = request.form["description"].strip()
        is_private = True if request.form.get("is_private") == "on" else False

        board = {
            "user_id": ObjectId(session["user_id"]),
            "title": title,
            "description": description,
            "is_private": is_private,
            "created_at": datetime.utcnow()
        }

        boards_collection.insert_one(board)
        return redirect(url_for("boards_page"))

    return render_template("create_board.html")


@app.route("/posts/<post_id>/save", methods=["POST"])
def save_post(post_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    board_id = request.form["board_id"]
    note = request.form.get("note", "").strip()

    post = posts_collection.find_one({"_id": ObjectId(post_id)})
    if not post:
        return "Post not found", 404

    board = boards_collection.find_one({
        "_id": ObjectId(board_id),
        "user_id": ObjectId(session["user_id"])
    })
    if not board:
        return "Board not found", 404

    existing_saved = saved_posts_collection.find_one({
        "user_id": ObjectId(session["user_id"]),
        "board_id": ObjectId(board_id),
        "post_id": ObjectId(post_id)
    })

    if existing_saved:
        flash("Post is already saved to this board.")
        return redirect(url_for("post_detail", post_id=post_id))

    saved_item = {
        "user_id": ObjectId(session["user_id"]),
        "board_id": ObjectId(board_id),
        "post_id": ObjectId(post_id),
        "note": note,
        "created_at": datetime.utcnow()
    }

    saved_posts_collection.insert_one(saved_item)
    return redirect(url_for("board_detail", board_id=board_id))


@app.route("/boards/<board_id>")
def board_detail(board_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    board = boards_collection.find_one({
        "_id": ObjectId(board_id),
        "user_id": ObjectId(session["user_id"])
    })

    if not board:
        return "Board not found", 404

    saved_items = list(
        saved_posts_collection.find({
            "board_id": ObjectId(board_id),
            "user_id": ObjectId(session["user_id"])
        }).sort("created_at", -1)
    )

    board_saved_items = []
    for item in saved_items:
        post = posts_collection.find_one({"_id": item["post_id"]})
        if post:
            board_saved_items.append({
                "saved_id": str(item["_id"]),
                "note": item.get("note", ""),
                "post": post
            })

    return render_template(
        "board_detail.html",
        board=board,
        board_saved_items=board_saved_items
    )

seed_spaces()

if __name__ == "__main__":
    
    app.run(debug=True)   