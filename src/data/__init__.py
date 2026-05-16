"""Data pipeline package."""

__all__ = ["PipelinePaths", "run_pipeline"]


def __getattr__(name: str):
    if name in __all__:
        from src.data.silver_pipeline import PipelinePaths, run_pipeline

        exports = {"PipelinePaths": PipelinePaths, "run_pipeline": run_pipeline}
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
