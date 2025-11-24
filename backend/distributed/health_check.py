import asyncio
import time
from typing import Dict, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    status: HealthStatus
    timestamp: float = field(default_factory=time.time)
    response_time: float = 0.0
    message: Optional[str] = None
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "timestamp": datetime.fromtimestamp(self.timestamp).isoformat(),
            "response_time_ms": round(self.response_time * 1000, 2),
            "message": self.message,
            "details": self.details
        }


@dataclass
class HealthCheckConfig:
    service_name: str
    check_interval: float = 5.0
    timeout: float = 2.0
    failure_threshold: int = 3
    success_threshold: int = 2
    enabled: bool = True


class HealthChecker:

    def __init__(self):

        self._configs: Dict[str, HealthCheckConfig] = {}

        self._results: Dict[str, HealthCheckResult] = {}

        self._consecutive_failures: Dict[str, int] = {}
        self._consecutive_successes: Dict[str, int] = {}

        self._check_tasks: Dict[str, asyncio.Task] = {}

        self._check_functions: Dict[str, Callable[[], Awaitable[HealthCheckResult]]] = {}

        self._lock = asyncio.Lock()

        logger.info("Health Checker inicializado")

    async def register_check(
            self,
            service_name: str,
            check_function: Callable[[], Awaitable[HealthCheckResult]],
            config: Optional[HealthCheckConfig] = None
    ):

        async with self._lock:

            if config is None:
                config = HealthCheckConfig(service_name=service_name)

            self._configs[service_name] = config
            self._check_functions[service_name] = check_function
            self._consecutive_failures[service_name] = 0
            self._consecutive_successes[service_name] = 0

            if config.enabled:
                await self._start_monitoring(service_name)

            logger.info(f"Health check registrado para: {service_name}")

    async def unregister_check(self, service_name: str):

        async with self._lock:
            if service_name in self._check_tasks:
                self._check_tasks[service_name].cancel()
                del self._check_tasks[service_name]

            self._configs.pop(service_name, None)
            self._check_functions.pop(service_name, None)
            self._results.pop(service_name, None)
            self._consecutive_failures.pop(service_name, None)
            self._consecutive_successes.pop(service_name, None)

            logger.info(f"Health check eliminado para: {service_name}")

    async def _start_monitoring(self, service_name: str):

        if service_name in self._check_tasks:
            return

        task = asyncio.create_task(self._monitor_service(service_name))
        self._check_tasks[service_name] = task

        logger.info(f"Monitoreo iniciado para: {service_name}")

    async def _monitor_service(self, service_name: str):

        config = self._configs[service_name]
        check_function = self._check_functions[service_name]

        while True:
            try:

                await asyncio.sleep(config.check_interval)

                start_time = time.time()

                try:
                    result = await asyncio.wait_for(
                        check_function(),
                        timeout=config.timeout
                    )
                    result.response_time = time.time() - start_time

                except asyncio.TimeoutError:
                    result = HealthCheckResult(
                        status=HealthStatus.UNHEALTHY,
                        response_time=config.timeout,
                        message=f"Health check timeout ({config.timeout}s)"
                    )

                except Exception as e:
                    result = HealthCheckResult(
                        status=HealthStatus.UNHEALTHY,
                        response_time=time.time() - start_time,
                        message=f"Health check error: {str(e)}"
                    )
                    logger.error(
                        f"Error en health check de {service_name}: {e}",
                        exc_info=True
                    )

                await self._update_result(service_name, result)

            except asyncio.CancelledError:
                logger.info(f"Monitoreo detenido para: {service_name}")
                break

            except Exception as e:
                logger.error(
                    f"Error en monitor de {service_name}: {e}",
                    exc_info=True
                )

    async def _update_result(
            self,
            service_name: str,
            result: HealthCheckResult
    ):

        async with self._lock:
            config = self._configs[service_name]

            if result.status == HealthStatus.HEALTHY:
                self._consecutive_successes[service_name] += 1
                self._consecutive_failures[service_name] = 0
            else:
                self._consecutive_failures[service_name] += 1
                self._consecutive_successes[service_name] = 0

            failures = self._consecutive_failures[service_name]
            successes = self._consecutive_successes[service_name]

            if failures >= config.failure_threshold:
                final_status = HealthStatus.UNHEALTHY
                logger.warning(
                    f"Servicio {service_name} marcado como UNHEALTHY "
                    f"({failures} fallos consecutivos)"
                )
            elif successes >= config.success_threshold:
                final_status = HealthStatus.HEALTHY
            else:

                final_status = result.status

            final_result = HealthCheckResult(
                status=final_status,
                timestamp=result.timestamp,
                response_time=result.response_time,
                message=result.message,
                details={
                    **result.details,
                    "consecutive_failures": failures,
                    "consecutive_successes": successes
                }
            )

            self._results[service_name] = final_result

            logger.debug(
                f"Health check actualizado: {service_name} -> {final_status.value}"
            )

    async def check_now(self, service_name: str) -> Optional[HealthCheckResult]:

        if service_name not in self._check_functions:
            return None

        check_function = self._check_functions[service_name]
        config = self._configs[service_name]

        start_time = time.time()

        try:
            result = await asyncio.wait_for(
                check_function(),
                timeout=config.timeout
            )
            result.response_time = time.time() - start_time

            await self._update_result(service_name, result)
            return result

        except Exception as e:
            result = HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                response_time=time.time() - start_time,
                message=f"Health check error: {str(e)}"
            )

            await self._update_result(service_name, result)
            return result

    async def get_status(self, service_name: str) -> Optional[HealthCheckResult]:

        async with self._lock:
            return self._results.get(service_name)

    async def get_all_statuses(self) -> Dict[str, HealthCheckResult]:

        async with self._lock:
            return dict(self._results)

    async def is_healthy(self, service_name: str) -> bool:

        result = await self.get_status(service_name)
        return result and result.status == HealthStatus.HEALTHY

    async def get_healthy_services(self) -> list[str]:

        async with self._lock:
            return [
                service_name
                for service_name, result in self._results.items()
                if result.status == HealthStatus.HEALTHY
            ]

    async def get_stats(self) -> dict:

        async with self._lock:
            total_services = len(self._configs)
            healthy = sum(
                1 for r in self._results.values()
                if r.status == HealthStatus.HEALTHY
            )
            unhealthy = sum(
                1 for r in self._results.values()
                if r.status == HealthStatus.UNHEALTHY
            )
            degraded = sum(
                1 for r in self._results.values()
                if r.status == HealthStatus.DEGRADED
            )

            return {
                "total_services": total_services,
                "healthy": healthy,
                "unhealthy": unhealthy,
                "degraded": degraded,
                "monitoring_tasks": len(self._check_tasks)
            }


_health_checker_instance: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    global _health_checker_instance
    if _health_checker_instance is None:
        _health_checker_instance = HealthChecker()
    return _health_checker_instance


async def create_simple_health_check(
        check_function: Callable[[], Awaitable[bool]],
        service_name: str
) -> Callable[[], Awaitable[HealthCheckResult]]:
    async def health_check() -> HealthCheckResult:
        try:
            is_healthy = await check_function()
            return HealthCheckResult(
                status=HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY,
                message=f"{service_name} is {'healthy' if is_healthy else 'unhealthy'}"
            )
        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=str(e)
            )

    return health_check

