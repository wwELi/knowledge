from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    text: str
    page: int
