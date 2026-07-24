class WorkflowError(Exception):
    """Base exception for all workflow package errors."""
    pass

class StageNotFoundError(WorkflowError, KeyError):
    """Raised when a requested stage is not found."""
    pass

class StageAlreadyExistsError(WorkflowError, ValueError):
    """Raised when attempting to add a stage that already exists."""
    pass

class SweepNotFoundError(WorkflowError, KeyError):
    """Raised when a requested sweep is not found."""
    pass

class SweepAlreadyExistsError(WorkflowError, ValueError):
    """Raised when attempting to add a sweep that already exists."""
    pass

class VariableAlreadyExistsError(WorkflowError, ValueError):
    """Raised when attempting to add a variable that already exists."""
    pass

class VariableNotFoundError(WorkflowError, KeyError):
    """Raised when a variable is not found."""
    pass

class ConversionError(WorkflowError, TypeError, ValueError):
    """Raised when casting a variable value fails."""
    pass

class ServerNotRunningError(WorkflowError, ValueError):
    """Raised when the workflow server is not running but requested."""
    pass
