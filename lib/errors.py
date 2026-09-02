class PipelineError(Exception):
    """Pipeline-specific error with severity level."""

    def __init__(self, message, level="ERROR"):
        super().__init__(message)
        self.message = message
        self.level = level
