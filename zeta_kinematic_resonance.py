"""Facade → geometry-off-zetas engine (correct direction).

Historical stub compared kinematics to actual γ_n. That direction is wrong.
This module only exposes geometry induced from the zeta field.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm import AnalysisResult, KinematicSpectralRealm, ZetaField, analyze_cycle

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class ZetaKinematicResonance(KinematicSpectralRealm):
    """Alias of the correct engine."""

    def __init__(self, d_distinctions: int = 3, r_relations: int = 8, **kwargs):
        super().__init__(**kwargs)
        self.D = d_distinctions
        self.R = r_relations
        import numpy as np

        self.topological_action_S_min = self.D * self.R * (2 * np.pi)

    def run(self) -> AnalysisResult:
        return self.analyze()


if __name__ == "__main__":
    res = analyze_cycle(N=11)
    logger.info("ontology: %s", res.summary()["ontology"])
    print(res.summary())
