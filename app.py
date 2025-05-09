from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

# Import our modules
from src import models
from src.campaign_routes import router as campaign_router
from src.routes import router as main_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    # Initialize MongoDB indexes
    await models.init_mongodb()
    yield

# Create FastAPI app
app = FastAPI(title="Ad Campaign Dashboard", lifespan=lifespan)

# Static files and templates setup
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Include the routers
app.include_router(main_router)
app.include_router(campaign_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000) 