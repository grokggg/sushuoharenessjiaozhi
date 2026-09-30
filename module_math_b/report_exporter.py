"""
module_math_b.report_exporter — 标准化数学任务 Markdown 报告导出器

从哈希快照链导出标准化数学任务 Markdown 报告。
包含：命题状态、推导链、收敛判定、哈希链完整性、插件执行结果。

v1.1 增量增强，不修改任何 v1.0 核心源码。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from module_math_b.math_snapshot_bridge import MathSnapshotBridge
from module_math_b.math_structs import MathProofSnapshot
from module_math_b.plugins.plugin_registry import PluginResult, PluginStatus


# =============================================================================
# 报告配置
# =============================================================================

@dataclass
class ReportConfig:
    """报告导出配置"""
    include_hash_chain: bool = True
    include_derivation_steps: bool = True
    include_validation_reports: bool = True
    include_plugin_results: bool = True
    include_counter_examples: bool = True
    max_steps_per_proposition: int = 50
    max_counter_examples: int = 20
    language: str = "zh"  # zh | en


# =============================================================================
# 报告导出器
# =============================================================================

class ReportExporter:
    """
    标准化数学任务 Markdown 报告导出器

    从 MathSnapshotBridge 哈希快照链提取数据，
    生成结构化 Markdown 报告，包含：
      - 任务概览
      - 命题状态演变
      - 推导链详情
      - 反例记录
      - 校验报告摘要
      - 收敛判定
      - 哈希链完整性
      - 插件执行结果
    """

    __slots__ = ("_bridge", "_config", "_plugin_results")

    def __init__(
        self,
        bridge: MathSnapshotBridge,
        config: ReportConfig | None = None,
        plugin_results: dict[str, PluginResult] | None = None,
    ) -> None:
        self._bridge = bridge
        self._config = config or ReportConfig()
        self._plugin_results = plugin_results or {}

    # =========================================================================
    # 主入口
    # =========================================================================

    def export_to_markdown(self) -> str:
        """
        导出完整 Markdown 报告

        Returns:
            完整的 Markdown 字符串
        """
        lines: list[str] = []
        snapshots = self._bridge.get_all_snapshots()

        if not snapshots:
            return self._empty_report()

        latest = snapshots[-1]
        self._append_header(lines, latest)
        self._append_task_overview(lines, snapshots)
        self._append_propositions(lines, snapshots)
        self._append_counter_examples(lines, snapshots)
        self._append_convergence(lines, latest)
        self._append_validation_summary(lines, latest)
        if self._config.include_hash_chain:
            self._append_hash_chain(lines, snapshots)
        if self._config.include_plugin_results and self._plugin_results:
            self._append_plugin_results(lines)
        self._append_footer(lines, snapshots)

        return "\n".join(lines)

    def export_to_file(self, filepath: str) -> str:
        """
        导出 Markdown 报告到文件

        Args:
            filepath: 目标文件路径

        Returns:
            文件路径
        """
        markdown = self.export_to_markdown()
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown)
        return filepath

    def export_to_json(self) -> dict[str, Any]:
        """
        导出 JSON 结构化报告（用于程序化消费）

        Returns:
            结构化 JSON 字典
        """
        snapshots = self._bridge.get_all_snapshots()
        if not snapshots:
            return {"error": "无快照数据", "generated_at": datetime.now(timezone.utc).isoformat()}

        latest = snapshots[-1]

        # 命题汇总
        all_props: dict[str, Any] = {}
        for snap in snapshots:
            for prop in snap.propositions:
                pid = prop["proposition_id"]
                if pid not in all_props:
                    all_props[pid] = prop

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_version": "1.1.0",
            "task_id": self._bridge._task_id,
            "total_rounds": len(snapshots),
            "chain_verified": self._bridge.verify_chain_integrity(),
            "final_convergence": latest.convergence_report,
            "propositions": [
                {
                    "proposition_id": pid,
                    "statement": prop.get("statement", ""),
                    "status": prop.get("status", "PENDING"),
                    "domain": prop.get("domain", "number_theory"),
                    "derivation_step_count": prop.get("derivation_step_count", 0),
                    "counter_example_count": prop.get("counter_example_count", 0),
                    "gap_count": prop.get("gap_count", 0),
                }
                for pid, prop in all_props.items()
            ],
            "snapshots": [
                {
                    "snapshot_id": s.snapshot_id,
                    "round_number": s.round_number,
                    "timestamp": s.timestamp,
                    "content_hash": s.content_hash,
                    "convergence_report": s.convergence_report,
                }
                for s in snapshots
            ],
            "plugin_results": {
                name: {
                    "plugin_name": r.plugin_name,
                    "status": r.status.value,
                    "error": r.error,
                    "elapsed_ms": r.elapsed_ms,
                }
                for name, r in self._plugin_results.items()
            } if self._plugin_results else {},
        }

    # =========================================================================
    # 报告段落
    # =========================================================================

    def _empty_report(self) -> str:
        return """# Module-MathB 数学任务报告

