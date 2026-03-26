from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import certifi
import os
import requests as http_requests

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
space_follows_collection = db["space_follows"]
user_follows_collection = db["user_follows"]
conversations_collection = db["conversations"]
messages_collection = db["messages"]


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
    feed_posts = []
    followed_space_ids = []

    if "user_id" in session:
        follows = space_follows_collection.find({"user_id": ObjectId(session["user_id"])})
        followed_space_ids = [f["space_id"] for f in follows]

        if followed_space_ids:
            feed_posts = list(
                posts_collection.find({"space_id": {"$in": followed_space_ids}}).sort("created_at", -1).limit(30)
            )

            space_map = {
                s["_id"]: s["name"]
                for s in spaces_collection.find({"_id": {"$in": followed_space_ids}})
            }
            for post in feed_posts:
                post["space_name"] = space_map.get(post["space_id"], "")

    return render_template("index.html", feed_posts=feed_posts, followed_space_ids=followed_space_ids)


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

    is_following = False
    if "user_id" in session:
        is_following = space_follows_collection.find_one({
            "user_id": ObjectId(session["user_id"]),
            "space_id": ObjectId(space_id)
        }) is not None

    return render_template("space_detail.html", space=space, space_posts=space_posts, is_following=is_following)


@app.route("/spaces/<space_id>/follow", methods=["POST"])
def follow_space(space_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    existing = space_follows_collection.find_one({
        "user_id": ObjectId(session["user_id"]),
        "space_id": ObjectId(space_id)
    })

    if existing:
        space_follows_collection.delete_one({"_id": existing["_id"]})
    else:
        space_follows_collection.insert_one({
            "user_id": ObjectId(session["user_id"]),
            "space_id": ObjectId(space_id),
            "created_at": datetime.utcnow()
        })

    return redirect(url_for("space_detail", space_id=space_id))


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
        image_url = request.form.get("image_url", "").strip()

        if not content and not image_url:
            flash("Comment must have text or an image.")
            return redirect(url_for("post_detail", post_id=post_id))

        comment = {
            "post_id": ObjectId(post_id),
            "user_id": ObjectId(session["user_id"]),
            "username": session["username"],
            "content": content,
            "image_url": image_url,
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

@app.route("/giphy/search")
def giphy_search():
    query = request.args.get("q", "")
    api_key = os.getenv("GIPHY_API_KEY")
    if not api_key:
        return jsonify({"error": "Missing GIPHY_API_KEY"}), 500
    try:
        response = http_requests.get(
            "https://api.giphy.com/v1/gifs/search",
            params={"api_key": api_key, "q": query, "limit": 12, "rating": "pg-13"}
        )
        data = response.json()
        if "data" not in data:
            return jsonify({"error": data}), 500
        gifs = [{"url": g["images"]["fixed_height"]["url"]} for g in data["data"]]
        return jsonify(gifs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = ObjectId(session["user_id"])
    user = users_collection.find_one({"_id": user_id})

    user_posts = list(posts_collection.find({"user_id": user_id}).sort("created_at", -1))
    user_comments = list(comments_collection.find({"user_id": user_id}).sort("created_at", -1))
    user_boards = list(boards_collection.find({"user_id": user_id}).sort("created_at", -1))
    user_spaces = list(spaces_collection.find({"created_by": user_id}).sort("created_at", -1))

    followers_count = user_follows_collection.count_documents({"following_id": user_id})
    following_count = user_follows_collection.count_documents({"follower_id": user_id})

    for comment in user_comments:
        post = posts_collection.find_one({"_id": comment["post_id"]})
        comment["post_title"] = post["title"] if post else "Deleted post"
        comment["post_id_str"] = str(comment["post_id"])

    return render_template(
        "profile.html",
        user=user,
        user_posts=user_posts,
        user_comments=user_comments,
        user_boards=user_boards,
        user_spaces=user_spaces,
        followers_count=followers_count,
        following_count=following_count
    )


@app.route("/posts/<post_id>/delete", methods=["POST"])
def delete_post(post_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    post = posts_collection.find_one({"_id": ObjectId(post_id)})
    if not post or str(post["user_id"]) != session["user_id"]:
        return "Unauthorized", 403

    space_id = str(post["space_id"])
    posts_collection.delete_one({"_id": ObjectId(post_id)})
    comments_collection.delete_many({"post_id": ObjectId(post_id)})
    saved_posts_collection.delete_many({"post_id": ObjectId(post_id)})
    return redirect(url_for("space_detail", space_id=space_id))


@app.route("/comments/<comment_id>/delete", methods=["POST"])
def delete_comment(comment_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    comment = comments_collection.find_one({"_id": ObjectId(comment_id)})
    if not comment or str(comment["user_id"]) != session["user_id"]:
        return "Unauthorized", 403

    post_id = str(comment["post_id"])
    comments_collection.delete_one({"_id": ObjectId(comment_id)})
    return redirect(url_for("post_detail", post_id=post_id))


@app.route("/boards/<board_id>/delete", methods=["POST"])
def delete_board(board_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    board = boards_collection.find_one({"_id": ObjectId(board_id)})
    if not board or str(board["user_id"]) != session["user_id"]:
        return "Unauthorized", 403

    boards_collection.delete_one({"_id": ObjectId(board_id)})
    saved_posts_collection.delete_many({"board_id": ObjectId(board_id)})
    return redirect(url_for("boards_page"))


@app.route("/spaces/<space_id>/delete", methods=["POST"])
def delete_space(space_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    space = spaces_collection.find_one({"_id": ObjectId(space_id)})
    if not space or str(space.get("created_by", "")) != session["user_id"]:
        return "Unauthorized", 403

    spaces_collection.delete_one({"_id": ObjectId(space_id)})
    return redirect(url_for("spaces_page"))


@app.route("/users/search")
def search_users():
    q = request.args.get("q", "").strip()
    users = []
    if q:
        users = list(users_collection.find(
            {"username": {"$regex": q, "$options": "i"}},
            {"password_hash": 0}
        ).limit(10))
    return render_template("search_users.html", users=users, q=q)


@app.route("/users/<username>")
def user_profile(username):
    target = users_collection.find_one({"username": username})
    if not target:
        return "User not found", 404

    if "user_id" in session and session["user_id"] == str(target["_id"]):
        return redirect(url_for("profile"))

    is_following = False
    is_friend = False

    if "user_id" in session:
        viewer_id = ObjectId(session["user_id"])
        target_id = target["_id"]

        viewer_follows_target = user_follows_collection.find_one({
            "follower_id": viewer_id, "following_id": target_id
        }) is not None

        target_follows_viewer = user_follows_collection.find_one({
            "follower_id": target_id, "following_id": viewer_id
        }) is not None

        is_following = viewer_follows_target
        is_friend = viewer_follows_target and target_follows_viewer

    is_private = target.get("is_private", False)
    can_view = not is_private or is_friend

    user_posts = []
    user_boards = []
    user_spaces = []

    if can_view:
        user_posts = list(posts_collection.find({"user_id": target["_id"]}).sort("created_at", -1))
        user_boards = list(boards_collection.find({"user_id": target["_id"], "is_private": False}).sort("created_at", -1))
        user_spaces = list(spaces_collection.find({"created_by": target["_id"]}).sort("created_at", -1))

    followers_count = user_follows_collection.count_documents({"following_id": target["_id"]})
    following_count = user_follows_collection.count_documents({"follower_id": target["_id"]})

    return render_template("user_profile.html",
        target=target,
        is_following=is_following,
        is_friend=is_friend,
        can_view=can_view,
        user_posts=user_posts,
        user_boards=user_boards,
        user_spaces=user_spaces,
        followers_count=followers_count,
        following_count=following_count
    )


@app.route("/users/<username>/follow", methods=["POST"])
def follow_user(username):
    if "user_id" not in session:
        return redirect(url_for("login"))

    target = users_collection.find_one({"username": username})
    if not target or str(target["_id"]) == session["user_id"]:
        return "Invalid", 400

    existing = user_follows_collection.find_one({
        "follower_id": ObjectId(session["user_id"]),
        "following_id": target["_id"]
    })

    if existing:
        user_follows_collection.delete_one({"_id": existing["_id"]})
    else:
        user_follows_collection.insert_one({
            "follower_id": ObjectId(session["user_id"]),
            "following_id": target["_id"],
            "created_at": datetime.utcnow()
        })

    return redirect(url_for("user_profile", username=username))


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        is_private = request.form.get("is_private") == "on"
        users_collection.update_one(
            {"_id": ObjectId(session["user_id"])},
            {"$set": {"is_private": is_private}}
        )
        flash("Settings updated.")
        return redirect(url_for("settings"))

    user = users_collection.find_one({"_id": ObjectId(session["user_id"])})
    return render_template("settings.html", user=user)


@app.route("/messages")
def messages_page():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = ObjectId(session["user_id"])
    convos = list(conversations_collection.find({"participants": user_id}).sort("updated_at", -1))

    for convo in convos:
        last_msg = messages_collection.find_one(
            {"conversation_id": convo["_id"]},
            sort=[("created_at", -1)]
        )
        convo["last_message"] = last_msg
        if not convo.get("is_group"):
            other_id = next((p for p in convo["participants"] if p != user_id), None)
            if other_id:
                other_user = users_collection.find_one({"_id": other_id}, {"username": 1})
                convo["display_name"] = other_user["username"] if other_user else "Unknown"
        else:
            convo["display_name"] = convo.get("name", "Group Chat")

    return render_template("messages.html", convos=convos)


@app.route("/messages/new/<username>", methods=["POST"])
def new_dm(username):
    if "user_id" not in session:
        return redirect(url_for("login"))

    target = users_collection.find_one({"username": username})
    if not target:
        return "User not found", 404

    user_id = ObjectId(session["user_id"])
    target_id = target["_id"]

    existing = conversations_collection.find_one({
        "is_group": False,
        "participants": {"$all": [user_id, target_id], "$size": 2}
    })

    if existing:
        return redirect(url_for("conversation", conversation_id=str(existing["_id"])))

    result = conversations_collection.insert_one({
        "participants": [user_id, target_id],
        "is_group": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })
    return redirect(url_for("conversation", conversation_id=str(result.inserted_id)))


@app.route("/messages/group/create", methods=["GET", "POST"])
def create_group():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"].strip()
        usernames = [u.strip() for u in request.form["usernames"].split(",") if u.strip()]

        participants = [ObjectId(session["user_id"])]
        for uname in usernames:
            u = users_collection.find_one({"username": uname})
            if u and u["_id"] not in participants:
                participants.append(u["_id"])

        if len(participants) < 2:
            flash("Add at least one valid username.")
            return redirect(url_for("create_group"))

        result = conversations_collection.insert_one({
            "participants": participants,
            "is_group": True,
            "name": name,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
        return redirect(url_for("conversation", conversation_id=str(result.inserted_id)))

    return render_template("create_group.html")


@app.route("/messages/<conversation_id>", methods=["GET", "POST"])
def conversation(conversation_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = ObjectId(session["user_id"])
    convo = conversations_collection.find_one({
        "_id": ObjectId(conversation_id),
        "participants": user_id
    })

    if not convo:
        return "Conversation not found", 404

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        post_id = request.form.get("post_id", "").strip()

        if content or post_id:
            message = {
                "conversation_id": ObjectId(conversation_id),
                "sender_id": user_id,
                "sender_username": session["username"],
                "content": content,
                "created_at": datetime.utcnow()
            }
            if post_id:
                message["post_id"] = ObjectId(post_id)
            messages_collection.insert_one(message)
            conversations_collection.update_one(
                {"_id": ObjectId(conversation_id)},
                {"$set": {"updated_at": datetime.utcnow()}}
            )

        return redirect(url_for("conversation", conversation_id=conversation_id))

    msgs = list(messages_collection.find(
        {"conversation_id": ObjectId(conversation_id)}
    ).sort("created_at", 1))

    for msg in msgs:
        if msg.get("post_id"):
            msg["shared_post"] = posts_collection.find_one({"_id": msg["post_id"]})

    participants = []
    for pid in convo["participants"]:
        u = users_collection.find_one({"_id": pid}, {"username": 1})
        if u:
            participants.append(u["username"])

    if convo.get("is_group"):
        display_name = convo.get("name", "Group Chat")
    else:
        display_name = next((p for p in participants if p != session["username"]), "Unknown")

    return render_template("conversation.html",
        convo=convo,
        msgs=msgs,
        participants=participants,
        display_name=display_name
    )


@app.route("/posts/<post_id>/share", methods=["GET", "POST"])
def share_post(post_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    post = posts_collection.find_one({"_id": ObjectId(post_id)})
    if not post:
        return "Post not found", 404

    user_id = ObjectId(session["user_id"])

    if request.method == "POST":
        conversation_id = request.form["conversation_id"]
        content = request.form.get("content", "").strip()

        convo = conversations_collection.find_one({
            "_id": ObjectId(conversation_id),
            "participants": user_id
        })
        if not convo:
            return "Conversation not found", 404

        messages_collection.insert_one({
            "conversation_id": ObjectId(conversation_id),
            "sender_id": user_id,
            "sender_username": session["username"],
            "content": content,
            "post_id": ObjectId(post_id),
            "created_at": datetime.utcnow()
        })
        conversations_collection.update_one(
            {"_id": ObjectId(conversation_id)},
            {"$set": {"updated_at": datetime.utcnow()}}
        )
        return redirect(url_for("conversation", conversation_id=conversation_id))

    convos = list(conversations_collection.find({"participants": user_id}).sort("updated_at", -1))
    for convo in convos:
        if not convo.get("is_group"):
            other_id = next((p for p in convo["participants"] if p != user_id), None)
            if other_id:
                other_user = users_collection.find_one({"_id": other_id}, {"username": 1})
                convo["display_name"] = other_user["username"] if other_user else "Unknown"
        else:
            convo["display_name"] = convo.get("name", "Group Chat")

    return render_template("share_post.html", post=post, convos=convos)


seed_spaces()

if __name__ == "__main__":
    
    app.run(debug=True, host="0.0.0.0")