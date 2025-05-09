from fastapi import APIRouter, Depends, status, Form, UploadFile, File, Request, HTTPException
from typing import List, Dict, Any, Optional, Union
import random
from datetime import datetime
from bson import ObjectId
import io
import aiohttp
from PIL import Image
import mimetypes

from . import models
from . import auth
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

# Available locations for campaign targeting
LOCATIONS = [
    "New York", "London", "Tokyo", "Paris", "Berlin", "Sydney", "Toronto", "Madrid", "Rome", "Moscow", 
    "San Francisco", "Silicon Valley", "Los Angeles", "Chicago", "Boston", "Seattle", "Austin",
    "Miami", "Dallas", "Denver", "Atlanta", "Vancouver", "Amsterdam", "Singapore", "Hong Kong"
]

# Available interest categories for targeting
INTERESTS = [
    "Sports", "Technology", "Fashion", "Food", "Travel", "Music", "Movies", "Art", "Health", "Education"
]

router = APIRouter()
templates = Jinja2Templates(directory="templates")

async def verify_campaign_ownership(campaign_id: str, current_user: Dict[str, Any], db) -> Dict:
    """Verify campaign ownership and return campaign if valid."""
    campaign = await get_campaign(db, campaign_id)
    if not campaign or str(campaign["owner_id"]) != str(current_user["_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Campaign not found or access denied"
        )
    return campaign

async def get_campaign(db, campaign_id: str):
    """Find campaign by ID."""
    try:
        campaign_id = models.ensure_object_id(campaign_id)
        return await db.campaigns.find_one({"_id": campaign_id})
    except:
        return None

async def get_user_campaigns(db, user_id, skip: int = 0, limit: int = 100):
    """Find all campaigns for a user."""
    user_id = models.ensure_object_id(user_id)
    cursor = db.campaigns.find({"owner_id": user_id}).skip(skip).limit(limit)
    return await cursor.to_list(length=None)

async def download_image_from_url(url: str) -> tuple[bytes, str]:
    """Download image from URL and return its bytes and content type."""
    # Check for common image file extensions in the URL
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
    if not any(url.lower().endswith(ext) for ext in image_extensions):
        raise ValueError(
            "Please provide a direct link to an image file (URL should end with .jpg, .jpeg, .png, .gif, etc). "
            "If you're copying from Google Images, right-click the image and select 'Copy image address' instead."
        )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise ValueError(f"Failed to download image from URL: HTTP {response.status}")
            
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                raise ValueError(
                    "The URL does not point to an image file. "
                    "Please make sure you're using a direct link to an image (right-click image → Copy image address)"
                )
            
            image_data = await response.read()
            
            # Validate it's actually an image
            try:
                img = Image.open(io.BytesIO(image_data))
                img.verify()
            except Exception:
                raise ValueError("The URL provided does not contain valid image data")
            
            return image_data, content_type

async def process_banner(banner: Union[UploadFile, str, None]) -> tuple[bytes, str, str]:
    """Process banner from either file upload or URL."""
    print(f"Processing banner input: {banner}")  # Debug logging
    
    if banner is None:
        raise ValueError("No banner provided")
        
    if isinstance(banner, str):
        if not banner.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        try:
            # Handle URL upload
            file_data, content_type = await download_image_from_url(banner)
            filename = banner.split('/')[-1]
            if not filename or '.' not in filename:
                ext = mimetypes.guess_extension(content_type) or '.jpg'
                filename = f"banner{ext}"
        except Exception as e:
            raise ValueError(f"Error downloading image from URL: {str(e)}")
            
    elif hasattr(banner, 'filename') and hasattr(banner, 'read'):  # Check for UploadFile-like object
        try:
            # Handle file upload
            file_data = await banner.read()
            filename = banner.filename
            content_type = banner.content_type or 'image/jpeg'
            
            # Validate uploaded file is an image
            try:
                img = Image.open(io.BytesIO(file_data))
                img.verify()
            except Exception:
                raise ValueError("Invalid image file uploaded")
        except Exception as e:
            raise ValueError(f"Error processing uploaded file: {str(e)}")
    else:
        raise ValueError("Banner must be either a file upload or a valid image URL")
    
    return file_data, filename, content_type

async def create_campaign(db, campaign_data: dict, user_id, banner: Union[UploadFile, str]):
    """Create new campaign with banner from file or URL."""
    try:
        file_data, filename, content_type = await process_banner(banner)
        banner_id = await models.save_image_to_gridfs(io.BytesIO(file_data), filename)
        
        campaign = models.create_campaign_dict(
            name=campaign_data["name"],
            owner_id=user_id,
            banner_id=banner_id,
            ad_copy=campaign_data.get("ad_copy", ""),
            targeting=campaign_data["targeting"]
        )
        
        result = await db.campaigns.insert_one(campaign)
        campaign["_id"] = result.inserted_id
        return campaign
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error processing banner: {str(e)}"
        )

