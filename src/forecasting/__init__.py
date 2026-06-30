"""ROAScast shared forecasting core.

This package is the single math core imported by BOTH the scored offline path
(`predict.py`, run by the grader) and — in the product layer built later — the
FastAPI service. Keeping one code path means the demo and the scored output can
never disagree on the numbers.

Hard rule for everything in this package: NO network calls, NO LLM, NO web
framework. Those belong to the product layer on the other side of the wall.
"""

from . import schema, mapping, features, curves, model, reconcile  # noqa: F401

__all__ = ["schema", "mapping", "features", "curves", "model", "reconcile"]
__version__ = "1.0.0"
