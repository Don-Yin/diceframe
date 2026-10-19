"""Shared sanity-loss transitions for narrative and recovery settlements.

These retain DiceFrame's existing light insanity model. They are not a full
implementation of the CoC insanity rules, and never grant or restore SAN.
"""
from __future__ import annotations

import logging
import random
from typing import Any

from src.engine.modules import progression_state

logger = logging.getLogger('trpg')


def apply_sanity_loss(instance: Any, uid: str, sheet: dict, loss: int,
                      *, rng: random.Random | None = None) -> None:
    if sheet.get('sanity', 99) <= 0 and not sheet.get('deceased'):
        sheet['deceased'] = True
        sheet['death_cause'] = '永久疯狂'
        sheet['death_round'] = progression_state.round_value(instance)
        logger.info('%s 因永久疯狂而不可操作 (round=%d)', uid, progression_state.round_value(instance))
        return
    if loss < 5:
        return
    long_term = loss >= 10
    maximum = 10 if long_term else 3
    sheet['madness'] = {
        'type': 'long_term' if long_term else 'temporary',
        'remaining_rounds': rng.randint(1, maximum) if rng is not None else random.randint(1, maximum),
        'symptom': '持续行为异常' if long_term else '临时行为异常',
    }
    logger.info('%s 进入疯狂状态 (round=%d, rounds=%d)', uid,
                progression_state.round_value(instance), sheet['madness']['remaining_rounds'])