async def update_campaign_analytics(db, campaign_id, impressions, clicks, ctr):
    """Update campaign performance metrics."""
    campaign_id = models.ensure_object_id(campaign_id)
    await db.campaigns.update_one(
        {"_id": campaign_id},
        {"$set": {
            "impressions": impressions,
            "clicks": clicks, 
            "ctr": ctr
        }}
    )

def generate_analytics(campaign_id):
    """Generate sample analytics data for demo purposes."""
    impressions = random.randint(500, 10000)
    clicks = random.randint(10, impressions // 10)
    ctr = (clicks / impressions) * 100 if impressions > 0 else 0
    return impressions, clicks, round(ctr, 2)

@router.get("/campaign-banner/{campaign_id}")
async def get_campaign_banner(campaign_id: str, db = Depends(models.get_db)):
    """Serve campaign banner image."""
    try:
        campaign = await get_campaign(db, campaign_id)
        if not campaign or not campaign.get("banner_id"):
            raise HTTPException(status_code=404, detail="Banner not found")
        
        banner = await models.get_image_by_id(campaign["banner_id"])
        if not banner:
            raise HTTPException(status_code=404, detail="Banner not found")
            
        content = await banner.read()
        return StreamingResponse(io.BytesIO(content), media_type=banner.metadata.get("content_type", "image/jpeg"))
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail="Error retrieving banner")

@router.get("/dashboard")
async def dashboard_view(request: Request, current_user: Dict[str, Any] = Depends(auth.get_current_user)):
    """Render dashboard view."""
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": current_user})

@router.get("/create-campaign")
async def create_campaign_view(request: Request, current_user: Dict[str, Any] = Depends(auth.get_current_user)):
    """Render campaign creation form."""
    return templates.TemplateResponse(
        "create_campaign.html", 
        {"request": request, "user": current_user, "interests": INTERESTS, "locations": LOCATIONS}
    )

@router.post("/create-campaign")
async def create_campaign_submit(
    request: Request,
    name: str = Form(...),
    ad_copy: str = Form(""),
    age_min: int = Form(...),
    age_max: int = Form(...),
    location: str = Form(...),
    interests: List[str] = Form(...),
    upload_type: str = Form(...),
    banner: Union[UploadFile, None] = File(None),
    banner_url: Optional[str] = Form(None),
    db = Depends(models.get_db),
    current_user: Dict[str, Any] = Depends(auth.get_current_user)
):
    """Create new campaign from form data with either file upload or URL."""
    # Debug logging
    print(f"Upload type received: {upload_type}")
    print(f"Banner file received: {banner}")
    print(f"Banner URL received: {banner_url}")
    
    if upload_type == "file" and (not banner or not banner.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File upload selected but no file provided"
        )
    elif upload_type == "url" and not banner_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL upload selected but no URL provided. Please provide a direct link to an image file (ending in .jpg, .png, etc)"
        )
    
    targeting = {
        "age_range": f"{age_min}-{age_max}",
        "location": location,
        "interests": interests
    }
    
    campaign_data = {
        "name": name,
        "targeting": targeting,
        "ad_copy": ad_copy
    }
    
    # Debug logging
    banner_input = banner if upload_type == "file" else banner_url
    print(f"Banner input being used: {banner_input}")
    
    try:
        campaign = await create_campaign(db, campaign_data, current_user["_id"], banner_input)
        impressions, clicks, ctr = generate_analytics(campaign["_id"])
        await update_campaign_analytics(db, campaign["_id"], impressions, clicks, ctr)
        
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        print(f"Error processing banner: {str(e)}")  # Debug logging
        return RedirectResponse(
            url=f"/create-campaign?error={str(e)}", 
            status_code=status.HTTP_303_SEE_OTHER
        )

@router.get("/campaigns")
async def campaigns_view(
    request: Request, 
    db = Depends(models.get_db),
    current_user: Dict[str, Any] = Depends(auth.get_current_user)
):
    """Render campaigns list view."""
    campaigns = await get_user_campaigns(db, current_user["_id"])
    return templates.TemplateResponse(
        "campaigns.html", 
        {"request": request, "user": current_user, "campaigns": campaigns}
    )

