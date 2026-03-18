"""Custom exceptions and global exception handlers."""

from fastapi import Request
from fastapi.responses import JSONResponse


class GameError(Exception):
    """Base game logic error."""

    def __init__(self, message: str, code: str = "GAME_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class RoomNotFoundError(GameError):
    def __init__(self, room_id: str):
        super().__init__(f"Room not found: {room_id}", "ROOM_NOT_FOUND")


class RoomFullError(GameError):
    def __init__(self):
        super().__init__("Room is full", "ROOM_FULL")


class InvalidActionError(GameError):
    def __init__(self, message: str):
        super().__init__(message, "INVALID_ACTION")


async def game_error_handler(_request: Request, exc: GameError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": exc.code, "message": exc.message},
    )
