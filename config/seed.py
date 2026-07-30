"""Seed stratejisi: il bazlı bağımsız RNG (bkz. prompt-v2 §11, onaylı iyileştirme).

Tek bir `default_rng(SEED)` yerine `SeedSequence(SEED).spawn(len(IL_SIRASI))` kullanılır —
hem determinizmi korur hem de tek bir ilin bağımsız yeniden üretilmesine izin verir.
"""

import numpy as np

from config.provinces import IL_SIRASI

SEED = 20260727

_ss = np.random.SeedSequence(SEED)
_CHILD_SEEDS = dict(zip(IL_SIRASI, _ss.spawn(len(IL_SIRASI))))


def rng_for_il(il_kodu: int) -> np.random.Generator:
    return np.random.default_rng(_CHILD_SEEDS[il_kodu])