@router.get("/api/campaigns")
async def read_campaigns(
    skip: int = 0, 
    limit: int = 100, 
    db = Depends(models.get_db),
    current_user: Dict[str, Any] = Depends(auth.get_current_user)
):
    """API endpoint to get user's campaigns."""
    campaigns = await get_user_campaigns(db, current_user["_id"], skip, limit)
    return campaigns

@router.get("/cancel-campaign/{campaign_id}")
async def cancel_campaign(
    campaign_id: str,
    db = Depends(models.get_db),
    current_user: Dict[str, Any] = Depends(auth.get_current_user)
):
    """Cancel active campaign."""
    try:
        campaign = await verify_campaign_ownership(campaign_id, current_user, db)
        await db.campaigns.update_one(
            {"_id": campaign["_id"]},
            {"$set": {"status": "Cancelled"}}
        )
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException:
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/reactivate-campaign/{campaign_id}")
async def reactivate_campaign(
    campaign_id: str,
    db = Depends(models.get_db),
    current_user: Dict[str, Any] = Depends(auth.get_current_user)
):
    """Reactivate cancelled campaign."""
    try:
        campaign = await verify_campaign_ownership(campaign_id, current_user, db)
        await db.campaigns.update_one(
            {"_id": campaign["_id"]},
            {"$set": {"status": "Active"}}
        )
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException:
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/edit-campaign/{campaign_id}")
async def edit_campaign_view(
    campaign_id: str,
    request: Request,
    db = Depends(models.get_db),
    current_user: Dict[str, Any] = Depends(auth.get_current_user)
):
    """Render campaign edit form."""
    try:
        campaign = await verify_campaign_ownership(campaign_id, current_user, db)
        targeting = campaign.get("targeting", {})
        age_range = targeting.get("age_range", "25-45").split("-")
        age_min = int(age_range[0]) if len(age_range) > 0 else 25
        age_max = int(age_range[1]) if len(age_range) > 1 else 45
        location = targeting.get("location", "New York")
        selected_interests = targeting.get("interests", [])
        
        return templates.TemplateResponse(
            "edit_campaign.html", 
            {
                "request": request, 
                "user": current_user, 
                "campaign": campaign,
                "interests": INTERESTS,
                "locations": LOCATIONS,
                "age_min": age_min,
                "age_max": age_max,
                "location": location,
                "selected_interests": selected_interests
            }
        )
    except HTTPException:
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/edit-campaign/{campaign_id}")
async def edit_campaign_submit(
    campaign_id: str,
    request: Request,
    name: str = Form(...),
    ad_copy: str = Form(""),
    age_min: int = Form(...),
    age_max: int = Form(...),
    location: str = Form(...),
    interests: List[str] = Form(...),
    banner: Union[UploadFile, None] = File(None),
    banner_url: Optional[str] = Form(None),
    db = Depends(models.get_db),
    current_user: Dict[str, Any] = Depends(auth.get_current_user)
):
    """Update campaign with edited data."""
    try:
        campaign = await verify_campaign_ownership(campaign_id, current_user, db)
        banner_id = campaign["banner_id"]
        
        # Process new banner if provided (either file or URL)
        if banner or banner_url:
            if banner_id:
                await models.delete_image(banner_id)
            banner_input = banner if banner else banner_url
            file_data, filename, content_type = await process_banner(banner_input)
            banner_id = await models.save_image_to_gridfs(io.BytesIO(file_data), filename)
        
        targeting = {
            "age_range": f"{age_min}-{age_max}",
            "location": location,
            "interests": interests
        }
        
        await db.campaigns.update_one(
            {"_id": campaign["_id"]},
            {"$set": {
                "name": name,
                "ad_copy": ad_copy,
                "targeting": targeting,
                "banner_id": banner_id,
                "updated_date": datetime.utcnow()
            }}
        )
        
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException:
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        return RedirectResponse(
            url=f"/edit-campaign/{campaign_id}?error={str(e)}", 
            status_code=status.HTTP_303_SEE_OTHER
        )

@router.get("/delete-campaign/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    db = Depends(models.get_db),
    current_user: Dict[str, Any] = Depends(auth.get_current_user)
):
    """Delete campaign and its banner."""
    try:
        campaign = await verify_campaign_ownership(campaign_id, current_user, db)
        if campaign.get("banner_id"):
            await models.delete_image(campaign["banner_id"])
        await db.campaigns.delete_one({"_id": campaign["_id"]})
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException:
        return RedirectResponse(url="/campaigns", status_code=status.HTTP_303_SEE_OTHER) 