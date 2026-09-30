"""
module_math_b.plugins.plugin_registry — 插件注册表与配置加载器

所有插件默认关闭，通过任务 JSON 的 mathb_config.plugins 字段显式开启。
每个插件有独立的超时、内存限制、开关控制。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class PluginStatus(Enum):
    DISABLED = "disabled"
    ENABLED = "enabled"
    TIMEOUT = "timeout"
    ERROR = "error"
    LOADING = "loading"


@dataclass
class PluginConfig:
    """单个插件配置"""
    name: str
    enabled: bool = False
    timeout_seconds: float = 5.0
    memory_limit_mb: int = 128
    extra_args: dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginResult:
    """插件执行结果"""
    plugin_name: str
    status: PluginStatus
    output: Any = None
    error: str = ""
    elapsed_ms: float = 0.0
    memory_used_mb: float = 0.0


class PluginBase:
    """
    插件基类

    所有插件必须实现：
      - plugin_name: str
      - execute(context: dict) -> PluginResult
    """

    plugin_name: str = "base"

    def execute(self, context: dict[str, Any]) -> PluginResult:
        raise NotImplementedError

    def validate_config(self, config: PluginConfig) -> bool:
        return True


class PluginRegistry:
    """
    插件注册表

    管理所有插件的注册、配置、执行和生命周期。
    默认全部关闭，通过任务 JSON 显式开启。
    """

    __slots__ = ("_plugins", "_configs", "_results", "_lock")

    def __init__(self) -> None:
        self._plugins: dict[str, PluginBase] = {}
        self._configs: dict[str, PluginConfig] = {}
        self._results: list[PluginResult] = []
        self._lock = threading.Lock()

    # =========================================================================
    # 注册
    # =========================================================================

    def register(self, plugin: PluginBase, config: PluginConfig | None = None) -> None:
        """注册插件"""
        with self._lock:
            self._plugins[plugin.plugin_name] = plugin
            if config is None:
                config = PluginConfig(name=plugin.plugin_name, enabled=False)
            self._configs[plugin.plugin_name] = config

    def unregister(self, plugin_name: str) -> None:
        """注销插件"""
        with self._lock:
            self._plugins.pop(plugin_name, None)
            self._configs.pop(plugin_name, None)

    # =========================================================================
    # 配置
    # =========================================================================

    def load_config(self, task_config: dict[str, Any]) -> None:
        """
        从任务 JSON 加载插件配置

        格式:
          "mathb_config": {
            "plugins": {
              "sympy_bridge": {"enabled": true, "timeout_seconds": 10},
              "lean_repl_bridge": {"enabled": false},
              "stagnation_analyzer": {"enabled": true}
            }
          }
        """
        plugins_cfg = task_config.get("mathb_config", {}).get("plugins", {})
        if not isinstance(plugins_cfg, dict):
            return

        with self._lock:
            for name, cfg in plugins_cfg.items():
                if not isinstance(cfg, dict):
                    continue
                if name in self._configs:
                    self._configs[name].enabled = cfg.get("enabled", False)
                    self._configs[name].timeout_seconds = cfg.get(
                        "timeout_seconds", self._configs[name].timeout_seconds,
                    )
                    self._configs[name].memory_limit_mb = cfg.get(
                        "memory_limit_mb", self._configs[name].memory_limit_mb,
                    )
                    self._configs[name].extra_args = cfg.get("extra_args", {})

    def enable(self, plugin_name: str) -> None:
        """启用插件"""
        with self._lock:
            if plugin_name in self._configs:
                self._configs[plugin_name].enabled = True

    def disable(self, plugin_name: str) -> None:
        """禁用插件"""
        with self._lock:
            if plugin_name in self._configs:
                self._configs[plugin_name].enabled = False

    def is_enabled(self, plugin_name: str) -> bool:
        with self._lock:
            cfg = self._configs.get(plugin_name)
            return cfg.enabled if cfg else False

    # =========================================================================
    # 执行
    # =========================================================================

    def execute_enabled(self, context: dict[str, Any]) -> dict[str, PluginResult]:
        """
        执行所有已启用的插件

        Args:
            context: 执行上下文（包含 proposition、derivation_steps 等）

        Returns:
            {plugin_name: PluginResult}
        """
        import time
        results: dict[str, PluginResult] = {}

        with self._lock:
            enabled = [
                name for name, cfg in self._configs.items()
                if cfg.enabled and name in self._plugins
            ]

        for name in enabled:
            with self._lock:
                plugin = self._plugins.get(name)
                cfg = self._configs.get(name)
                if plugin is None or cfg is None:
                    continue

            # 带超时执行
            result_holder: list[PluginResult] = []

            def _run() -> None:
                try:
                    t0 = time.time()
                    res = plugin.execute(context)
                    res.elapsed_ms = (time.time() - t0) * 1000
                    result_holder.append(res)
                except Exception as e:
                    result_holder.append(PluginResult(
                        plugin_name=name,
                        status=PluginStatus.ERROR,
                        error=str(e),
                    ))

            thread = threading.Thread(target=_run, daemon=True)
            thread.start()
            thread.join(timeout=cfg.timeout_seconds)

            if thread.is_alive():
                result = PluginResult(
                    plugin_name=name,
                    status=PluginStatus.TIMEOUT,
                    error=f"超时 {cfg.timeout_seconds}s",
                )
            elif result_holder:
                result = result_holder[0]
            else:
                result = PluginResult(
                    plugin_name=name,
                    status=PluginStatus.ERROR,
                    error="未知错误",
                )

            results[name] = result
            self._results.append(result)

        return results

    def execute_one(self, plugin_name: str, context: dict[str, Any]) -> PluginResult:
        """执行单个插件（无论是否启用）"""
        with self._lock:
            plugin = self._plugins.get(plugin_name)
            cfg = self._configs.get(plugin_name)
        if plugin is None:
            return PluginResult(plugin_name=plugin_name, status=PluginStatus.ERROR, error="未注册")
        if cfg is None:
            cfg = PluginConfig(name=plugin_name)

        import time
        t0 = time.time()
        try:
            result = plugin.execute(context)
            result.elapsed_ms = (time.time() - t0) * 1000
        except Exception as e:
            result = PluginResult(plugin_name=plugin_name, status=PluginStatus.ERROR, error=str(e))
        return result

    # =========================================================================
    # 查询
    # =========================================================================

    def get_config(self, plugin_name: str) -> PluginConfig | None:
        with self._lock:
            return self._configs.get(plugin_name)

    def list_plugins(self) -> list[str]:
        with self._lock:
            return list(self._plugins.keys())

    def list_enabled(self) -> list[str]:
        with self._lock:
            return [n for n, c in self._configs.items() if c.enabled]

    def get_results(self) -> list[PluginResult]:
        with self._lock:
            return list(self._results)

    def clear_results(self) -> None:
        with self._lock:
            self._results.clear()

    def reset(self) -> None:
        """重置注册表"""
        with self._lock:
            self._plugins.clear()
            self._configs.clear()
            self._results.clear()