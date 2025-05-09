from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status, Request, Cookie
from typing import Optional
from pydantic import BaseModel, Field
import os
import uuid
from bson import ObjectId

from . import models

# Security configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# JWT configuration
SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Define TokenData model inline (updated for Pydantic v2)
class TokenData(BaseModel):
    username: Optional[str] = Field(default=None)

def verify_password(plain_password, hashed_password):
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """Hash a password."""
    return pwd_context.hash(password)

async def get_user(db, username: str):
    """Get a user by username."""
    return await models.get_user_by_username(db, username)

async def get_user_by_email(db, email: str):
    """Get a user by email."""
    return await models.get_user_by_email(db, email)

async def authenticate_user(db, username: str, password: str):
    """Authenticate a user."""
    user = await get_user(db, username)
    if not user:
        return False
    if not verify_password(password, user["hashed_password"]):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def create_user(db, username: str, email: str, full_name: str, password: str):
    """Create a new user."""
    # Check if username or email already exists
    if await get_user(db, username):
        return False, "Username already exists"
    
    if await get_user_by_email(db, email):
        return False, "Email already exists"
    
    # Create new user
    hashed_password = get_password_hash(password)
    user_data = models.create_user_dict(
        username=username,
        email=email,
        full_name=full_name,
        hashed_password=hashed_password
    )
    
    result = await db.users.insert_one(user_data)
    if result.inserted_id:
        user_data['_id'] = result.inserted_id
        return True, user_data
    else:
        return False, "Failed to create user"

async def get_current_user(
    request: Request,
    db = Depends(models.get_db),
    access_token: str = Cookie(None)
):
    """Get the current authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not access_token:
        raise credentials_exception
    
    try:
        # Remove 'Bearer ' prefix if it exists
        if access_token.startswith('Bearer '):
            access_token = access_token.split(' ')[1]
            
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
        
    user = await get_user(db, username=token_data.username)
    if user is None:
        raise credentials_exception
        
    return user

# Initialize database 
async def init_db():
    """Initialize the database with indexes if needed."""
    # Just initialize collections and indexes in MongoDB
    await models.init_mongodb() 