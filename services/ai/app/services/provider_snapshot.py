"""Capture instance configuration and SDK dependencies at public operation entry."""
from copy import copy
from functools import wraps


def operation_snapshot(method):
    @wraps(method)
    def invoke(provider, *args, **kwargs):
        snapshot = copy(provider)
        snapshot._operation_adapter = provider._sdk_adapter()
        return method(snapshot, *args, **kwargs)
    return invoke
