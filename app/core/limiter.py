"""Shared slowapi rate-limiter instance.

Import `limiter` here in both main.py (to attach to app.state)
and in route modules (to apply @limiter.limit decorators).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
