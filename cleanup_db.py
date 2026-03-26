from pymongo import MongoClient
from dotenv import load_dotenv
import certifi, os

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"), tlsCAFile=certifi.where())
db = client["fancon"]

# Find the Project Hail Mary space
space = db["spaces"].find_one({"name": {"$regex": "hail mary", "$options": "i"}})
if not space:
    print("Could not find Project Hail Mary space. Check the exact name in your DB.")
    exit()

space_id = space["_id"]
print(f"Found space: {space['name']} ({space_id})")

# Keep only posts in that space
keep_posts = list(db["posts"].find({"space_id": space_id}, {"_id": 1}))
keep_post_ids = [p["_id"] for p in keep_posts]
print(f"Keeping {len(keep_post_ids)} posts in Project Hail Mary.")

# Delete all other posts
result = db["posts"].delete_many({"space_id": {"$ne": space_id}})
print(f"Deleted {result.deleted_count} posts.")

# Delete comments not belonging to kept posts
result = db["comments"].delete_many({"post_id": {"$nin": keep_post_ids}})
print(f"Deleted {result.deleted_count} comments.")

print("Done.")
