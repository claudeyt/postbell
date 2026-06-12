class PostbellError(Exception):
    def __init__(self, message: str = "An error occurred"):
        self.message = message
        super().__init__(self.message)


class AuthError(PostbellError):
    def __init__(self, message: str = "Authentication error"):
        super().__init__(message)


class UploadError(PostbellError):
    def __init__(self, message: str = "Upload error"):
        super().__init__(message)


class QuotaExceededError(PostbellError):
    def __init__(self, message: str = "Daily quota exceeded"):
        super().__init__(message)


class RoutingError(PostbellError):
    def __init__(self, message: str = "Routing error"):
        super().__init__(message)


class ConfigError(PostbellError):
    def __init__(self, message: str = "Configuration error"):
        super().__init__(message)
