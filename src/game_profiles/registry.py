from src.game_profiles.contracts import GameProfile
from src.game_profiles.heist import HeistRuntime
from src.game_profiles.survival import SurvivalRuntime

_PROFILES = {}


def register(profile):
    if (
        profile.id in _PROFILES
        or profile.version != 1
        or profile.mode not in ("phase", "calendar")
        or not 1 <= profile.actions_per_stage <= 2
        or not set(profile.ui_sections) <= {"actors", "resources", "clocks", "history"}
    ):
        raise ValueError("invalid or duplicate game profile")
    _PROFILES[profile.id] = profile


def resolve(identity, version=1):
    if not isinstance(identity, str):
        raise ValueError("game profile identity must be a string")
    profile = _PROFILES.get(identity)
    if profile is None or type(version) is not int or version != profile.version:
        raise ValueError("game profile is missing or has an unsupported version")
    return profile


def catalog():
    return [
        {
            "id": profile.id,
            "version": profile.version,
            "title": profile.title,
            "mode": profile.mode,
            "phases": list(profile.phases),
            "ui_sections": list(profile.ui_sections),
        }
        for profile in _PROFILES.values()
    ]


register(
    GameProfile(
        "core:demo-heist",
        1,
        "Heist: the sealed vault",
        "phase",
        ("planning", "operation", "downtime"),
        2,
        ("actors", "clocks", "resources", "history"),
        HeistRuntime(),
    )
)
register(
    GameProfile(
        "core:demo-survival",
        1,
        "Survival: five days at the shelter",
        "calendar",
        ("day",),
        1,
        ("resources", "actors", "history"),
        SurvivalRuntime(),
    )
)
