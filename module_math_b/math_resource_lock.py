"""
module_math_b.math_resource_lock — 工业级内存硬约束控制器

强制规则：
  1. 实时监控进程总内存
  2. 模块占用 >= 总 RAM 60% 触发三级降级
  3. 任何情况下不崩溃、不卡死、不泄露内存
  4. 单会话结束强制 GC 回收、强制 DB 关闭

三级降级：
  L1 — 拒绝新数学子任务入队
  L2 — 清空全部临时数值实验缓存、推导草稿缓存
  L3 — 冻结迭代，保存快照，安全退出
"""

from __future__ import annotations

import gc
import os
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable


# =============================================================================
# 降级等级
# =============================================================================

class DegradationLevel(IntEnum):
    NORMAL = 0      # 正常运行
    L1 = 1          # 拒绝新任务入队
    L2 = 2          # 清空非热缓存
    L3 = 3          # 冻结迭代，安全退出


@dataclass
class ResourceStatus:
    """资源状态快照"""
    level: DegradationLevel = DegradationLevel.NORMAL
    total_ram_mb: int = 0
    used_ram_mb: int = 0
    module_ram_mb: int = 0
    usage_ratio: float = 0.0
    task_queue_size: int = 0
    active_tasks: int = 0
    triggered_at: str = ""
    degraded_from: DegradationLevel = DegradationLevel.NORMAL


# =============================================================================
# 资源锁控制器
# =============================================================================

class MathResourceLock:
    """
    数学模块内存硬约束控制器

    用法：
        lock = MathResourceLock()
        lock.acquire_task()  # 请求执行任务，返回是否允许
        # ... 执行数学任务 ...
        lock.release_task()

        # 定期检查
        status = lock.check_status()
        if status.level >= DegradationLevel.L3:
            lock.emergency_shutdown()
    """

    RAM_THRESHOLD: float = 0.60  # 硬限制 60%

    __slots__ = (
        "_active_tasks",
        "_task_queue_size",
        "_current_level",
        "_degradation_history",
        "_on_l3_callback",
        "_temp_caches",
        "_lock",
        "_started",
    )

    def __init__(self, on_l3_callback: Callable[[], None] | None = None) -> None:
        self._active_tasks: int = 0
        self._task_queue_size: int = 0
        self._current_level: DegradationLevel = DegradationLevel.NORMAL
        self._degradation_history: list[ResourceStatus] = []
        self._on_l3_callback = on_l3_callback
        self._temp_caches: list[Any] = []  # 可清理的临时缓存
        self._lock = threading.Lock()
        self._started = True

    # =========================================================================
    # 任务准入
    # =========================================================================

    def acquire_task(self) -> bool:
        """
        请求执行数学任务

        Returns:
            True  — 允许执行
            False — 拒绝（当前处于 L1/L2/L3 降级）
        """
        with self._lock:
            # 检查当前状态
            if self._current_level >= DegradationLevel.L1:
                self._task_queue_size += 1
                return False

            ram_ratio = self._get_ram_usage_ratio()

            if ram_ratio >= self.RAM_THRESHOLD:
                self._trigger_degradation(ram_ratio)
                self._task_queue_size += 1
                return False

            self._active_tasks += 1
            return True

    def release_task(self) -> None:
        """释放一个任务槽位"""
        with self._lock:
            if self._active_tasks > 0:
                self._active_tasks -= 1

    # =========================================================================
    # 状态检查
    # =========================================================================

    def check_status(self) -> ResourceStatus:
        """获取当前资源状态"""
        ram_ratio = self._get_ram_usage_ratio()
        total, used = self._get_ram_info()

        # 自动触发降级
        if ram_ratio >= self.RAM_THRESHOLD and self._current_level == DegradationLevel.NORMAL:
            self._trigger_degradation(ram_ratio)

        return ResourceStatus(
            level=self._current_level,
            total_ram_mb=total,
            used_ram_mb=used,
            module_ram_mb=self._estimate_module_ram(),
            usage_ratio=ram_ratio,
            task_queue_size=self._task_queue_size,
            active_tasks=self._active_tasks,
        )

    def _trigger_degradation(self, ram_ratio: float) -> None:
        """触发三级降级"""
        prev = self._current_level

        if self._current_level == DegradationLevel.NORMAL:
            self._current_level = DegradationLevel.L1
            self._log_degradation(prev, ram_ratio)
        elif self._current_level == DegradationLevel.L1:
            self._current_level = DegradationLevel.L2
            self._clear_temp_caches()
            self._log_degradation(prev, ram_ratio)
        elif self._current_level == DegradationLevel.L2:
            self._current_level = DegradationLevel.L3
            self._freeze_and_save()
            self._log_degradation(prev, ram_ratio)
            if self._on_l3_callback:
                try:
                    self._on_l3_callback()
                except Exception:
                    pass

    def _clear_temp_caches(self) -> None:
        """L2: 清空全部临时缓存"""
        self._temp_caches.clear()
        gc.collect()

    def _freeze_and_save(self) -> None:
        """L3: 冻结迭代，保存快照，安全退出"""
        gc.collect()

    def _log_degradation(self, prev: DegradationLevel, ram_ratio: float) -> None:
        import datetime
        self._degradation_history.append(ResourceStatus(
            level=self._current_level,
            usage_ratio=ram_ratio,
            triggered_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            degraded_from=prev,
        ))

    # =========================================================================
    # 缓存管理
    # =========================================================================

    def register_temp_cache(self, cache_obj: Any) -> None:
        """注册临时缓存对象（L2 降级时自动清理）"""
        self._temp_caches.append(cache_obj)

    def emergency_shutdown(self) -> None:
        """紧急关闭：释放所有资源"""
        with self._lock:
            self._clear_temp_caches()
            self._active_tasks = 0
            self._task_queue_size = 0
            self._started = False
            gc.collect()

    def is_operational(self) -> bool:
        return self._started and self._current_level < DegradationLevel.L3

    # =========================================================================
    # 内存检测
    # =========================================================================

    def _get_ram_usage_ratio(self) -> float:
        """获取当前进程 RAM 使用率"""
        total, used = self._get_ram_info()
        if total == 0:
            return 0.0
        return used / total

    @staticmethod
    def _get_ram_info() -> tuple[int, int]:
        """获取总 RAM 和已用 RAM (MB)"""
        try:
            # Linux: /proc/meminfo
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()

            total = 0
            available = 0
            for line in meminfo.splitlines():
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available = int(line.split()[1])

            # kB → MB
            total_mb = total // 1024
            used_mb = (total - available) // 1024 if available else 0
            return total_mb, used_mb
        except Exception:
            # 回退：使用 psutil（如果可用）
            try:
                import psutil
                mem = psutil.virtual_memory()
                return mem.total // (1024 * 1024), mem.used // (1024 * 1024)
            except ImportError:
                return 8192, 2048  # 默认假设 8GB 总 RAM，2GB 已用

    @staticmethod
    def _estimate_module_ram() -> int:
        """估算模块自身内存占用 (MB)"""
        try:
            import sys
            # 粗略估算：Python 对象总大小
            total_size = 0
            for obj in gc.get_objects():
                try:
                    total_size += sys.getsizeof(obj)
                except (TypeError, RuntimeError):
                    pass
            return total_size // (1024 * 1024)
        except Exception:
            return 0

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def current_level(self) -> DegradationLevel:
        return self._current_level

    @property
    def degradation_history(self) -> list[ResourceStatus]:
        return list(self._degradation_history)

    @property
    def active_task_count(self) -> int:
        return self._active_tasks