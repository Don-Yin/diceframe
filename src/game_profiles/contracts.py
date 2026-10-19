from dataclasses import dataclass
from typing import Protocol


class ProfileRuntime(Protocol):
    def initial(self, players: dict) -> dict: ...
    def validate(self, state: dict) -> None: ...
    def legal(self, state: dict, time: dict, uid: str) -> list[str]: ...
    def move(self, state: dict, time: dict, uid: str, move: str, roll: int) -> dict: ...
    def advance(self, state: dict, time: dict, roll: int) -> dict: ...


@dataclass(frozen=True)
class GameProfile:
    id: str
    version: int
    title: str
    mode: str
    phases: tuple[str, ...]
    actions_per_stage: int
    ui_sections: tuple[str, ...]
    runtime: ProfileRuntime


def integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("profile value outside its declared bounds")


def validate_common(state):
    integer(state.get("revision"), 0, 1000000)
    if state.get("status") not in ("active", "won", "lost"):
        raise ValueError("invalid profile status")
    if not isinstance(state.get("actors"), dict) or not 1 <= len(state["actors"]) <= 4:
        raise ValueError("invalid profile actors")
    if any(
        not isinstance(uid, str) or not uid or len(uid) > 128 for uid in state["actors"]
    ):
        raise ValueError("invalid profile actor identity")
    if not isinstance(state.get("history"), list) or len(state["history"]) > 100:
        raise ValueError("invalid profile history")
    previous = 0
    for event in state["history"]:
        if (
            not isinstance(event, dict)
            or event.get("type") not in ("move", "auto", "advance")
            or event.get("actor_uid") not in state["actors"]
        ):
            raise ValueError("invalid profile history event")
        integer(event.get("revision"), previous + 1, state["revision"])
        previous = event["revision"]
    if previous != state["revision"]:
        raise ValueError("profile history does not match its revision")
