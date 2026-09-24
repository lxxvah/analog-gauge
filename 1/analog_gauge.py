#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用模拟仪表盘 —— PySide6 / QPainter
Apple 设计语言 · 真立体 + 真毛玻璃 · 透明镶嵌 · 全局主题跟随

设计理念：
    万能模拟仪表。任何有 min/max 的物理量都能显示 —— 压力、温度、
    转速、湿度、电压、电流、功率、百分比、油量、电池、速度、流量、
    频率、光照、噪声……内置 30+ 常用预设。

    · 背景透明，可"镶嵌"到任意面板（浅色 / 深色 / 渐变 / 图片）之上
    · 表盘颜色自动跟随全局主题 —— 一次 set_theme，所有表盘一起切

安装：
    pip install PySide6

最简用法 —— 三件事搞定：
    from analog_gauge import AnalogGauge, ThemeManager

    # 1) 选预设（单位自动配好）
    # 2) 改量程（可选）
    # 3) 摆到 UI 位置
    g = AnalogGauge(parent, preset="temperature_c", max_value=200)
    layout.addWidget(g)
    g.set_value(65)

    # 主题切换 —— 所有跟随中的表盘一起变
    ThemeManager.instance().set_theme("dark")

预设列表见 GAUGE_PRESETS 字典。
"""
import math
from dataclasses import dataclass, replace, asdict
from typing import List, Optional, Tuple, Union

from PySide6.QtCore import (
    Qt, QPointF, QRectF, QPropertyAnimation, QEasingCurve, Property, Signal,
    QObject,
)
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QRadialGradient, QLinearGradient,
    QPen, QBrush, QFont, QPolygonF, QFontDatabase,
)
from PySide6.QtWidgets import QWidget


# ===========================================================================
# 配置模型
# ===========================================================================
@dataclass
class GaugeZone:
    start: float
    end: float
    color: str


ZoneSpec = Union[GaugeZone, Tuple[float, float, str]]


@dataclass
class GaugeConfig:
    """通用仪表配置"""
    # ---- 量程 & 单位 ----
    min_value: float = 0.0
    max_value: float = 100.0
    unit: str = ""
    title: str = ""

    # ---- 刻度 ----
    major_step: float = 20.0
    minor_step: float = 5.0

    # ---- 主题 & 颜色 ----
    theme: str = "light"
    accent_color: Optional[str] = None
    needle_color: Optional[str] = None

    # ---- 语义区间 ----
    zones: Optional[List[ZoneSpec]] = None

    # ---- 表盘几何 ----
    angle_start: float = -135.0
    angle_range: float = 270.0

    # ---- 显示开关 ----
    show_numbers: bool = True
    show_unit: bool = True
    show_value: bool = True
    show_zones: bool = True
    show_glass: bool = True

    # ---- 数值格式 ----
    decimals: int = 0

    # ---- 透明 & 镶嵌 ----
    transparent: bool = True
    embed_style: str = "inset"     # "inset" / "raised" / "none"


# ===========================================================================
# ★ 全局主题管理器 —— 一次切换，所有表盘跟着变
# ===========================================================================
class GaugeThemeManager(QObject):
    """
    单例主题管理器。

    用法：
        ThemeManager.instance().set_theme("dark")
        ThemeManager.instance().theme_changed.connect(on_change)
    """
    theme_changed = Signal(str)

    _instance: Optional["GaugeThemeManager"] = None

    def __init__(self):
        super().__init__()
        self._theme = "light"

    @classmethod
    def instance(cls) -> "GaugeThemeManager":
        if cls._instance is None:
            cls._instance = GaugeThemeManager()
        return cls._instance

    def theme(self) -> str:
        return self._theme

    def set_theme(self, name: str):
        """切换全局主题。所有 auto_follow 的表盘会自动刷新"""
        if name in ("light", "dark") and name != self._theme:
            self._theme = name
            self.theme_changed.emit(name)


# 便捷全局函数
def set_global_theme(name: str):
    GaugeThemeManager.instance().set_theme(name)


def get_global_theme() -> str:
    return GaugeThemeManager.instance().theme()


# ===========================================================================
# ★ 预设库
# ===========================================================================
GAUGE_PRESETS = {
    # ---------------------- 压力 ----------------------
    "pressure_mmhg": dict(unit="mmHg", title="PRESSURE",
                          min_value=0, max_value=300, major_step=50, minor_step=10),
    "pressure_kpa":  dict(unit="kPa", title="PRESSURE",
                          min_value=0, max_value=500, major_step=100, minor_step=20),
    "pressure_psi":  dict(unit="PSI", title="PRESSURE",
                          min_value=0, max_value=150, major_step=30, minor_step=5),
    "pressure_bar":  dict(unit="bar", title="PRESSURE",
                          min_value=0, max_value=10, major_step=2, minor_step=0.5,
                          decimals=1),
    "pressure_mpa":  dict(unit="MPa", title="PRESSURE",
                          min_value=0, max_value=1.0, major_step=0.2, minor_step=0.05,
                          decimals=2),

    # ---------------------- 温度 ----------------------
    "temperature_c": dict(unit="°C", title="TEMPERATURE",
                          min_value=-20, max_value=120, major_step=20, minor_step=5,
                          accent_color="#FF9500", needle_color="#FF9500",
                          zones=[(-20, 0, "#64D2FF"),
                                 (0, 60, "#34C759"),
                                 (60, 90, "#FFCC00"),
                                 (90, 120, "#FF3B30")]),
    "temperature_f": dict(unit="°F", title="TEMPERATURE",
                          min_value=0, max_value=250, major_step=50, minor_step=10,
                          accent_color="#FF9500", needle_color="#FF9500",
                          zones=[(0, 100, "#64D2FF"),
                                 (100, 160, "#34C759"),
                                 (160, 200, "#FFCC00"),
                                 (200, 250, "#FF3B30")]),
    "temperature_k": dict(unit="K", title="TEMPERATURE",
                          min_value=250, max_value=400, major_step=30, minor_step=10,
                          accent_color="#FF9500", needle_color="#FF9500"),

    # ---------------------- 转速 ----------------------
    "rpm": dict(unit="RPM", title="RPM",
                min_value=0, max_value=8000, major_step=1000, minor_step=200,
                accent_color="#FF9500", needle_color="#FF9500",
                zones=[(0, 5000, "#34C759"),
                       (5000, 6000, "#FFCC00"),
                       (6000, 8000, "#FF3B30")]),
    "rps": dict(unit="RPS", title="RPS",
                min_value=0, max_value=150, major_step=30, minor_step=5,
                accent_color="#FF9500", needle_color="#FF9500"),

    # ---------------------- 湿度 ----------------------
    "humidity": dict(unit="%RH", title="HUMIDITY",
                     min_value=0, max_value=100, major_step=10, minor_step=2,
                     accent_color="#64D2FF", needle_color="#64D2FF",
                     zones=[(0, 30, "#FFCC00"),
                            (30, 70, "#34C759"),
                            (70, 100, "#64D2FF")]),

    # ---------------------- 电压 ----------------------
    "voltage_v":  dict(unit="V", title="VOLTAGE",
                       min_value=0, max_value=30, major_step=5, minor_step=1,
                       accent_color="#FFCC00", needle_color="#FFCC00",
                       decimals=1),
    "voltage_mv": dict(unit="mV", title="VOLTAGE",
                       min_value=0, max_value=1000, major_step=200, minor_step=50,
                       accent_color="#FFCC00", needle_color="#FFCC00"),
    "voltage_kv": dict(unit="kV", title="VOLTAGE",
                       min_value=0, max_value=10, major_step=2, minor_step=0.5,
                       accent_color="#FFCC00", needle_color="#FFCC00",
                       decimals=1),

    # ---------------------- 电流 ----------------------
    "current_a":  dict(unit="A", title="CURRENT",
                       min_value=0, max_value=20, major_step=5, minor_step=1,
                       accent_color="#FFCC00", needle_color="#FFCC00",
                       decimals=1),
    "current_ma": dict(unit="mA", title="CURRENT",
                       min_value=0, max_value=500, major_step=100, minor_step=20,
                       accent_color="#FFCC00", needle_color="#FFCC00"),

    # ---------------------- 功率 ----------------------
    "power_w":  dict(unit="W", title="POWER",
                     min_value=0, max_value=5000, major_step=1000, minor_step=200,
                     accent_color="#FF6B00", needle_color="#FF6B00"),
    "power_kw": dict(unit="kW", title="POWER",
                     min_value=0, max_value=5, major_step=1, minor_step=0.2,
                     accent_color="#FF6B00", needle_color="#FF6B00",
                     decimals=1),

    # ---------------------- 百分比 / 进度 ----------------------
    "percentage": dict(unit="%", title="PERCENT",
                       min_value=0, max_value=100, major_step=10, minor_step=2),
    "progress":   dict(unit="%", title="PROGRESS",
                       min_value=0, max_value=100, major_step=20, minor_step=5,
                       show_zones=False,
                       accent_color="#30D158", needle_color="#30D158"),

    # ---------------------- 油量 / 电池 ----------------------
    "fuel":       dict(unit="%", title="FUEL",
                       min_value=0, max_value=100, major_step=20, minor_step=5,
                       zones=[(0, 15, "#FF3B30"),
                              (15, 30, "#FFCC00"),
                              (30, 100, "#34C759")]),
    "fuel_liter": dict(unit="L", title="FUEL",
                       min_value=0, max_value=60, major_step=10, minor_step=2,
                       zones=[(0, 8, "#FF3B30"),
                              (8, 18, "#FFCC00"),
                              (18, 60, "#34C759")]),
    "battery":    dict(unit="%", title="BATTERY",
                       min_value=0, max_value=100, major_step=20, minor_step=5,
                       zones=[(0, 20, "#FF3B30"),
                              (20, 40, "#FFCC00"),
                              (40, 100, "#34C759")]),

    # ---------------------- 速度 ----------------------
    "speed_kph": dict(unit="km/h", title="SPEED",
                      min_value=0, max_value=240, major_step=40, minor_step=10),
    "speed_mph": dict(unit="mph", title="SPEED",
                      min_value=0, max_value=150, major_step=30, minor_step=5),
    "speed_ms":  dict(unit="m/s", title="SPEED",
                      min_value=0, max_value=50, major_step=10, minor_step=2),

    # ---------------------- 流量 ----------------------
    "flow_lpm": dict(unit="L/min", title="FLOW",
                     min_value=0, max_value=100, major_step=20, minor_step=5,
                     accent_color="#64D2FF", needle_color="#64D2FF"),
    "flow_m3h": dict(unit="m³/h", title="FLOW",
                     min_value=0, max_value=50, major_step=10, minor_step=2,
                     accent_color="#64D2FF", needle_color="#64D2FF"),

    # ---------------------- 频率 ----------------------
    "frequency_hz":  dict(unit="Hz", title="FREQUENCY",
                          min_value=0, max_value=100, major_step=20, minor_step=5),
    "frequency_khz": dict(unit="kHz", title="FREQUENCY",
                          min_value=0, max_value=1000, major_step=200, minor_step=50),

    # ---------------------- 光照 / 噪声 ----------------------
    "lux":      dict(unit="lx", title="LIGHT",
                     min_value=0, max_value=2000, major_step=500, minor_step=100,
                     accent_color="#FFCC00", needle_color="#FFCC00"),
    "noise_db": dict(unit="dB", title="NOISE",
                     min_value=0, max_value=120, major_step=20, minor_step=5),
}


# ===========================================================================
# 通用仪表控件
# ===========================================================================
class AnalogGauge(QWidget):
    """通用模拟仪表 —— Apple 设计语言 · 真立体 + 真毛玻璃 · 透明镶嵌 · 主题跟随"""

    valueChanged = Signal(float)

    # ------------------------------------------------------------------
    # 主题色板 —— 完整两套
    # ------------------------------------------------------------------
    THEMES = {
        "light": {
            "bg":           "#F5F5F7",
            "bezel_hi":     "#FFFFFF",
            "bezel_light":  "#E8E8ED",
            "bezel_dark":   "#C8C8CE",
            "bezel_lo":     "#9A9AA0",
            "face_inner":   "#FBFBFD",
            "face_mid":     "#F2F2F5",
            "face_outer":   "#DEDEE4",
            "tick_minor":   "#8E8E93",
            "tick_major":   "#1D1D1F",
            "number":       "#1D1D1F",
            "label":        "#86868B",
            "value_text":   "#0066CC",
            "needle":       "#FF3B30",
            "needle_hi":    "#FFB0A8",
            "hub_outer":    "#1D1D1F",
            "hub_hi":       "#5A5A5E",
            "hub_inner":    "#FBFBFD",
            "arc_green":    "#34C759",
            "arc_yellow":   "#FFCC00",
            "arc_red":      "#FF3B30",
            "glass_a_hi":   150,
            "glass_a_mid":  45,
            "glass_tint":   12,
        },
        "dark": {
            "bg":           "#1C1C1E",
            "bezel_hi":     "#7A7A80",
            "bezel_light":  "#5A5A5E",
            "bezel_dark":   "#38383A",
            "bezel_lo":     "#242426",
            "face_inner":   "#2E2E30",
            "face_mid":     "#262628",
            "face_outer":   "#1C1C1E",
            "tick_minor":   "#98989D",
            "tick_major":   "#FFFFFF",
            "number":       "#E5E5EA",
            "label":        "#98989D",
            "value_text":   "#2997FF",
            "needle":       "#FF453A",
            "needle_hi":    "#FF8A80",
            "hub_outer":    "#E5E5EA",
            "hub_hi":       "#FFFFFF",
            "hub_inner":    "#2E2E30",
            "arc_green":    "#30D158",
            "arc_yellow":   "#FFD60A",
            "arc_red":      "#FF453A",
            "glass_a_hi":   90,
            "glass_a_mid":  30,
            "glass_tint":   8,
        },
    }

    # ==================================================================
    # 构造
    # ==================================================================
    def __init__(
        self,
        parent=None,
        width: int = 340,
        height: int = 340,
        preset: Optional[str] = None,
        config: Optional[GaugeConfig] = None,
        auto_follow_theme: bool = True,      # ★ 是否自动跟随全局主题
        **kwargs,
    ):
        super().__init__(parent)
        self.setFixedSize(width, height)

        # ---- 是否跟随全局主题 ----
        self._auto_follow_theme = auto_follow_theme

        # ---- 决定初始主题 ----
        if auto_follow_theme:
            # 跟随全局主题：用户显式传的 theme 会被忽略
            kwargs.pop("theme", None)
            theme_name = GaugeThemeManager.instance().theme()
        else:
            theme_name = kwargs.get("theme", "light")

        # ---- 装配配置 ----
        if config is None:
            base = {}
            if preset:
                if preset not in GAUGE_PRESETS:
                    raise ValueError(
                        f"未知预设 '{preset}'。可用：\n  "
                        + ", ".join(sorted(GAUGE_PRESETS.keys()))
                    )
                base.update(GAUGE_PRESETS[preset])
            base.update(kwargs)
            base["theme"] = theme_name
            config = GaugeConfig(**base)
        else:
            config = replace(config, theme=theme_name)
            if kwargs:
                config = replace(config, **kwargs)
        self._config = config

        self._value = config.min_value
        self._display_value = config.min_value
        self._theme_name = theme_name
        self._theme = self._resolve_theme()

        # ---- 透明背景 ----
        if config.transparent:
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WA_NoSystemBackground, True)
            self.setAutoFillBackground(False)

        # ---- 指针动画 ----
        self._anim = QPropertyAnimation(self, b"displayValue")
        self._anim.setDuration(600)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        # ---- 订阅全局主题 ----
        if auto_follow_theme:
            GaugeThemeManager.instance().theme_changed.connect(self._on_global_theme)

        self._setup_fonts()

    @classmethod
    def from_config(cls, parent, config: GaugeConfig,
                    width: int = 340, height: int = 340,
                    auto_follow_theme: bool = True) -> "AnalogGauge":
        return cls(parent, width, height, config=config,
                   auto_follow_theme=auto_follow_theme)

    # ------------------------------------------------------------------
    # 全局主题响应
    # ------------------------------------------------------------------
    def _on_global_theme(self, theme_name: str):
        """全局主题变化 —— 自动刷新（前提：仍在跟随）"""
        if not self._auto_follow_theme:
            return
        self._theme_name = theme_name
        self._config = replace(self._config, theme=theme_name)
        self._theme = self._resolve_theme()
        self.update()

    def follow_theme(self, follow: bool = True):
        """开启 / 关闭全局主题跟随"""
        if follow and not self._auto_follow_theme:
            try:
                GaugeThemeManager.instance().theme_changed.connect(self._on_global_theme)
            except Exception:
                pass
            self._auto_follow_theme = True
            self._on_global_theme(GaugeThemeManager.instance().theme())
        elif not follow and self._auto_follow_theme:
            try:
                GaugeThemeManager.instance().theme_changed.disconnect(self._on_global_theme)
            except Exception:
                pass
            self._auto_follow_theme = False

    def is_following_theme(self) -> bool:
        return self._auto_follow_theme

    # ------------------------------------------------------------------
    # 字体
    # ------------------------------------------------------------------
    def _setup_fonts(self):
        families = set(QFontDatabase.families())

        def pick(*candidates):
            for name in candidates:
                if name in families:
                    return name
            return "Helvetica Neue"

        self._display_family = pick("SF Pro Display", "Inter", "Helvetica Neue")
        self._text_family    = pick("SF Pro Text",    "Inter", "Helvetica Neue")

    def _resolve_theme(self) -> dict:
        theme = dict(self.THEMES[self._theme_name])
        if self._config.accent_color:
            theme["value_text"] = self._config.accent_color
        if self._config.needle_color:
            theme["needle"] = self._config.needle_color
            theme["needle_hi"] = QColor(self._config.needle_color).lighter(140).name()
        return theme

    # ------------------------------------------------------------------
    # 动画属性
    # ------------------------------------------------------------------
    def _get_display_value(self) -> float:
        return self._display_value

    def _set_display_value(self, v: float):
        self._display_value = v
        self.update()

    displayValue = Property(float, _get_display_value, _set_display_value)

    # ==================================================================
    # 外部接口
    # ==================================================================
    def set_value(self, v: float, animate: bool = True):
        clamped = max(self._config.min_value, min(self._config.max_value, v))
        self._value = clamped
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._display_value)
            self._anim.setEndValue(clamped)
            self._anim.start()
        else:
            self._display_value = clamped
            self.update()
        self.valueChanged.emit(clamped)

    def get_value(self) -> float:
        return self._value

    def set_theme(self, theme_name: str):
        """
        手动指定该表盘的主题 —— 会停止跟随全局主题。
        想恢复跟随，调用 follow_theme(True)。
        """
        if theme_name in self.THEMES:
            self._auto_follow_theme = False
            self._theme_name = theme_name
            self._config = replace(self._config, theme=theme_name)
            self._theme = self._resolve_theme()
            self.update()

    def theme_name(self) -> str:
        return self._theme_name

    def set_unit(self, unit: str):
        self._config = replace(self._config, unit=unit)
        self.update()

    def set_range(self, min_value: float, max_value: float,
                  major_step: Optional[float] = None,
                  minor_step: Optional[float] = None):
        kwargs = dict(min_value=min_value, max_value=max_value)
        if major_step is not None:
            kwargs["major_step"] = major_step
        if minor_step is not None:
            kwargs["minor_step"] = minor_step
        self._config = replace(self._config, **kwargs)
        self._value = max(min_value, min(max_value, self._value))
        self._display_value = self._value
        self.update()

    def set_config(self, config: GaugeConfig):
        self._config = config
        self._theme_name = config.theme
        self._theme = self._resolve_theme()
        if config.transparent:
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._value = max(config.min_value, min(config.max_value, self._value))
        self._display_value = self._value
        self.update()

    def config(self) -> GaugeConfig:
        return self._config

    def config_dict(self) -> dict:
        return asdict(self._config)

    # ---- 属性快捷访问 ----
    @property
    def min_value(self) -> float:
        return self._config.min_value

    @property
    def max_value(self) -> float:
        return self._config.max_value

    @property
    def unit(self) -> str:
        return self._config.unit

    @property
    def title(self) -> str:
        return self._config.title

    # ------------------------------------------------------------------
    # 角度 / 几何
    # ------------------------------------------------------------------
    def _value_to_angle(self, v: float) -> float:
        span = self._config.max_value - self._config.min_value
        ratio = 0.0 if span == 0 else (v - self._config.min_value) / span
        ratio = max(0.0, min(1.0, ratio))
        return self._config.angle_start + ratio * self._config.angle_range

    @staticmethod
    def _polar(cx, cy, r, angle_deg):
        rad = math.radians(angle_deg)
        return cx + r * math.cos(rad), cy + r * math.sin(rad)

    def _format_value(self, v: float) -> str:
        d = self._config.decimals
        if d <= 0:
            return f"{int(round(v))}"
        return f"{v:.{d}f}"

    # ==================================================================
    # 绘制入口
    # ==================================================================
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        t = self._theme
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - max(10, min(w, h) * 0.055)

        if not self._config.transparent:
            p.fillRect(self.rect(), QColor(t["bg"]))

        style = self._config.embed_style
        if style == "inset":
            self._draw_inset_ring(p, cx, cy, R)
        elif style == "raised":
            self._draw_raised_shadow(p, cx, cy, R)

        self._draw_bezel(p, cx, cy, R, t)

        bezel_thickness = max(4, R * 0.04)
        face_R = R - bezel_thickness - 1
        self._draw_face(p, cx, cy, face_R, t)

        arc_r_outer = face_R - R * 0.10
        arc_r_inner = arc_r_outer - max(5, R * 0.045)
        if self._config.show_zones:
            self._draw_zones(p, cx, cy, arc_r_outer, arc_r_inner, t)

        tick_outer       = arc_r_inner - R * 0.045
        tick_major_inner = tick_outer - R * 0.10
        tick_minor_inner = tick_outer - R * 0.058
        self._draw_ticks(p, cx, cy, tick_outer, tick_major_inner, tick_minor_inner, t)

        num_r = tick_major_inner - R * 0.10
        if self._config.show_numbers:
            self._draw_numbers(p, cx, cy, num_r, t)

        if self._config.show_glass:
            self._draw_glass(p, cx, cy, face_R, t)

        if self._config.show_value:
            self._draw_value(p, cx, cy, R, t)

        needle_len = num_r - R * 0.02
        self._draw_needle(p, cx, cy, needle_len, R, t)
        self._draw_hub(p, cx, cy, R, t)

        p.end()

    # ==================================================================
    # 镶嵌环 —— 面板开孔内阴影
    # ==================================================================
    def _draw_inset_ring(self, p, cx, cy, R):
        ring_width = max(6.0, R * 0.06)
        steps = 10
        for i in range(steps):
            ratio = i / (steps - 1)
            alpha = int(95 * (1 - ratio) ** 1.7)
            if alpha <= 0:
                continue
            pen = QPen(QColor(0, 0, 0, alpha))
            pen.setWidthF(ring_width / steps + 0.6)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            r = R + 0.5 + ratio * ring_width
            p.drawEllipse(QPointF(cx, cy), r, r)

        edge = QPen(QColor(0, 0, 0, 70))
        edge.setWidthF(1.0)
        p.setPen(edge)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R - 0.5, R - 0.5)

    # ==================================================================
    # 浮起阴影
    # ==================================================================
    def _draw_raised_shadow(self, p, cx, cy, R):
        g = QRadialGradient(QPointF(cx, cy + R * 0.06), R * 1.20)
        g.setColorAt(0.00, QColor(0, 0, 0, 70))
        g.setColorAt(0.80, QColor(0, 0, 0, 40))
        g.setColorAt(0.94, QColor(0, 0, 0, 10))
        g.setColorAt(1.00, QColor(0, 0, 0, 0))

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy + R * 0.06), R * 1.20, R * 1.20)

    # ==================================================================
    # 金属外圈
    # ==================================================================
    def _draw_bezel(self, p, cx, cy, R, t):
        g = QRadialGradient(QPointF(cx - R * 0.38, cy - R * 0.38), R * 1.55)
        g.setColorAt(0.00, QColor(t["bezel_hi"]))
        g.setColorAt(0.35, QColor(t["bezel_light"]))
        g.setColorAt(0.72, QColor(t["bezel_dark"]))
        g.setColorAt(1.00, QColor(t["bezel_lo"]))

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), R, R)

    # ==================================================================
    # 表盘
    # ==================================================================
    def _draw_face(self, p, cx, cy, R, t):
        g = QRadialGradient(QPointF(cx, cy), R)
        g.setColorAt(0.00, QColor(t["face_inner"]))
        g.setColorAt(0.72, QColor(t["face_mid"]))
        g.setColorAt(1.00, QColor(t["face_outer"]))

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), R, R)

    # ==================================================================
    # 语义弧带
    # ==================================================================
    def _draw_zones(self, p, cx, cy, r_out, r_in, t):
        zones = self._resolve_zones(t)
        if not zones:
            return
        p.setPen(Qt.NoPen)
        for spec in zones:
            if isinstance(spec, GaugeZone):
                v0, v1, color = spec.start, spec.end, spec.color
            else:
                v0, v1, color = spec
            self._draw_arc_band(
                p, cx, cy, r_out, r_in,
                self._value_to_angle(v0), self._value_to_angle(v1), color,
            )

    def _resolve_zones(self, t) -> List[ZoneSpec]:
        cfg = self._config
        if cfg.zones is not None:
            return list(cfg.zones)
        span = cfg.max_value - cfg.min_value
        return [
            (cfg.min_value,               cfg.min_value + span * 0.60, t["arc_green"]),
            (cfg.min_value + span * 0.60, cfg.min_value + span * 0.80, t["arc_yellow"]),
            (cfg.min_value + span * 0.80, cfg.max_value,                t["arc_red"]),
        ]

    def _draw_arc_band(self, p, cx, cy, r_out, r_in, a0, a1, color):
        steps = max(2, int(abs(a1 - a0) / 2))
        pts_out, pts_in = [], []
        for i in range(steps + 1):
            x, y = self._polar(cx, cy, r_out, a0 + (a1 - a0) * i / steps)
            pts_out.append(QPointF(x, y))
        for i in range(steps, -1, -1):
            x, y = self._polar(cx, cy, r_in, a0 + (a1 - a0) * i / steps)
            pts_in.append(QPointF(x, y))

        path = QPainterPath()
        path.moveTo(pts_out[0])
        for pt in pts_out[1:]:
            path.lineTo(pt)
        for pt in pts_in:
            path.lineTo(pt)
        path.closeSubpath()

        p.setBrush(QBrush(QColor(color)))
        p.drawPath(path)

    # ==================================================================
    # 刻度
    # ==================================================================
    def _draw_ticks(self, p, cx, cy, outer, major_in, minor_in, t):
        cfg = self._config
        if cfg.minor_step <= 0:
            return
        v = cfg.min_value
        while v <= cfg.max_value + 1e-6:
            is_major = abs((v / cfg.major_step) - round(v / cfg.major_step)) < 0.01
            angle = self._value_to_angle(v)
            if is_major:
                r_in, width, color = major_in, 2.0, t["tick_major"]
            else:
                r_in, width, color = minor_in, 1.0, t["tick_minor"]

            x1, y1 = self._polar(cx, cy, outer, angle)
            x2, y2 = self._polar(cx, cy, r_in,  angle)

            pen = QPen(QColor(color))
            pen.setWidthF(width)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            v += cfg.minor_step

    # ==================================================================
    # 刻度数字
    # ==================================================================
    def _draw_numbers(self, p, cx, cy, r, t):
        cfg = self._config
        font = QFont(self._display_family)
        font.setPixelSize(max(9, int(r * 0.075)))
        font.setWeight(QFont.Weight.Normal)

        v = cfg.min_value
        while v <= cfg.max_value + 1e-6:
            is_major = abs((v / cfg.major_step) - round(v / cfg.major_step)) < 0.01
            if is_major:
                angle = self._value_to_angle(v)
                nx, ny = self._polar(cx, cy, r, angle)
                p.setPen(QPen(QColor(t["number"])))
                p.setFont(font)
                rect = QRectF(nx - 25, ny - 10, 50, 20)
                p.drawText(rect, Qt.AlignCenter, self._format_value(v))
            v += cfg.major_step

    # ==================================================================
    # 毛玻璃罩
    # ==================================================================
    def _draw_glass(self, p, cx, cy, R, t):
        a_hi  = t["glass_a_hi"]
        a_mid = t["glass_a_mid"]
        tint  = t["glass_tint"]

        if tint > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(255, 255, 255, tint)))
            p.drawEllipse(QPointF(cx, cy), R, R)

        g = QRadialGradient(QPointF(cx - R * 0.08, cy - R * 0.46), R * 0.98)
        g.setColorAt(0.00, QColor(255, 255, 255, a_hi))
        g.setColorAt(0.45, QColor(255, 255, 255, a_mid))
        g.setColorAt(0.75, QColor(255, 255, 255, int(a_mid * 0.35)))
        g.setColorAt(1.00, QColor(255, 255, 255, 0))

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), R, R)

        band = QLinearGradient(
            QPointF(cx - R * 0.9, cy - R * 0.9),
            QPointF(cx + R * 0.3, cy + R * 0.3),
        )
        band.setColorAt(0.00, QColor(255, 255, 255, 0))
        band.setColorAt(0.42, QColor(255, 255, 255, 0))
        band.setColorAt(0.52, QColor(255, 255, 255, int(a_mid * 0.7)))
        band.setColorAt(0.62, QColor(255, 255, 255, 0))
        band.setColorAt(1.00, QColor(255, 255, 255, 0))

        p.setBrush(QBrush(band))
        p.drawEllipse(QPointF(cx, cy), R, R)

        path = QPainterPath()
        rect = QRectF(cx - R * 0.84, cy - R * 0.84, R * 1.68, R * 1.68)
        path.arcMoveTo(rect, 250)
        path.arcTo(rect, 250, 40)

        pen = QPen(QColor(255, 255, 255, int(a_mid * 0.8)))
        pen.setWidthF(max(3.0, R * 0.045))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        pen2 = QPen(QColor(255, 255, 255, int(a_mid * 0.5)))
        pen2.setWidthF(1.0)
        p.setPen(pen2)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R - 1.5, R - 1.5)

    # ==================================================================
    # 当前值 + 单位
    # ==================================================================
    def _draw_value(self, p, cx, cy, R, t):
        val_text = self._format_value(self._display_value)

        f_val = QFont(self._display_family)
        f_val.setPixelSize(max(16, int(R * 0.22)))
        f_val.setWeight(QFont.Weight.Light)
        p.setPen(QPen(QColor(t["value_text"])))
        p.setFont(f_val)
        p.drawText(
            QRectF(cx - R * 0.7, cy + R * 0.06, R * 1.4, R * 0.30),
            Qt.AlignCenter, val_text,
        )

        if self._config.show_unit and self._config.unit:
            f_unit = QFont(self._text_family)
            f_unit.setPixelSize(max(9, int(R * 0.085)))
            f_unit.setWeight(QFont.Weight.Normal)
            p.setPen(QPen(QColor(t["label"])))
            p.setFont(f_unit)
            p.drawText(
                QRectF(cx - R * 0.7, cy + R * 0.34, R * 1.4, R * 0.16),
                Qt.AlignCenter, self._config.unit,
            )

    # ==================================================================
    # 指针
    # ==================================================================
    def _draw_needle(self, p, cx, cy, length, R, t):
        angle = self._value_to_angle(self._display_value)
        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        perp = math.radians(angle + 90)
        cos_p, sin_p = math.cos(perp), math.sin(perp)

        s = R / 150.0
        tail_len = 13 * s
        tail_w   = 3.0 * s
        shoulder = 4.0 * s

        def pt(r, w):
            return QPointF(cx + r * cos_a + w * cos_p,
                           cy + r * sin_a + w * sin_p)

        poly = QPolygonF([
            pt(-tail_len,          0.0),
            pt(-tail_len + 1 * s,  tail_w),
            pt(length * 0.30,      shoulder),
            pt(length,             0.0),
            pt(length * 0.30,     -shoulder),
            pt(-tail_len + 1 * s, -tail_w),
        ])

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(t["needle"])))
        p.drawPolygon(poly)

        pen = QPen(QColor(t["needle_hi"]))
        pen.setWidthF(max(0.8, 1.1 * s))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        hx1, hy1 = self._polar(cx, cy, length * 0.15, angle)
        hx2, hy2 = self._polar(cx, cy, length * 0.75, angle)
        off = 1.4 * s
        p.drawLine(
            QPointF(hx1 + off * cos_p, hy1 + off * sin_p),
            QPointF(hx2 + off * cos_p, hy2 + off * sin_p),
        )

    # ==================================================================
    # 中心轴
    # ==================================================================
    def _draw_hub(self, p, cx, cy, R, t):
        r_hub = max(5.0, R * 0.052)

        g = QRadialGradient(
            QPointF(cx - r_hub * 0.35, cy - r_hub * 0.35),
            r_hub * 1.6,
        )
        g.setColorAt(0.0, QColor(t["hub_hi"]))
        g.setColorAt(0.5, QColor(t["hub_outer"]))
        g.setColorAt(1.0, QColor(t["hub_outer"]).darker(140))

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), r_hub, r_hub)

        p.setBrush(QBrush(QColor(t["hub_inner"])))
        p.drawEllipse(QPointF(cx, cy), r_hub * 0.4, r_hub * 0.4)


# ===========================================================================
# 向后兼容
# ===========================================================================
PressureGauge = AnalogGauge
ThemeManager = GaugeThemeManager     # 便捷别名


# ===========================================================================
# 工厂函数
# ===========================================================================
def create_gauge(parent=None, preset: str = "percentage",
                 width: int = 260, height: int = 260, **kwargs) -> AnalogGauge:
    return AnalogGauge(parent, width, height, preset=preset, **kwargs)


def create_pressure_gauge(parent=None, width: int = 260, height: int = 260,
                          max_value: float = 300.0, unit: str = "mmHg",
                          theme: Optional[str] = None, **kwargs) -> AnalogGauge:
    major = 50 if max_value <= 600 else max_value / 6
    minor = major / 5
    cfg_kwargs = dict(
        min_value=0, max_value=max_value, unit=unit,
        major_step=round(major), minor_step=round(minor, 1),
        title="PRESSURE",
    )
    if theme is not None:
        cfg_kwargs["theme"] = theme
        return AnalogGauge(parent, width, height,
                           auto_follow_theme=False, **cfg_kwargs, **kwargs)
    return AnalogGauge(parent, width, height, **cfg_kwargs, **kwargs)


def create_percentage_gauge(parent=None, width: int = 260, height: int = 260,
                            theme: Optional[str] = None, **kwargs) -> AnalogGauge:
    if theme is not None:
        return AnalogGauge(parent, width, height, preset="percentage",
                           auto_follow_theme=False, theme=theme, **kwargs)
    return AnalogGauge(parent, width, height, preset="percentage", **kwargs)


def create_temperature_gauge(parent=None, width: int = 260, height: int = 260,
                             min_value: float = -20.0, max_value: float = 120.0,
                             unit: str = "°C",
                             theme: Optional[str] = None, **kwargs) -> AnalogGauge:
    cfg_kwargs = dict(
        min_value=min_value, max_value=max_value, unit=unit,
        major_step=20, minor_step=5, title="TEMPERATURE",
        accent_color="#FF9500", needle_color="#FF9500",
        zones=[(min_value, 0.0, "#64D2FF"),
               (0.0, 60.0, "#34C759"),
               (60.0, 90.0, "#FFCC00"),
               (90.0, max_value, "#FF3B30")],
    )
    if theme is not None:
        cfg_kwargs["theme"] = theme
        return AnalogGauge(parent, width, height,
                           auto_follow_theme=False, **cfg_kwargs, **kwargs)
    return AnalogGauge(parent, width, height, **cfg_kwargs, **kwargs)


def create_rpm_gauge(parent=None, width: int = 260, height: int = 260,
                     max_rpm: float = 8000.0,
                     theme: Optional[str] = None, **kwargs) -> AnalogGauge:
    if theme is not None:
        return AnalogGauge(parent, width, height, preset="rpm",
                           max_value=max_rpm, auto_follow_theme=False,
                           theme=theme, **kwargs)
    return AnalogGauge(parent, width, height, preset="rpm",
                       max_value=max_rpm, **kwargs)


# ===========================================================================
# 自测
# ===========================================================================
if __name__ == "__main__":
    import sys
    import random
    from PySide6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
        QPushButton, QComboBox,
    )

    app = QApplication(sys.argv)

    class Showcase(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Universal Analog Gauge — Auto Theme Follow")
            self.resize(1180, 720)
            self.setObjectName("root")

            layout = QVBoxLayout(self)
            layout.setContentsMargins(24, 20, 24, 20)
            layout.setSpacing(16)

            # ---------------- 浅色面板 ----------------
            self.light_panel = QFrame()
            self.light_panel.setObjectName("light_panel")
            light_row = QHBoxLayout(self.light_panel)
            light_row.setContentsMargins(20, 20, 20, 20)
            light_row.setSpacing(16)

            self.light_title = QLabel("LIGHT PANEL")
            self.light_title.setObjectName("panel_title")

            self.g1 = create_gauge(self.light_panel, "pressure_mmhg", 240, 240)
            self.g2 = create_gauge(self.light_panel, "temperature_c", 240, 240)
            self.g3 = create_gauge(self.light_panel, "humidity",      240, 240)

            light_row.addWidget(self.light_title)
            light_row.addStretch()
            light_row.addWidget(self.g1)
            light_row.addWidget(self.g2)
            light_row.addWidget(self.g3)
            light_row.addStretch()
            layout.addWidget(self.light_panel)

            # ---------------- 深色面板 ----------------
            self.dark_panel = QFrame()
            self.dark_panel.setObjectName("dark_panel")
            dark_row = QHBoxLayout(self.dark_panel)
            dark_row.setContentsMargins(20, 20, 20, 20)
            dark_row.setSpacing(16)

            self.dark_title = QLabel("DARK PANEL")
            self.dark_title.setObjectName("panel_title_dark")

            self.g4 = create_gauge(self.dark_panel, "rpm",       240, 240)
            self.g5 = create_gauge(self.dark_panel, "battery",   240, 240)
            self.g6 = create_gauge(self.dark_panel, "voltage_v", 240, 240)

            dark_row.addWidget(self.dark_title)
            dark_row.addStretch()
            dark_row.addWidget(self.g4)
            dark_row.addWidget(self.g5)
            dark_row.addWidget(self.g6)
            dark_row.addStretch()
            layout.addWidget(self.dark_panel)

            # ---------------- 控制栏 ----------------
            bar = QHBoxLayout()
            bar.setSpacing(8)

            all_gauges = [self.g1, self.g2, self.g3, self.g4, self.g5, self.g6]

            def make_btn(text, cb):
                b = QPushButton(text)
                b.setCursor(Qt.PointingHandCursor)
                b.setFixedHeight(36)
                b.clicked.connect(cb)
                return b

            bar.addWidget(make_btn("Random", lambda: [
                g.set_value(random.uniform(g.min_value, g.max_value)) for g in all_gauges
            ]))
            bar.addWidget(make_btn("Zero", lambda: [
                g.set_value(0) for g in all_gauges
            ]))
            bar.addWidget(make_btn("Max", lambda: [
                g.set_value(g.max_value) for g in all_gauges
            ]))

            bar.addStretch()

            bar.addWidget(QLabel("Global Theme:"))
            self.theme_combo = QComboBox()
            self.theme_combo.addItems(["light", "dark"])
            self.theme_combo.setFixedWidth(110)
            self.theme_combo.setFixedHeight(34)
            self.theme_combo.currentTextChanged.connect(self._on_global_theme_change)
            bar.addWidget(self.theme_combo)

            layout.addLayout(bar)

            # ---------------- 面板样式 ----------------
            self.setStyleSheet("""
                QWidget#root { background-color: #E8E8ED; }
                QFrame#light_panel {
                    background-color: #FFFFFF;
                    border-radius: 18px;
                    border: 1px solid #E0E0E0;
                }
                QFrame#dark_panel {
                    background-color: #1C1C1E;
                    border-radius: 18px;
                }
                QLabel#panel_title {
                    color: #6E6E73;
                    font-family: 'SF Pro Text', 'Inter', sans-serif;
                    font-size: 11px;
                    font-weight: 700;
                    letter-spacing: 2px;
                    background: transparent;
                    padding-right: 8px;
                }
                QLabel#panel_title_dark {
                    color: #8E8E93;
                    font-family: 'SF Pro Text', 'Inter', sans-serif;
                    font-size: 11px;
                    font-weight: 700;
                    letter-spacing: 2px;
                    background: transparent;
                    padding-right: 8px;
                }
                QLabel {
                    color: #6E6E73;
                    background: transparent;
                    font-family: 'SF Pro Text', 'Inter', sans-serif;
                    font-size: 13px;
                }
                QPushButton {
                    background-color: #0066CC;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 18px;
                    padding: 8px 18px;
                    font-family: 'SF Pro Text', 'Inter', sans-serif;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:pressed { background-color: #0055AA; }
                QComboBox {
                    background-color: #FFFFFF;
                    color: #1D1D1F;
                    border: 1px solid #D2D2D7;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-family: 'SF Pro Text', 'Inter', sans-serif;
                    font-size: 13px;
                }
            """)

            # 初始值
            self.g1.set_value(180, animate=False)
            self.g2.set_value(72,  animate=False)
            self.g3.set_value(45,  animate=False)
            self.g4.set_value(4200, animate=False)
            self.g5.set_value(78,  animate=False)
            self.g6.set_value(12.6, animate=False)

        def _on_global_theme_change(self, theme: str):
            # ★ 只改这一行 —— 所有表盘自动跟着变
            ThemeManager.instance().set_theme(theme)

    win = Showcase()
    win.show()
    sys.exit(app.exec())