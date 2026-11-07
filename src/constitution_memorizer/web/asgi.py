"""Back-compat import path. Hosted start uses constitution_memorizer.asgi:app."""

from constitution_memorizer.asgi import (  # noqa: F401
    BootSafeASGI,
    app,
    create_hosted_app,
    health_app,
)
