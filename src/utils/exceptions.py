"""Pipeline-specific exceptions. Narrow types so we can catch deliberately."""


class PipelineError(Exception):
    """Base class for all pipeline errors."""


class SchemaError(PipelineError):
    """Schema contract violated — usually a missing required column."""


class IngestionError(PipelineError):
    """A source file could not be read or parsed at the file level."""


class ValidationFailureError(PipelineError):
    """Hard data-quality check failed."""


class StateError(PipelineError):
    """Watermark / state file is missing or corrupt."""
