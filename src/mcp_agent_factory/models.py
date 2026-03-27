"""Pydantic v2 models for tool argument and output validation."""
from pydantic import BaseModel


class EchoInput(BaseModel):
	message: str


class EchoOutput(BaseModel):
	text: str


class AddInput(BaseModel):
	a: float
	b: float


class AddOutput(BaseModel):
	result: float
