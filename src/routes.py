from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from typing import Dict, Any

from . import auth
from . import models
from .ai_service import ai_service

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Landing page with product information."""
    return templates.TemplateResponse("landing.html", {"request": request})

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse("login.html", {"request": request})

# Keeping this for backward compatibility but redirecting to the root
@router.get("/landing", response_class=HTMLResponse)
async def landing_page_redirect():
    """Redirect old landing page URL to the root."""
    return RedirectResponse(url="/", status_code=303)

@router.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    """Sign up page."""
    return templates.TemplateResponse("signup.html", {"request": request})

@router.post("/signup", response_class=HTMLResponse)
async def signup(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db = Depends(models.get_db)
):
    """Handle user registration."""
    # Check if passwords match
    if password != confirm_password:
        return templates.TemplateResponse("signup.html", {
            "request": request, 
            "error": "Passwords do not match"
        })
    
    # Create user
    success, result = await auth.create_user(db, username, email, full_name, password)
    if not success:
        return templates.TemplateResponse("signup.html", {
            "request": request, 
            "error": result
        })
    
    # Redirect to login page with success message
    return RedirectResponse("/login?success=Account+created+successfully.+Please+log+in.", status_code=303)

@router.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db = Depends(models.get_db)
):
    """Login route that handles authentication and token creation."""
    user = await auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        return RedirectResponse(url="/login?error=Invalid+credentials", status_code=303)
    
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return response

@router.get("/logout")
async def logout():
    """Logout route that clears the authentication cookie."""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("access_token")
    return response

@router.get("/api/campaign-suggestion")
async def get_campaign_suggestion(
    request: Request,
    business_type: str = Query(None, description="Optional business type for tailored suggestions"),
    db = Depends(models.get_db)
):
    """Get a campaign suggestion to populate the campaign creation form."""
    try:
        # Try to get current user, but make it optional
        current_user = None
        try:
            current_user = await auth.get_current_user(request=request, db=db)
        except:
            # Allow anonymous access for demo/development
            pass
        
        # Log request details
        print(f"Campaign suggestion requested - Business type: {business_type or 'Not specified'}")
        
        # Get suggestion from AI service
        try:
            suggestion = await ai_service.get_campaign_suggestion(business_type)
            
            # Log success
            print(f"Campaign suggestion generated successfully for business type: {business_type or 'Not specified'}")
            
            return JSONResponse(content=suggestion)
        except Exception as e:
            error_message = str(e)
            print(f"AI service error: {error_message}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Could not generate campaign suggestion",
                    "message": "The AI service is currently unavailable. Please ensure you have set up the CEREBRAS_API_KEY in your environment."
                }
            )
    except Exception as e:
        print(f"Error in campaign suggestion API: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to generate suggestion: {str(e)}"}
        ) 