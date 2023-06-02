from app.backend.app.db.mongo_db import Mongo
from fastapi import APIRouter, HTTPException

import json

router = APIRouter()
mongo_client = None

@router.on_event("startup")
async def startup_event():
    global mongo_client
    mongo_client = Mongo()
    await mongo_client.test()

@router.get("/")
async def ping():
    return {"Success": True}

@router.get("/db/get_data_from_bounds=l:{l},b:{b},r:{r},t:{t}")
async def get_data_from_bounds(l: float, b: float, r: float, t: float):
    """
    Retrieve map data within the specified bounds.

    Arguments:
    - l (float): The left boundary value.
    - b (float): The bottom boundary value.
    - r (float): The right boundary value.
    - t (float): The top boundary value.

    Returns:
    - json: A json containing the result of the query.

    Raises:
    - HTTPException(400): If the bounds are invalid.
    """
    bounds = (l, b, r, t)
    if (len(bounds) != 4 or
        bounds[2] - bounds[0] < 0 or 
        bounds[3] - bounds[1] < 0
        ):
        raise HTTPException(status_code=400, detail="Invalid bounds")
    res = await mongo_client.get_in_bounds(bounds)
    return json.dumps(res)
