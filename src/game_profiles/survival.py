"""Five-day cooperative shelter demo with explicit upkeep and build costs."""

from src.game_profiles.contracts import integer, validate_common


class SurvivalRuntime:
    def initial(self, players):
        return {
            "revision": 0,
            "status": "active",
            "resources": {
                "food": 3 * len(players),
                "water": 3 * len(players),
                "supplies": 3,
                "base": 0,
                "relationships": 0,
            },
            "weather": "clear",
            "clocks": {},
            "history": [],
            "actors": {uid: {"health": 5, "inventory": []} for uid in players},
        }

    def validate(self, state):
        validate_common(state)
        if (
            set(state.get("resources", {}))
            != {"food", "water", "supplies", "base", "relationships"}
            or state.get("weather") not in ("clear", "rain", "storm")
            or state.get("clocks") != {}
        ):
            raise ValueError("invalid shelter resources or weather")
        for key in ("food", "water", "supplies"):
            integer(state["resources"][key], 0, 100)
        integer(state["resources"]["base"], 0, 3)
        integer(state["resources"]["relationships"], -3, 3)
        for actor in state["actors"].values():
            if not isinstance(actor, dict):
                raise ValueError("invalid shelter actor")
            integer(actor.get("health"), 0, 5)
            if (
                not isinstance(actor.get("inventory"), list)
                or len(actor["inventory"]) > 12
                or any(item != "medkit" for item in actor["inventory"])
            ):
                raise ValueError("invalid shelter inventory")

    def legal(self, state, time, uid):
        actor, resources = state["actors"][uid], state["resources"]
        if state["status"] != "active" or actor["health"] == 0:
            return []
        moves = ["forage", "explore", "gather"]
        if resources["supplies"] >= 2 and len(actor["inventory"]) < 12:
            moves.append("craft")
        if resources["supplies"] >= 3 and resources["base"] < 3:
            moves.append("build")
        if actor["health"] < 5 and resources["food"] > 0:
            moves.append("rest")
        if actor["health"] < 5 and "medkit" in actor["inventory"]:
            moves.append("treat")
        return moves

    def move(self, state, time, uid, move, roll):
        actor, r = state["actors"][uid], state["resources"]
        success = roll >= 4
        if move == "forage":
            r["food"] = min(100, r["food"] + (3 if success else 1))
            r["water"] = min(100, r["water"] + 2)
        elif move == "gather":
            r["supplies"] = min(100, r["supplies"] + (3 if success else 1))
        elif move == "explore":
            r["water"] = min(100, r["water"] + 3)
            r["food"] = min(100, r["food"] + 2)
            r["relationships"] = min(3, r["relationships"] + 1)
            if not success:
                actor["health"] = max(0, actor["health"] - 1)
        elif move == "craft":
            r["supplies"] -= 2
            actor["inventory"].append("medkit")
        elif move == "build":
            r["supplies"] -= 3
            r["base"] += 1
        elif move == "rest":
            r["food"] -= 1
            actor["health"] = min(5, actor["health"] + 2)
        elif move == "treat":
            actor["inventory"].remove("medkit")
            actor["health"] = min(5, actor["health"] + 3)
        return {"move_id": move, "roll": roll, "success": success}

    def advance(self, state, time, roll):
        living = [actor for actor in state["actors"].values() if actor["health"] > 0]
        r = state["resources"]
        shortage = r["food"] < len(living) or r["water"] < len(living)
        r["food"] = max(0, r["food"] - len(living))
        r["water"] = max(0, r["water"] - len(living))
        state["weather"] = "storm" if roll == 1 else "rain" if roll <= 3 else "clear"
        storm = state["weather"] == "storm" and r["base"] < 2
        for actor in living:
            actor["health"] = max(0, actor["health"] - int(shortage) - int(storm))
        if all(actor["health"] == 0 for actor in state["actors"].values()):
            state["status"] = "lost"
        elif time["day"] >= 5:
            state["status"] = "won"
        return {
            "roll": roll,
            "weather": state["weather"],
            "shortage": shortage,
            "storm_damage": storm,
            "status": state["status"],
        }
