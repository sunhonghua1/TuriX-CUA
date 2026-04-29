from typing import Literal, Optional

from typing import List
from pydantic import BaseModel, Field
from src.controller.registry.views import ActionModel
# mlx-use actions 


class DoneAction(BaseModel):
	text: str

class InputTextAction(BaseModel):
	text: str

class TypeKeysAction(BaseModel):
	text: str
	app_name: Optional[str] = None

class RecordAction(BaseModel):
	text: str = Field(..., description="information you need to record")
	file_name: str = Field(..., description="filename summary for the recorded info")

class OpenAppAction(BaseModel):
	app_name: str

class AppleScriptAction(BaseModel):
	script: str

class PressAction(BaseModel):
	key: str

class PressCombinedAction(BaseModel):
	key1: str
	key2: str
	key3: Optional[str] = None

class LeftClickPositionAction(BaseModel):
	index: int

class RightClickPositionAction(BaseModel):
	index: int

class MoveToAction(BaseModel):
	position: List[float] = Field(..., description="Coordinates (normalised) [x,y]")

class LeftClickPixel(BaseModel):
    # Provide item type (int). You can also enforce a 2-length list by min_items/max_items if desired.
    position: List[float] = Field(..., description="Coordinates (normalised) [x,y]")

class RightClickPixel(BaseModel):
    position: List[float] = Field(..., description="Coordinates (normalised) [x,y]")

class ScrollUpAction(BaseModel):
	position: List[float] = Field(..., description="Coordinates (normalised) [x,y] to execute scroll")
	dx: Optional[int] = Field(..., description="Amount to scroll left, between 0 and 25")
	dy: Optional[int] = Field(..., description="Amount to scroll up, between 0 and 25. 25 is one page up")

class ScrollDownAction(BaseModel):
	position: List[float] = Field(..., description="Coordinates (normalised) [x,y] to execute scroll")
	dx: Optional[int] = Field(..., description="Amount to scroll left, between 0 and 25")
	dy: Optional[int] = Field(..., description="Amount to scroll down, between 0 and 25. 25 is one page down")

class ExtractAction(BaseModel):
	position1: List[float] = Field(..., description="Coordinates (normalised) [x,y]")

class DragAction(BaseModel):
	position1: List[float] = Field(..., description="Starting Coordinates (normalised) [x,y]")
	position2: List[float] = Field(..., description="Ending Coordinates (normalised) [x,y]")

class NoParamsAction(ActionModel):
	"""
	Simple parameter model requiring no arguments.
	"""
	pass

class RunScriptAction(BaseModel):
	"""Run a standalone Python helper script as a subprocess."""
	script_path: str = Field(..., description="Path to the Python script, e.g. 'src/mac/calc_helper.py'")
	args: List[str] = Field(default_factory=list, description="Arguments to pass to the script")