> **状态**: 无快照数据

该任务尚未生成任何快照数据，无法导出报告。
"""

    def _append_header(self, lines: list[str], latest: MathProofSnapshot) -> None:
        lines.append("# Module-MathB 数学任务报告")
        lines.append("")
        lines.append(f"> **生成时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"> **报告版本**: v1.1.0")
        lines.append(f"> **快照数量**: {len(self._bridge.get_all_snapshots())}")
        lines.append(f"> **哈希链完整**: {'✅ 通过' if self._bridge.verify_chain_integrity() else '❌ 异常'}")
        lines.append("")
        lines.append("---")
        lines.append("")

    def _append_task_overview(self, lines: list[str], snapshots: list[MathProofSnapshot]) -> None:
        latest = snapshots[-1]

        lines.append("## 1. 任务概览")
        lines.append("")
        lines.append(f"| 属性 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 任务ID | `{latest.task_id}` |")
        lines.append(f"| 总迭代轮次 | {len(snapshots)} |")
        lines.append(f"| 最终收敛类型 | `{latest.convergence_report.get('convergence_type', '未收敛')}` |")
        lines.append(f"| 收敛原因 | {latest.convergence_report.get('convergence_reason', '无')} |")
        lines.append(f"| 开始时间 | {snapshots[0].timestamp} |")
        lines.append(f"| 结束时间 | {latest.timestamp} |")
        lines.append(f"| 扩展标识 | `{latest.extension_tag}` |")
        lines.append("")

    def _append_propositions(self, lines: list[str], snapshots: list[MathProofSnapshot]) -> None:
        latest = snapshots[-1]
        propositions = latest.propositions

        if not propositions:
            lines.append("## 2. 命题记录")
            lines.append("")
            lines.append("*无命题记录*")
            lines.append("")
            return

        lines.append("## 2. 命题记录")
        lines.append("")

        status_emoji = {
            "PENDING": "⏳",
            "PROVEN": "✅",
            "DISPROVEN": "❌",
            "INCONCLUSIVE": "❓",
        }

        for prop in propositions:
            emoji = status_emoji.get(prop.get("status", "PENDING"), "❓")
            lines.append(f"### 2.{propositions.index(prop) + 1} {emoji} 命题 `{prop['proposition_id']}`")
            lines.append("")
            lines.append(f"**陈述**: {prop.get('statement', '无')}")
            lines.append("")
            lines.append(f"| 属性 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| 状态 | `{prop.get('status', 'PENDING')}` |")
            lines.append(f"| 领域 | `{prop.get('domain', 'number_theory')}` |")
            lines.append(f"| 难度 | `{prop.get('difficulty', 'intermediate')}` |")
            lines.append(f"| 迭代深度 | {prop.get('iteration_depth', 0)} |")
            lines.append(f"| 推导步骤数 | {prop.get('derivation_step_count', 0)} |")
            lines.append(f"| 反例数 | {prop.get('counter_example_count', 0)} |")
            lines.append(f"| 缺口数 | {prop.get('gap_count', 0)} |")
            lines.append(f"| 证明者 | {prop.get('proven_by', '无')} |")
            lines.append("")

            # 推导步骤详情
            if self._config.include_derivation_steps:
                self._append_derivation_steps(lines, prop, snapshots)

    def _append_derivation_steps(
        self, lines: list[str], prop: dict[str, Any], snapshots: list[MathProofSnapshot],
    ) -> None:
        """附加推导步骤详情"""
        # 从 proof_chain 中提取该命题的步骤
        steps: list[dict[str, Any]] = []
        for snap in snapshots:
            for step in snap.proof_chain:
                if step.get("proposition_id") == prop["proposition_id"]:
                    if not any(s["step_id"] == step["step_id"] for s in steps):
                        steps.append(step)

        if not steps:
            lines.append("#### 推导步骤: *无推导记录*")
            lines.append("")
            return

        max_steps = self._config.max_steps_per_proposition
        shown = steps[:max_steps]
        truncated = len(steps) - len(shown) if len(steps) > max_steps else 0

        lines.append(f"#### 推导步骤 ({len(shown)} 步{'，已截断' if truncated > 0 else ''})")
        lines.append("")
        lines.append("| 步骤 | 前提 | 结论 | 规则 | 缺口 | 循环 | 校验 |")
        lines.append("|------|------|------|------|------|------|------|")

        for step in shown:
            premises = ", ".join(step.get("premises", [])[:3])
            if len(step.get("premises", [])) > 3:
                premises += "..."

            gap = "⚠️" if step.get("has_gap") else "✅"
            circular = "⚠️" if step.get("is_circular") else "✅"
            validated = "✅" if step.get("validation_passed") else "❌"

            lines.append(
                f"| {step.get('step_number', '?')} "
                f"| {premises[:60]} "
                f"| {step.get('conclusion', '')[:60]} "
                f"| {step.get('derivation_rule', '')[:30]} "
                f"| {gap} "
                f"| {circular} "
                f"| {validated} |"
            )

        if truncated > 0:
            lines.append(f"| ... | ... | ... | ... | ... | ... | ... |")
            lines.append(f"| *还有 {truncated} 步未显示* |")

        lines.append("")

    def _append_counter_examples(
        self, lines: list[str], snapshots: list[MathProofSnapshot],
    ) -> None:
        """附加反例记录"""
        if not self._config.include_counter_examples:
            return

        # 收集所有反例
        all_ces: dict[str, dict[str, Any]] = {}
        for snap in snapshots:
            for prop in snap.propositions:
                for ce in prop.get("counter_examples", []):
                    ce_id = ce.get("example_id", "")
                    if ce_id and ce_id not in all_ces:
                        all_ces[ce_id] = ce

        if not all_ces:
            return

        shown = list(all_ces.values())[:self._config.max_counter_examples]

        lines.append("## 3. 反例记录")
        lines.append("")

        for ce in shown:
            lines.append(f"### 反例 `{ce.get('example_id', '?')}`")
            lines.append("")
            lines.append(f"| 属性 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| 目标命题 | `{ce.get('target_proposition_id', '?')}` |")
            lines.append(f"| 值表示 | `{ce.get('value_representation', '无')}` |")
            lines.append(f"| 有效 | {'✅' if ce.get('is_valid') else '❌'} |")
            lines.append(f"| 可复现 | {'✅' if ce.get('is_reproducible') else '❌'} |")
            lines.append(f"| 定义域检查 | {ce.get('domain_check', '无')} |")
            lines.append("")

    def _append_convergence(self, lines: list[str], latest: MathProofSnapshot) -> None:
        conv = latest.convergence_report
        if not conv:
            lines.append("## 4. 收敛判定")
            lines.append("")
            lines.append("*无收敛报告*")
            lines.append("")
            return

        lines.append("## 4. 收敛判定")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 是否收敛 | {'✅ 是' if conv.get('is_converged') else '❌ 否'} |")
        lines.append(f"| 收敛类型 | `{conv.get('convergence_type', '')}` |")
        lines.append(f"| 收敛原因 | {conv.get('convergence_reason', '无')} |")
        lines.append(f"| 证明完整度 | {conv.get('proof_completeness', 0):.2%} |")
        lines.append(f"| 证明缺口数 | {conv.get('proof_gap_count', 0)} |")
        lines.append(f"| 循环论证数 | {conv.get('proof_circular_count', 0)} |")
        lines.append(f"| 隐性假设数 | {conv.get('proof_hidden_assumption_count', 0)} |")
        lines.append(f"| 反例有效 | {'✅' if conv.get('counter_example_valid') else '❌'} |")
        lines.append(f"| 反例数 | {conv.get('counter_example_count', 0)} |")
        lines.append(f"| 停滞轮数 | {conv.get('stagnation_rounds', 0)} |")
        lines.append(f"| 熵降为零 | {'⚠️ 是' if conv.get('entropy_zero') else '否'} |")
        lines.append("")

    def _append_validation_summary(self, lines: list[str], latest: MathProofSnapshot) -> None:
        vs = latest.validation_summary
        if not vs or not self._config.include_validation_reports:
            return

        lines.append("## 5. 校验报告摘要")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 总校验次数 | {vs.get('total_validations', 0)} |")
        lines.append(f"| 通过率 | {vs.get('pass_rate', 0):.1%} |")
        lines.append(f"| 语法错误数 | {vs.get('syntax_errors', 0)} |")
        lines.append(f"| 逻辑缺口数 | {vs.get('logical_gaps', 0)} |")
        lines.append(f"| 隐性假设数 | {vs.get('hidden_assumptions', 0)} |")
        lines.append(f"| 循环论证数 | {vs.get('circular_count', 0)} |")
        lines.append(f"| 自相矛盾 | {vs.get('self_contradiction_count', 0)} |")
        lines.append(f"| 边界测试通过 | {vs.get('boundary_tests_passed', 0)} |")
        lines.append("")

    def _append_hash_chain(self, lines: list[str], snapshots: list[MathProofSnapshot]) -> None:
        lines.append("## 6. 哈希链完整性")
        lines.append("")
        lines.append(f"**链状态**: {'✅ 完整' if self._bridge.verify_chain_integrity() else '❌ 异常'}")
        lines.append("")
        lines.append("| 轮次 | 快照ID | 内容哈希 | 前驱哈希 | 时间戳 |")
        lines.append("|------|--------|----------|----------|--------|")

        for snap in snapshots:
            lines.append(
                f"| {snap.round_number} "
                f"| `{snap.snapshot_id}` "
                f"| `{snap.content_hash[:16]}...` "
                f"| `{snap.prev_snapshot_hash[:16] if snap.prev_snapshot_hash else '—'}...` "
                f"| {snap.timestamp[:19]} |"
            )
        lines.append("")

        # 哈希链验证详情
        if len(snapshots) >= 2:
            lines.append("### 链验证详情")
            lines.append("")
            for i in range(1, len(snapshots)):
                prev_hash = snapshots[i - 1].content_hash
                curr_prev = snapshots[i].prev_snapshot_hash
                match = "✅" if prev_hash == curr_prev else "❌"
                lines.append(f"- {match} 轮次 {snapshots[i-1].round_number} → 轮次 {snapshots[i].round_number}: "
                           f"`{prev_hash[:16]}...` → `{curr_prev[:16]}...`")
            lines.append("")

    def _append_plugin_results(self, lines: list[str]) -> None:
        lines.append("## 7. 插件执行结果")
        lines.append("")

        status_map = {
            PluginStatus.DISABLED: "⚪ 禁用",
            PluginStatus.ENABLED: "🟢 成功",
            PluginStatus.TIMEOUT: "🟡 超时",
            PluginStatus.ERROR: "🔴 错误",
            PluginStatus.LOADING: "🔵 加载中",
        }

        lines.append("| 插件 | 状态 | 耗时(ms) | 错误信息 |")
        lines.append("|------|------|----------|----------|")

        for name, result in sorted(self._plugin_results.items()):
            status_label = status_map.get(result.status, "未知")
            lines.append(
                f"| `{name}` "
                f"| {status_label} "
                f"| {result.elapsed_ms:.1f} "
                f"| {result.error[:80] if result.error else '—'} |"
            )
        lines.append("")

        # 详细输出
        for name, result in sorted(self._plugin_results.items()):
            if result.status == PluginStatus.ENABLED and result.output:
                lines.append(f"### {name} 输出")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(result.output, ensure_ascii=False, indent=2, default=str))
                lines.append("```")
                lines.append("")

    def _append_footer(self, lines: list[str], snapshots: list[MathProofSnapshot]) -> None:
        lines.append("---")
        lines.append("")
        lines.append(f"*报告由 Module-MathB v1.1 ReportExporter 自动生成*")
        lines.append(f"*哈希链快照数: {len(snapshots)} | 完整性: "
                    f"{'通过' if self._bridge.verify_chain_integrity() else '异常'}*")
        lines.append("")

    # =========================================================================
    # 便捷方法
    # =========================================================================

    @staticmethod
    def from_workflow_result(
        workflow_result: dict[str, Any],
        plugin_results: dict[str, PluginResult] | None = None,
    ) -> str:
        """
        从工作流结果字典直接导出 Markdown 报告

        用于快速生成报告，无需完整的 MathSnapshotBridge 实例。

        Args:
            workflow_result: math_router 输出的结果字典
            plugin_results: 插件执行结果

        Returns:
            Markdown 字符串
        """
        lines: list[str] = []
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        lines.append("# Module-MathB 数学任务报告")
        lines.append("")
        lines.append(f"> **生成时间**: {now}")
        lines.append(f"> **报告版本**: v1.1.0")
        lines.append("")
        lines.append("---")
        lines.append("")

        lines.append("## 1. 任务概览")
        lines.append("")
        lines.append(f"| 属性 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 任务ID | `{workflow_result.get('task_id', '?')}` |")
        lines.append(f"| 总迭代轮次 | {workflow_result.get('total_rounds', 0)} |")
        lines.append(f"| 最终状态 | `{workflow_result.get('final_status', '?')}` |")
        lines.append(f"| 错误信息 | {workflow_result.get('error', '无')} |")
        lines.append("")

        # 命题
        propositions = workflow_result.get("propositions", [])
        if propositions:
            lines.append("## 2. 命题记录")
            lines.append("")
            for prop in propositions:
                status = prop.get("status", "PENDING")
                lines.append(f"### 命题 `{prop.get('proposition_id', '?')}`")
                lines.append("")
                lines.append(f"**陈述**: {prop.get('statement', '无')}")
                lines.append("")
                lines.append(f"| 状态 | 领域 | 推导步骤 | 反例 | 缺口 |")
                lines.append(f"|------|------|----------|------|------|")
                lines.append(
                    f"| `{status}` "
                    f"| `{prop.get('domain', '?')}` "
                    f"| {prop.get('derivation_step_count', 0)} "
                    f"| {prop.get('counter_example_count', 0)} "
                    f"| {prop.get('gap_count', 0)} |"
                )
                lines.append("")

        # 收敛
        conv = workflow_result.get("convergence_report", {})
        if conv:
            lines.append("## 3. 收敛判定")
            lines.append("")
            lines.append(f"| 指标 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| 是否收敛 | {'✅' if conv.get('is_converged') else '❌'} |")
            lines.append(f"| 收敛类型 | `{conv.get('convergence_type', '')}` |")
            lines.append(f"| 收敛原因 | {conv.get('convergence_reason', '无')} |")
            lines.append("")

        # 插件结果
        if plugin_results:
            lines.append("## 4. 插件执行结果")
            lines.append("")
            lines.append("| 插件 | 状态 | 耗时(ms) |")
            lines.append("|------|------|----------|")
            for name, result in sorted(plugin_results.items()):
                lines.append(f"| `{name}` | {result.status.value} | {result.elapsed_ms:.1f} |")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(f"*报告由 Module-MathB v1.1 ReportExporter 自动生成*")
        lines.append("")

        return "\n".join(lines)


# =============================================================================
# 模块导出
# =============================================================================

__all__ = [
    "ReportExporter",
    "ReportConfig",
]