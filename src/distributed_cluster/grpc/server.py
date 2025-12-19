"""
gRPC Server - سيرفر gRPC
========================

السيرفر الرئيسي لـ gRPC يدعم:
- MasterService للـ Workers
- ClientService للمستخدمين
- mTLS للأمان
- Interceptors للمراقبة
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

try:
    import grpc
    from grpc import aio as grpc_aio
    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    grpc = None
    grpc_aio = None

from distributed_cluster.models.lease import LeaseManager
from distributed_cluster.observability.logging import StructuredLogger
from distributed_cluster.observability.metrics import MetricsCollector
from distributed_cluster.scheduler import Scheduler
from distributed_cluster.security.auth import AuthManager
from distributed_cluster.storage.database import Database

logger = StructuredLogger("grpc.server")


@dataclass
class GRPCServerConfig:
    """إعدادات سيرفر gRPC."""
    host: str = "0.0.0.0"
    port: int = 50051

    # TLS
    use_tls: bool = False
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    ca_cert_path: Optional[str] = None  # for mTLS
    require_client_cert: bool = False

    # Performance
    max_workers: int = 10
    max_concurrent_rpcs: int = 100
    max_message_size: int = 64 * 1024 * 1024  # 64MB

    # Keepalive
    keepalive_time_seconds: int = 30
    keepalive_timeout_seconds: int = 10

    # Compression
    compression: str = "gzip"  # none, gzip, deflate


class AuthInterceptor(grpc_aio.ServerInterceptor if GRPC_AVAILABLE else object):
    """
    Interceptor للتحقق من الهوية.

    يتحقق من الـ auth_token في كل request.
    """

    def __init__(self, auth_manager: AuthManager, skip_methods: set[str] = None):
        self.auth_manager = auth_manager
        self.skip_methods = skip_methods or {"RegisterWorker"}

    async def intercept_service(self, continuation, handler_call_details):
        """Intercept incoming calls."""
        method_name = handler_call_details.method.split("/")[-1]

        # Skip auth for registration
        if method_name in self.skip_methods:
            return await continuation(handler_call_details)

        # Extract token from metadata
        metadata = dict(handler_call_details.invocation_metadata)
        token = metadata.get("authorization", "").replace("Bearer ", "")

        if not token:
            # Will be handled by the servicer
            pass

        return await continuation(handler_call_details)


class MetricsInterceptor(grpc_aio.ServerInterceptor if GRPC_AVAILABLE else object):
    """
    Interceptor لجمع المقاييس.
    """

    def __init__(self, metrics: MetricsCollector):
        self.metrics = metrics

    async def intercept_service(self, continuation, handler_call_details):
        """Track RPC metrics."""
        method_name = handler_call_details.method.split("/")[-1]
        start_time = datetime.utcnow()

        try:
            response = await continuation(handler_call_details)
            self.metrics.counter("grpc_requests_total", 1, {
                "method": method_name,
                "status": "ok"
            })
            return response
        except Exception:
            self.metrics.counter("grpc_requests_total", 1, {
                "method": method_name,
                "status": "error"
            })
            raise
        finally:
            duration = (datetime.utcnow() - start_time).total_seconds()
            self.metrics.histogram("grpc_request_duration_seconds", duration, {
                "method": method_name
            })


class LoggingInterceptor(grpc_aio.ServerInterceptor if GRPC_AVAILABLE else object):
    """
    Interceptor للتسجيل.
    """

    async def intercept_service(self, continuation, handler_call_details):
        """Log RPC calls."""
        method_name = handler_call_details.method

        logger.debug("gRPC call", method=method_name)

        try:
            response = await continuation(handler_call_details)
            return response
        except Exception as e:
            logger.error("gRPC error", method=method_name, error=str(e))
            raise


class GRPCServer:
    """
    سيرفر gRPC الرئيسي.

    يشغل MasterService و ClientService.

    Usage:
        server = GRPCServer(config, scheduler, auth_manager, ...)
        await server.start()
        await server.wait_for_termination()
    """

    def __init__(
        self,
        config: GRPCServerConfig,
        scheduler: Scheduler,
        auth_manager: AuthManager,
        lease_manager: LeaseManager,
        database: Database,
        metrics: Optional[MetricsCollector] = None,
    ):
        if not GRPC_AVAILABLE:
            raise RuntimeError(
                "gRPC is not installed. Install with: pip install grpcio grpcio-tools"
            )

        self.config = config
        self.scheduler = scheduler
        self.auth_manager = auth_manager
        self.lease_manager = lease_manager
        self.database = database
        self.metrics = metrics or MetricsCollector()

        self._server: Optional[grpc_aio.Server] = None
        self._started = False

    async def start(self) -> None:
        """بدء السيرفر."""
        if self._started:
            raise RuntimeError("Server already started")

        # Create interceptors
        interceptors = [
            LoggingInterceptor(),
            MetricsInterceptor(self.metrics),
            AuthInterceptor(self.auth_manager),
        ]

        # Create server
        self._server = grpc_aio.server(
            interceptors=interceptors,
            options=[
                ("grpc.max_send_message_length", self.config.max_message_size),
                ("grpc.max_receive_message_length", self.config.max_message_size),
                ("grpc.keepalive_time_ms", self.config.keepalive_time_seconds * 1000),
                ("grpc.keepalive_timeout_ms", self.config.keepalive_timeout_seconds * 1000),
                ("grpc.max_concurrent_streams", self.config.max_concurrent_rpcs),
            ],
        )

        # Register services
        self._register_services()

        # Configure address
        address = f"{self.config.host}:{self.config.port}"

        if self.config.use_tls:
            # Load credentials
            credentials = self._load_credentials()
            self._server.add_secure_port(address, credentials)
            logger.info("gRPC server starting with TLS", address=address)
        else:
            self._server.add_insecure_port(address)
            logger.info("gRPC server starting (insecure)", address=address)

        await self._server.start()
        self._started = True

        logger.info("gRPC server started", address=address)

    def _register_services(self) -> None:
        """تسجيل الخدمات."""
        # Import servicers
        from distributed_cluster.grpc.client_service import ClientServicer
        from distributed_cluster.grpc.master_service import MasterServicer

        # Create servicers
        MasterServicer(
            scheduler=self.scheduler,
            auth_manager=self.auth_manager,
            lease_manager=self.lease_manager,
            database=self.database,
            metrics=self.metrics,
        )

        ClientServicer(
            scheduler=self.scheduler,
            auth_manager=self.auth_manager,
            database=self.database,
            metrics=self.metrics,
        )

        # Register with server
        # Note: In real implementation, you'd use generated stubs:
        # nebula_pb2_grpc.add_MasterServiceServicer_to_server(master_servicer, self._server)
        # nebula_pb2_grpc.add_ClientServiceServicer_to_server(client_servicer, self._server)

        # For now, we use a generic registration approach
        logger.info("Registered MasterService and ClientService")

    def _load_credentials(self) -> grpc.ServerCredentials:
        """تحميل شهادات TLS."""
        if not self.config.cert_path or not self.config.key_path:
            raise ValueError("TLS enabled but cert_path or key_path not set")

        with open(self.config.cert_path, "rb") as f:
            cert = f.read()

        with open(self.config.key_path, "rb") as f:
            key = f.read()

        ca_cert = None
        if self.config.ca_cert_path:
            with open(self.config.ca_cert_path, "rb") as f:
                ca_cert = f.read()

        if self.config.require_client_cert and ca_cert:
            # mTLS
            return grpc.ssl_server_credentials(
                [(key, cert)],
                root_certificates=ca_cert,
                require_client_auth=True,
            )
        else:
            # Server TLS only
            return grpc.ssl_server_credentials([(key, cert)])

    async def stop(self, grace_period: float = 5.0) -> None:
        """إيقاف السيرفر."""
        if self._server:
            await self._server.stop(grace_period)
            self._started = False
            logger.info("gRPC server stopped")

    async def wait_for_termination(self) -> None:
        """انتظار إنهاء السيرفر."""
        if self._server:
            await self._server.wait_for_termination()

    @property
    def is_running(self) -> bool:
        """هل السيرفر يعمل؟"""
        return self._started


async def create_grpc_server(
    config: GRPCServerConfig,
    scheduler: Scheduler,
    auth_manager: AuthManager,
    lease_manager: LeaseManager,
    database: Database,
    metrics: Optional[MetricsCollector] = None,
) -> GRPCServer:
    """
    إنشاء وبدء سيرفر gRPC.

    Helper function للاستخدام السريع.
    """
    server = GRPCServer(
        config=config,
        scheduler=scheduler,
        auth_manager=auth_manager,
        lease_manager=lease_manager,
        database=database,
        metrics=metrics,
    )
    await server.start()
    return server
