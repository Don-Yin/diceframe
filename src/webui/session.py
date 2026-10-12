"""Session 中间件 —— UUID token + cookie，轻量身份系统。"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

from src.webui.cors import is_allowed_cors_origin

logger = logging.getLogger("trpg")


class SessionManager:
    """管理 player session：cookie → user_id 映射。"""

    def __init__(self, data_dir: Path):
        self._path = data_dir / "sessions.json"
        self._sessions: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._sessions = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                self._sessions = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(self._sessions, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        tmp_path.replace(self._path)

    def get_or_create(self, token: str | None) -> tuple[str, str]:
        """返回 (session_token, user_id)。"""
        if token and token in self._sessions:
            return token, self._sessions[token]["user_id"]

        token = token or uuid.uuid4().hex
        existing_user_ids = {session["user_id"] for session in self._sessions.values()}
        user_id = f"web_{uuid.uuid4().hex[:8]}"
        while user_id in existing_user_ids:
            user_id = f"web_{uuid.uuid4().hex[:8]}"
        self._sessions[token] = {
            "user_id": user_id,
            "name": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()
        return token, user_id

    def set_name(self, token: str, name: str) -> None:
        if token in self._sessions:
            self._sessions[token]["name"] = name
            self._save()

    def get_name(self, token: str) -> str:
        return self._sessions.get(token, {}).get("name", "")

    def revoke_game_binding(self, user_id: str, game_key: str) -> int:
        """Stop sessions bound to ``user_id`` from speaking for it in one game.

        Bindings are one uid per session, shared by every game. A seat's
        credential being rotated, or the seat being removed, must cut those
        sessions off in *that* game only: the session keeps its uid (and any
        seat it holds elsewhere) and is just an anonymous visitor here.
        """
        if not user_id or not game_key:
            return 0
        changed = 0
        for session in self._sessions.values():
            if session.get("user_id") != user_id:
                continue
            revoked = session.setdefault("revoked_games", [])
            if game_key not in revoked:
                revoked.append(game_key)
                changed += 1
        if changed:
            self._save()
        return changed

    def count_bound(self, user_id: str, game_key: str) -> int:
        """How many sessions still speak for ``user_id`` in ``game_key``.

        A session counts for a game it has entered with that uid. Sessions
        from before games were recorded have no ``games`` list and are
        counted conservatively (they may be bound here).
        """
        if not user_id:
            return 0
        count = 0
        for session in self._sessions.values():
            if session.get("user_id") != user_id:
                continue
            if game_key in (session.get("revoked_games") or []):
                continue
            games = session.get("games")
            if isinstance(games, list) and game_key not in games:
                continue
            count += 1
        return count

    def note_game(self, token: str, game_key: str) -> None:
        """Record that this session holds its uid's seat in ``game_key``."""
        session = self._sessions.get(token)
        if session is None or not game_key:
            return
        games = session.setdefault("games", [])
        if game_key not in games:
            games.append(game_key)
            self._save()

    def revoked_games(self, token: str) -> frozenset[str]:
        return frozenset(self._sessions.get(token, {}).get("revoked_games") or [])

    def rebind(self, token: str, user_id: str, game_key: str = "") -> None:
        """把当前 session token 绑定到指定 user_id（换设备恢复身份用）。"""
        session = self._sessions.get(token)
        if session is None:
            return
        if session.get("user_id") != user_id:
            # A new identity: revocations and game records were about the old one.
            session["user_id"] = user_id
            session.pop("revoked_games", None)
            session.pop("games", None)
        elif game_key:
            # Re-entering one game (with that seat's token) lifts only that
            # game's revocation; other games stay revoked.
            revoked = session.get("revoked_games") or []
            if game_key in revoked:
                revoked.remove(game_key)
        if game_key:
            games = session.setdefault("games", [])
            if game_key not in games:
                games.append(game_key)
        self._save()


@web.middleware
async def session_middleware(request: web.Request, handler) -> web.StreamResponse:
    """aiohttp 中间件：解析 session token，注入 user_id。"""
    mgr: SessionManager = request.app.get("session_manager")
    if not mgr:
        return await handler(request)

    token = request.cookies.get("trpg_session")
    new_token, user_id = mgr.get_or_create(token)
    request["user_id"] = user_id
    request["session_token"] = new_token
    request["session_revoked_games"] = mgr.revoked_games(new_token)

    response = await handler(request)
    if new_token != token:
        cross_origin = is_allowed_cors_origin(request)
        response.set_cookie(
            "trpg_session",
            new_token,
            httponly=True,
            path="/",
            max_age=7 * 86400,
            samesite="None" if cross_origin else "Lax",
            secure=cross_origin,
        )
    return response
