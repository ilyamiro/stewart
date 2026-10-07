from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .gateway import StudiePlusGateway
from .models import WeekSchedule, HomeworkItem
from .parser import AuthenticationRequiredError


def create_app(gateway: Optional[StudiePlusGateway] = None) -> FastAPI:
    app = FastAPI(
        title="Studie+ Gateway API",
        description="REST API Gateway for Studie+ (UDData+) schedule and homework",
        version="0.1.0",
    )
    gw = gateway or StudiePlusGateway()

    @app.get("/api/status")
    def get_status():
        logged_in = gw.is_logged_in()
        return {
            "authenticated": logged_in,
            "profile_dir": str(gw.config.profile_dir),
            "target_url": gw.config.schedule_url,
        }

    @app.get("/api/schedule", response_model=WeekSchedule)
    def get_schedule(url: Optional[str] = None):
        try:
            return gw.get_schedule(target_url=url)
        except AuthenticationRequiredError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse schedule: {e}")

    @app.get("/api/homework", response_model=List[HomeworkItem])
    def get_homework(url: Optional[str] = None):
        try:
            return gw.get_homework(target_url=url)
        except AuthenticationRequiredError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse homework: {e}")

    return app
