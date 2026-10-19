"""Small original heist demo, deliberately not a Blades rules implementation."""

from src.game_profiles.contracts import integer, validate_common

STATS = ("insight", "prowess", "sway", "resolve")
PHASE_MOVES = {
    "planning": ("study", "persuade", "acquire"),
    "operation": ("sneak", "force", "study"),
    "downtime": ("recover", "acquire"),
}


class HeistRuntime:
    def initial(self, players):
        return {
            "revision": 0,
            "status": "active",
            "resources": {"supplies": 4, "faction": 0},
            "clocks": {"preparation": 0, "alert": 0, "loot": 0},
            "history": [],
            "actors": {
                uid: {
                    "stats": dict(zip(STATS, (2, 2, 1, 1), strict=True)),
                    "stress": 0,
                    "harm": 0,
                    "inventory": [],
                }
                for uid in players
            },
        }

    def validate(self, state):
        validate_common(state)
        if set(state.get("resources", {})) != {"supplies", "faction"} or set(
            state.get("clocks", {})
        ) != {"preparation", "alert", "loot"}:
            raise ValueError("invalid heist resources")
        integer(state["resources"]["supplies"], 0, 20)
        integer(state["resources"]["faction"], -3, 3)
        for value in state["clocks"].values():
            integer(value, 0, 4)
        for actor in state["actors"].values():
            if not isinstance(actor, dict) or set(actor.get("stats", {})) != set(STATS):
                raise ValueError("invalid heist stats")
            for value in actor["stats"].values():
                integer(value, 0, 3)
            integer(actor.get("stress"), 0, 9)
            integer(actor.get("harm"), 0, 3)
            if (
                not isinstance(actor.get("inventory"), list)
                or len(actor["inventory"]) > 12
                or any(item != "toolkit" for item in actor["inventory"])
            ):
                raise ValueError("invalid heist inventory")

    def legal(self, state, time, uid):
        actor = state["actors"][uid]
        if (
            state["status"] != "active"
            or actor["harm"] >= 3
            or actor["stress"] >= 9
            and time["phase"] != "downtime"
        ):
            return []
        return [
            move
            for move in PHASE_MOVES[time["phase"]]
            if move != "acquire"
            or (state["resources"]["supplies"] > 0 and len(actor["inventory"]) < 12)
        ]

    def move(self, state, time, uid, move, roll):
        actor = state["actors"][uid]
        stat = {
            "study": "insight",
            "persuade": "sway",
            "sneak": "prowess",
            "force": "prowess",
            "recover": "resolve",
            "acquire": "insight",
        }[move]
        bonus = (
            state["clocks"]["preparation"] // 2 if time["phase"] == "operation" else 0
        )
        used_tool = move in ("sneak", "force") and "toolkit" in actor["inventory"]
        if used_tool:
            actor["inventory"].remove("toolkit")
            bonus += 1
        success = roll + actor["stats"][stat] + bonus >= 6
        if move == "recover":
            actor["stress"] = max(0, actor["stress"] - 3)
            actor["harm"] = max(0, actor["harm"] - 1)
        elif move == "acquire":
            state["resources"]["supplies"] -= 1
            actor["inventory"].append("toolkit")
        elif time["phase"] == "planning":
            state["clocks"]["preparation"] = min(
                4, state["clocks"]["preparation"] + (2 if success else 1)
            )
            if move == "persuade" and success:
                state["resources"]["faction"] = min(
                    3, state["resources"]["faction"] + 1
                )
        else:
            state["clocks"]["loot"] = min(
                4, state["clocks"]["loot"] + (2 if success else 1)
            )
            if not success:
                state["clocks"]["alert"] = min(4, state["clocks"]["alert"] + 1)
                actor["stress"] = min(9, actor["stress"] + 2)
                if move == "force":
                    actor["harm"] = min(3, actor["harm"] + 1)
        if state["clocks"]["alert"] == 4:
            state["status"] = "lost"
        return {
            "move_id": move,
            "roll": roll,
            "stat": stat,
            "bonus": bonus,
            "tool_used": used_tool,
            "success": success,
        }

    def advance(self, state, time, roll):
        if time["phase"] == "operation" and state["clocks"]["loot"] == 4:
            state["status"] = "won"
        return {"stage": time["phase"], "status": state["status"]}
