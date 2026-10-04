from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any
from app.ml.early_alarm import run_early_alarm_analysis, load_thresholds
from app.ml.alarm_board import run_alarm_board

router = APIRouter(prefix="/api/ml", tags=["ml"])

@router.get("/early-alarm")
def get_early_alarm_analysis() -> Dict[str, Any]:
    try:
        return run_early_alarm_analysis()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ML early alarm analysis failed: {str(e)}")

@router.get("/alarm-board")
def get_alarm_board(
    include_series: bool = Query(True, description="Include downsampled series for trend charts"),
    step: int = Query(3, description="Downsample step for trend series")
) -> Dict[str, Any]:
    try:
        return run_alarm_board(include_series=include_series, series_step=step)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate alarm board: {str(e)}")

@router.get("/thresholds")
def get_thresholds_config() -> Dict[str, Any]:
    try:
        return load_thresholds()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load thresholds config: {str(e)}")

