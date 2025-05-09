from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi
from bson import ObjectId
from datetime import datetime
import os
from dotenv import load_dotenv
import io
import motor.motor_asyncio
import asyncio

# Load environment variables
load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is not set")

# Global variables for database connections
client = None
db = None
fs = None

async def init_mongodb():
    """Initialize MongoDB connection and indexes."""
    global client, db, fs
    
    # Configure MongoDB client with reliability settings
    client = AsyncIOMotorClient(
        MONGODB_URI,
        server_api=ServerApi('1'),
        retryWrites=True,
        w='majority',
        connectTimeoutMS=5000,  # 5 second timeout for initial connection
        serverSelectionTimeoutMS=5000  # 5 second timeout for server selection
    )
    
    db = client.campaign_dashboard
    fs = motor.motor_asyncio.AsyncIOMotorGridFSBucket(db)
    
    # Create indexes
    await db.users.create_index("username", unique=True)
    await db.users.create_index("email", unique=True)
    await db.campaigns.create_index("owner_id")
    await db.campaigns.create_index("name")

def ensure_object_id(id_value):
    """Convert string ID to ObjectId if needed."""
    if isinstance(id_value, str) and len(id_value) == 24:
        return ObjectId(id_value)
    return id_value

async def save_image_to_gridfs(file_data, filename):
    """Store image in GridFS and return file ID."""
    global fs
    file_obj = io.BytesIO(file_data) if isinstance(file_data, bytes) else file_data
    return await fs.upload_from_stream(
        filename,
        file_obj,
        metadata={"content_type": "image/jpeg"}
    )

async def get_image_by_id(file_id):
    """Retrieve image from GridFS by ID."""
    global fs
    file_id = ensure_object_id(file_id)
    try:
        return await fs.open_download_stream(file_id)
    except:
        return None

async def delete_image(file_id):
    """Delete image from GridFS."""
    global fs
    file_id = ensure_object_id(file_id)
    try:
        await fs.delete(file_id)
    except:
        pass

async def get_db():
    """Return database instance."""
    global db
    return db

def create_user_dict(username, email, full_name, hashed_password):
    """Create user document for MongoDB."""
    return {
        "username": username,
        "email": email,
        "full_name": full_name,
        "hashed_password": hashed_password,
        "created_at": datetime.utcnow()
    }

async def get_user_by_username(db, username):
    """Find user by username."""
    return await db.users.find_one({"username": username})

async def get_user_by_email(db, email):
    """Find user by email."""
    return await db.users.find_one({"email": email})

def create_campaign_dict(name, owner_id, banner_id, ad_copy="", targeting=None, status="Active"):
    """Create campaign document for MongoDB."""
    return {
        "name": name,
        "owner_id": ensure_object_id(owner_id),
        "banner_id": banner_id,
        "ad_copy": ad_copy,
        "targeting": targeting or {},
        "status": status,
        "created_date": datetime.utcnow(),
        "updated_date": datetime.utcnow(),
        "impressions": 0,
        "clicks": 0,
        "ctr": 0.0
    } 