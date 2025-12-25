"""
Gateway Transforms - تحويلات البوابة
=====================================

Request/Response transformation utilities.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from .gateway import GatewayRequest, GatewayResponse

logger = logging.getLogger(__name__)


class Transform(ABC):
    """Base transform class."""

    @abstractmethod
    def apply(self, target: Any) -> Any:
        """Apply transformation."""
        pass


class RequestTransform(Transform):
    """Base class for request transformations."""

    @abstractmethod
    def apply(self, request: GatewayRequest) -> GatewayRequest:
        """Apply transformation to request."""
        pass


class ResponseTransform(Transform):
    """Base class for response transformations."""

    @abstractmethod
    def apply(self, response: GatewayResponse) -> GatewayResponse:
        """Apply transformation to response."""
        pass


class HeaderTransform(RequestTransform, ResponseTransform):
    """
    Header transformation.

    Add, remove, or modify headers.
    """

    def __init__(
        self,
        add: Optional[Dict[str, str]] = None,
        remove: Optional[List[str]] = None,
        rename: Optional[Dict[str, str]] = None,
        set_if_missing: Optional[Dict[str, str]] = None,
    ):
        self.add = add or {}
        self.remove = remove or []
        self.rename = rename or {}
        self.set_if_missing = set_if_missing or {}

    def apply(self, target: Union[GatewayRequest, GatewayResponse]) -> Union[GatewayRequest, GatewayResponse]:
        headers = dict(target.headers)

        # Remove headers
        for header in self.remove:
            headers.pop(header.lower(), None)

        # Rename headers
        for old_name, new_name in self.rename.items():
            if old_name.lower() in headers:
                headers[new_name.lower()] = headers.pop(old_name.lower())

        # Set if missing
        for name, value in self.set_if_missing.items():
            if name.lower() not in headers:
                headers[name.lower()] = value

        # Add/override headers
        for name, value in self.add.items():
            headers[name.lower()] = value

        target.headers = headers
        return target


class BodyTransform(RequestTransform, ResponseTransform):
    """
    Body transformation.

    Modify request/response body content.
    """

    def __init__(
        self,
        transform_fn: Optional[Callable[[bytes], bytes]] = None,
        json_transform: Optional[Callable[[Any], Any]] = None,
    ):
        self.transform_fn = transform_fn
        self.json_transform = json_transform

    def apply(self, target: Union[GatewayRequest, GatewayResponse]) -> Union[GatewayRequest, GatewayResponse]:
        if not target.body:
            return target

        if self.json_transform and "json" in target.content_type:
            try:
                data = json.loads(target.body.decode("utf-8"))
                data = self.json_transform(data)
                target.body = json.dumps(data).encode("utf-8")
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        elif self.transform_fn:
            target.body = self.transform_fn(target.body)

        return target


class URLRewriteTransform(RequestTransform):
    """
    URL rewriting transformation.

    Rewrite request paths using patterns.
    """

    def __init__(
        self,
        rules: Optional[List[Dict[str, str]]] = None,
    ):
        self.rules = rules or []
        self._compiled: List[tuple] = []

        for rule in self.rules:
            pattern = re.compile(rule["pattern"])
            replacement = rule["replacement"]
            self._compiled.append((pattern, replacement))

    def add_rule(self, pattern: str, replacement: str) -> None:
        """Add a rewrite rule."""
        self.rules.append({"pattern": pattern, "replacement": replacement})
        self._compiled.append((re.compile(pattern), replacement))

    def apply(self, request: GatewayRequest) -> GatewayRequest:
        path = request.path

        for pattern, replacement in self._compiled:
            new_path, count = pattern.subn(replacement, path)
            if count > 0:
                request.path = new_path
                logger.debug(f"URL rewrite: {path} -> {new_path}")
                break

        return request


class QueryTransform(RequestTransform):
    """
    Query string transformation.

    Add, remove, or modify query parameters.
    """

    def __init__(
        self,
        add: Optional[Dict[str, str]] = None,
        remove: Optional[List[str]] = None,
        rename: Optional[Dict[str, str]] = None,
    ):
        self.add = add or {}
        self.remove = remove or []
        self.rename = rename or {}

    def apply(self, request: GatewayRequest) -> GatewayRequest:
        # Parse query string
        params: Dict[str, str] = {}
        if request.query_string:
            for param in request.query_string.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    params[key] = value

        # Remove params
        for key in self.remove:
            params.pop(key, None)

        # Rename params
        for old_key, new_key in self.rename.items():
            if old_key in params:
                params[new_key] = params.pop(old_key)

        # Add params
        params.update(self.add)

        # Rebuild query string
        request.query_string = "&".join(f"{k}={v}" for k, v in params.items())

        return request


class JsonPathTransform(RequestTransform, ResponseTransform):
    """
    JSON path-based transformation.

    Modify specific fields in JSON body using path expressions.
    """

    def __init__(
        self,
        operations: Optional[List[Dict[str, Any]]] = None,
    ):
        self.operations = operations or []

    def add_operation(
        self,
        path: str,
        operation: str,
        value: Any = None,
    ) -> None:
        """
        Add a JSON path operation.

        Operations:
        - set: Set value at path
        - remove: Remove value at path
        - rename: Rename key at path
        - copy: Copy value from one path to another
        """
        self.operations.append({
            "path": path,
            "operation": operation,
            "value": value,
        })

    def apply(self, target: Union[GatewayRequest, GatewayResponse]) -> Union[GatewayRequest, GatewayResponse]:
        if not target.body or "json" not in target.content_type:
            return target

        try:
            data = json.loads(target.body.decode("utf-8"))

            for op in self.operations:
                data = self._apply_operation(data, op)

            target.body = json.dumps(data).encode("utf-8")

        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        return target

    def _apply_operation(self, data: Any, op: Dict[str, Any]) -> Any:
        """Apply a single operation."""
        path = op["path"].split(".")
        operation = op["operation"]
        value = op.get("value")

        if operation == "set":
            return self._set_path(data, path, value)
        elif operation == "remove":
            return self._remove_path(data, path)
        elif operation == "rename":
            return self._rename_path(data, path, value)

        return data

    def _set_path(self, data: Any, path: List[str], value: Any) -> Any:
        """Set value at path."""
        if not path:
            return value

        if isinstance(data, dict):
            key = path[0]
            if len(path) == 1:
                data[key] = value
            else:
                if key not in data:
                    data[key] = {}
                data[key] = self._set_path(data[key], path[1:], value)

        return data

    def _remove_path(self, data: Any, path: List[str]) -> Any:
        """Remove value at path."""
        if not path:
            return data

        if isinstance(data, dict):
            key = path[0]
            if len(path) == 1:
                data.pop(key, None)
            elif key in data:
                self._remove_path(data[key], path[1:])

        return data

    def _rename_path(self, data: Any, path: List[str], new_name: str) -> Any:
        """Rename key at path."""
        if not path or not new_name:
            return data

        if isinstance(data, dict):
            key = path[0]
            if len(path) == 1 and key in data:
                data[new_name] = data.pop(key)
            elif key in data:
                self._rename_path(data[key], path[1:], new_name)

        return data


class TransformChain:
    """
    Chain of transforms applied in sequence.

    Example:
        chain = TransformChain()
        chain.add_request_transform(HeaderTransform(add={"x-custom": "value"}))
        chain.add_request_transform(URLRewriteTransform(rules=[...]))

        request = chain.apply_request(request)
    """

    def __init__(self):
        self._request_transforms: List[RequestTransform] = []
        self._response_transforms: List[ResponseTransform] = []

    def add_request_transform(self, transform: RequestTransform) -> None:
        """Add a request transform."""
        self._request_transforms.append(transform)

    def add_response_transform(self, transform: ResponseTransform) -> None:
        """Add a response transform."""
        self._response_transforms.append(transform)

    def apply_request(self, request: GatewayRequest) -> GatewayRequest:
        """Apply all request transforms."""
        for transform in self._request_transforms:
            request = transform.apply(request)
        return request

    def apply_response(self, response: GatewayResponse) -> GatewayResponse:
        """Apply all response transforms."""
        for transform in self._response_transforms:
            response = transform.apply(response)
        return response


class TemplateTransform(ResponseTransform):
    """
    Template-based response transformation.

    Wrap response in a template.
    """

    def __init__(
        self,
        template: str,
        content_type: str = "application/json",
    ):
        self.template = template
        self.content_type = content_type

    def apply(self, response: GatewayResponse) -> GatewayResponse:
        if not response.body:
            return response

        try:
            data = json.loads(response.body.decode("utf-8"))

            # Simple template substitution
            result = self.template
            result = result.replace("{{data}}", json.dumps(data))
            result = result.replace("{{status}}", str(response.status_code))

            response.body = result.encode("utf-8")
            response.set_header("content-type", self.content_type)

        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        return response


class MaskTransform(ResponseTransform):
    """
    Data masking transformation.

    Mask sensitive fields in response.
    """

    def __init__(
        self,
        fields: Optional[List[str]] = None,
        mask_char: str = "*",
        mask_length: int = 8,
    ):
        self.fields = fields or ["password", "secret", "token", "api_key", "credit_card"]
        self.mask_char = mask_char
        self.mask_length = mask_length

    def apply(self, response: GatewayResponse) -> GatewayResponse:
        if not response.body or "json" not in response.content_type:
            return response

        try:
            data = json.loads(response.body.decode("utf-8"))
            data = self._mask_recursive(data)
            response.body = json.dumps(data).encode("utf-8")

        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        return response

    def _mask_recursive(self, data: Any) -> Any:
        """Recursively mask sensitive fields."""
        if isinstance(data, dict):
            return {
                k: self._mask_value(k, v) if self._should_mask(k) else self._mask_recursive(v)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self._mask_recursive(item) for item in data]
        return data

    def _should_mask(self, key: str) -> bool:
        """Check if field should be masked."""
        key_lower = key.lower()
        return any(field in key_lower for field in self.fields)

    def _mask_value(self, key: str, value: Any) -> str:
        """Mask a value."""
        if isinstance(value, str) and len(value) > 4:
            return value[:2] + self.mask_char * self.mask_length + value[-2:]
        return self.mask_char * self.mask_length
