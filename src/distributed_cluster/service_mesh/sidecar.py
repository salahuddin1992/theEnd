"""
Sidecar proxy configuration for Istio/Envoy integration.
"""

import json
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ProxyMode(Enum):
    """Sidecar proxy modes."""
    SIDECAR = "sidecar"
    GATEWAY = "gateway"
    ROUTER = "router"


class TrafficDirection(Enum):
    """Traffic interception direction."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BOTH = "both"


@dataclass
class TLSConfig:
    """TLS configuration for proxy."""
    enabled: bool = True
    mode: str = "ISTIO_MUTUAL"  # DISABLE, SIMPLE, MUTUAL, ISTIO_MUTUAL
    client_certificate: Optional[str] = None
    private_key: Optional[str] = None
    ca_certificates: Optional[str] = None
    min_protocol_version: str = "TLSv1_2"
    cipher_suites: List[str] = field(default_factory=list)


@dataclass
class AccessLogConfig:
    """Access logging configuration."""
    enabled: bool = True
    format: str = "JSON"  # JSON, TEXT
    path: str = "/dev/stdout"
    include_request_body: bool = False
    include_response_body: bool = False
    filter_state_objects: List[str] = field(default_factory=list)


@dataclass
class TracingConfig:
    """Distributed tracing configuration."""
    enabled: bool = True
    provider: str = "zipkin"  # zipkin, jaeger, lightstep, datadog
    sampling_rate: float = 1.0
    custom_tags: Dict[str, str] = field(default_factory=dict)
    max_tag_length: int = 256


@dataclass
class ProxyConfig:
    """General proxy configuration."""
    mode: ProxyMode = ProxyMode.SIDECAR
    direction: TrafficDirection = TrafficDirection.BOTH
    concurrency: int = 2
    drain_duration: int = 45
    termination_drain_duration: int = 5
    interception_mode: str = "REDIRECT"  # REDIRECT, TPROXY
    include_ip_ranges: List[str] = field(default_factory=list)
    exclude_ip_ranges: List[str] = field(default_factory=list)
    include_ports: List[int] = field(default_factory=list)
    exclude_ports: List[int] = field(default_factory=list)
    exclude_interfaces: List[str] = field(default_factory=list)
    tls: Optional[TLSConfig] = None
    access_log: Optional[AccessLogConfig] = None
    tracing: Optional[TracingConfig] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "direction": self.direction.value,
            "concurrency": self.concurrency,
            "drain_duration": self.drain_duration,
            "interception_mode": self.interception_mode,
            "include_ip_ranges": self.include_ip_ranges,
            "exclude_ip_ranges": self.exclude_ip_ranges,
            "include_ports": self.include_ports,
            "exclude_ports": self.exclude_ports,
        }


@dataclass
class EnvoyCluster:
    """Envoy cluster configuration."""
    name: str
    type: str = "STRICT_DNS"  # STATIC, STRICT_DNS, LOGICAL_DNS, EDS
    lb_policy: str = "ROUND_ROBIN"
    connect_timeout: float = 5.0
    http2_protocol_options: bool = False
    health_checks: List[Dict[str, Any]] = field(default_factory=list)
    circuit_breakers: Optional[Dict[str, Any]] = None
    outlier_detection: Optional[Dict[str, Any]] = None
    endpoints: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class EnvoyListener:
    """Envoy listener configuration."""
    name: str
    address: str = "0.0.0.0"
    port: int = 8080
    filter_chains: List[Dict[str, Any]] = field(default_factory=list)
    traffic_direction: str = "INBOUND"


@dataclass
class EnvoyRoute:
    """Envoy route configuration."""
    name: str
    domains: List[str] = field(default_factory=lambda: ["*"])
    routes: List[Dict[str, Any]] = field(default_factory=list)


class EnvoyConfig:
    """Envoy proxy configuration generator."""

    def __init__(self, service_name: str, config: Optional[ProxyConfig] = None):
        self.service_name = service_name
        self.config = config or ProxyConfig()
        self._clusters: List[EnvoyCluster] = []
        self._listeners: List[EnvoyListener] = []
        self._routes: List[EnvoyRoute] = []

    def add_cluster(self, cluster: EnvoyCluster):
        """Add a cluster configuration."""
        self._clusters.append(cluster)

    def add_listener(self, listener: EnvoyListener):
        """Add a listener configuration."""
        self._listeners.append(listener)

    def add_route(self, route: EnvoyRoute):
        """Add a route configuration."""
        self._routes.append(route)

    def generate_bootstrap(self) -> Dict[str, Any]:
        """Generate Envoy bootstrap configuration."""
        return {
            "node": {
                "id": f"{self.service_name}-sidecar",
                "cluster": self.service_name,
                "metadata": {
                    "ISTIO_VERSION": "1.17.0",
                    "MESH_ID": "mesh1",
                },
            },
            "admin": {
                "access_log_path": "/dev/null",
                "address": {
                    "socket_address": {
                        "address": "127.0.0.1",
                        "port_value": 15000,
                    }
                },
            },
            "static_resources": {
                "clusters": [self._generate_cluster(c) for c in self._clusters],
                "listeners": [self._generate_listener(l) for l in self._listeners],
            },
            "dynamic_resources": {
                "cds_config": {"ads": {}, "resource_api_version": "V3"},
                "lds_config": {"ads": {}, "resource_api_version": "V3"},
            },
        }

    def _generate_cluster(self, cluster: EnvoyCluster) -> Dict[str, Any]:
        """Generate cluster configuration."""
        config = {
            "name": cluster.name,
            "type": cluster.type,
            "lb_policy": cluster.lb_policy,
            "connect_timeout": f"{cluster.connect_timeout}s",
            "load_assignment": {
                "cluster_name": cluster.name,
                "endpoints": cluster.endpoints,
            },
        }

        if cluster.http2_protocol_options:
            config["http2_protocol_options"] = {}

        if cluster.health_checks:
            config["health_checks"] = cluster.health_checks

        if cluster.circuit_breakers:
            config["circuit_breakers"] = cluster.circuit_breakers

        if cluster.outlier_detection:
            config["outlier_detection"] = cluster.outlier_detection

        return config

    def _generate_listener(self, listener: EnvoyListener) -> Dict[str, Any]:
        """Generate listener configuration."""
        return {
            "name": listener.name,
            "address": {
                "socket_address": {
                    "address": listener.address,
                    "port_value": listener.port,
                }
            },
            "filter_chains": listener.filter_chains,
            "traffic_direction": listener.traffic_direction,
        }

    def generate_xds_config(self) -> Dict[str, Any]:
        """Generate xDS configuration for dynamic updates."""
        return {
            "version_info": str(int(time.time())),
            "resources": [
                {
                    "@type": "type.googleapis.com/envoy.config.cluster.v3.Cluster",
                    **self._generate_cluster(c)
                }
                for c in self._clusters
            ],
        }

    def to_yaml(self) -> str:
        """Export configuration as YAML."""
        try:
            import yaml
            return yaml.dump(self.generate_bootstrap(), default_flow_style=False)
        except ImportError:
            return json.dumps(self.generate_bootstrap(), indent=2)


@dataclass
class IstioDestinationRule:
    """Istio DestinationRule configuration."""
    name: str
    host: str
    traffic_policy: Optional[Dict[str, Any]] = None
    subsets: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "apiVersion": "networking.istio.io/v1beta1",
            "kind": "DestinationRule",
            "metadata": {"name": self.name},
            "spec": {
                "host": self.host,
                "trafficPolicy": self.traffic_policy,
                "subsets": self.subsets,
            },
        }


@dataclass
class IstioVirtualService:
    """Istio VirtualService configuration."""
    name: str
    hosts: List[str]
    http_routes: List[Dict[str, Any]] = field(default_factory=list)
    gateways: List[str] = field(default_factory=list)
    timeout: Optional[str] = None
    retries: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        spec = {
            "hosts": self.hosts,
            "http": self.http_routes,
        }
        if self.gateways:
            spec["gateways"] = self.gateways
        if self.timeout:
            for route in spec["http"]:
                route["timeout"] = self.timeout
        if self.retries:
            for route in spec["http"]:
                route["retries"] = self.retries

        return {
            "apiVersion": "networking.istio.io/v1beta1",
            "kind": "VirtualService",
            "metadata": {"name": self.name},
            "spec": spec,
        }


class IstioConfig:
    """Istio configuration generator."""

    def __init__(self, namespace: str = "default"):
        self.namespace = namespace
        self._destination_rules: List[IstioDestinationRule] = []
        self._virtual_services: List[IstioVirtualService] = []

    def add_destination_rule(self, rule: IstioDestinationRule):
        """Add a destination rule."""
        self._destination_rules.append(rule)

    def add_virtual_service(self, service: IstioVirtualService):
        """Add a virtual service."""
        self._virtual_services.append(service)

    def create_canary_config(
        self,
        service_name: str,
        stable_version: str,
        canary_version: str,
        canary_weight: int = 10
    ) -> tuple:
        """Create canary deployment configuration."""
        destination_rule = IstioDestinationRule(
            name=f"{service_name}-destination",
            host=service_name,
            subsets=[
                {"name": "stable", "labels": {"version": stable_version}},
                {"name": "canary", "labels": {"version": canary_version}},
            ],
        )

        virtual_service = IstioVirtualService(
            name=f"{service_name}-vs",
            hosts=[service_name],
            http_routes=[
                {
                    "route": [
                        {"destination": {"host": service_name, "subset": "stable"}, "weight": 100 - canary_weight},
                        {"destination": {"host": service_name, "subset": "canary"}, "weight": canary_weight},
                    ]
                }
            ],
        )

        self.add_destination_rule(destination_rule)
        self.add_virtual_service(virtual_service)

        return destination_rule, virtual_service

    def create_circuit_breaker_config(
        self,
        service_name: str,
        max_connections: int = 100,
        max_pending_requests: int = 100,
        max_requests: int = 1000,
        max_retries: int = 3,
        consecutive_errors: int = 5,
        base_ejection_time: str = "30s"
    ) -> IstioDestinationRule:
        """Create circuit breaker configuration."""
        destination_rule = IstioDestinationRule(
            name=f"{service_name}-circuit-breaker",
            host=service_name,
            traffic_policy={
                "connectionPool": {
                    "tcp": {"maxConnections": max_connections},
                    "http": {
                        "h2UpgradePolicy": "UPGRADE",
                        "http1MaxPendingRequests": max_pending_requests,
                        "http2MaxRequests": max_requests,
                        "maxRetries": max_retries,
                    },
                },
                "outlierDetection": {
                    "consecutiveErrors": consecutive_errors,
                    "interval": "10s",
                    "baseEjectionTime": base_ejection_time,
                    "maxEjectionPercent": 50,
                },
            },
        )

        self.add_destination_rule(destination_rule)
        return destination_rule

    def export_all(self) -> str:
        """Export all configurations as YAML."""
        try:
            import yaml

            configs = []
            for dr in self._destination_rules:
                configs.append(dr.to_dict())
            for vs in self._virtual_services:
                configs.append(vs.to_dict())

            return "---\n".join(yaml.dump(c, default_flow_style=False) for c in configs)
        except ImportError:
            return json.dumps([dr.to_dict() for dr in self._destination_rules] +
                            [vs.to_dict() for vs in self._virtual_services], indent=2)


class TrafficInterceptor:
    """Intercepts and processes traffic for sidecar proxy."""

    def __init__(self, config: Optional[ProxyConfig] = None):
        self.config = config or ProxyConfig()
        self._inbound_handlers: List[Callable] = []
        self._outbound_handlers: List[Callable] = []
        self._lock = threading.Lock()
        self._stats = {
            "inbound_requests": 0,
            "outbound_requests": 0,
            "inbound_bytes": 0,
            "outbound_bytes": 0,
            "errors": 0,
        }

    def add_inbound_handler(self, handler: Callable):
        """Add handler for inbound traffic."""
        with self._lock:
            self._inbound_handlers.append(handler)

    def add_outbound_handler(self, handler: Callable):
        """Add handler for outbound traffic."""
        with self._lock:
            self._outbound_handlers.append(handler)

    def intercept_inbound(self, request: Any) -> Any:
        """Intercept inbound request."""
        with self._lock:
            self._stats["inbound_requests"] += 1

        for handler in self._inbound_handlers:
            try:
                request = handler(request)
            except Exception as e:
                logger.error(f"Inbound handler error: {e}")
                self._stats["errors"] += 1

        return request

    def intercept_outbound(self, request: Any) -> Any:
        """Intercept outbound request."""
        with self._lock:
            self._stats["outbound_requests"] += 1

        for handler in self._outbound_handlers:
            try:
                request = handler(request)
            except Exception as e:
                logger.error(f"Outbound handler error: {e}")
                self._stats["errors"] += 1

        return request

    def get_stats(self) -> Dict[str, int]:
        """Get interceptor statistics."""
        with self._lock:
            return dict(self._stats)


class SidecarProxy:
    """Main sidecar proxy implementation."""

    def __init__(
        self,
        service_name: str,
        config: Optional[ProxyConfig] = None
    ):
        self.service_name = service_name
        self.config = config or ProxyConfig()
        self.envoy_config = EnvoyConfig(service_name, config)
        self.istio_config = IstioConfig()
        self.interceptor = TrafficInterceptor(config)
        self._running = False
        self._health_status = "healthy"

    def start(self):
        """Start the sidecar proxy."""
        self._running = True
        logger.info(f"Started sidecar proxy for {self.service_name}")

    def stop(self):
        """Stop the sidecar proxy."""
        self._running = False
        logger.info(f"Stopped sidecar proxy for {self.service_name}")

    def is_healthy(self) -> bool:
        """Check if proxy is healthy."""
        return self._running and self._health_status == "healthy"

    def get_config(self) -> Dict[str, Any]:
        """Get proxy configuration."""
        return {
            "service_name": self.service_name,
            "config": self.config.to_dict(),
            "running": self._running,
            "health_status": self._health_status,
            "stats": self.interceptor.get_stats(),
        }

    def apply_destination_rule(self, rule: IstioDestinationRule):
        """Apply an Istio destination rule."""
        self.istio_config.add_destination_rule(rule)
        logger.info(f"Applied destination rule: {rule.name}")

    def apply_virtual_service(self, service: IstioVirtualService):
        """Apply an Istio virtual service."""
        self.istio_config.add_virtual_service(service)
        logger.info(f"Applied virtual service: {service.name}")

    def export_envoy_config(self) -> str:
        """Export Envoy configuration."""
        return self.envoy_config.to_yaml()

    def export_istio_config(self) -> str:
        """Export Istio configuration."""
        return self.istio_config.export_all()
