#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用模拟仪表盘 —— PySide6 / QPainter
Webflow 设计语言（Ink Black + 白色 Canvas + 五色 Accent + Inter）

┌──────────────────────────────────────────────────────────────────────┐
│  【使用本模块只需要记住 3 件事】                                        │
│                                                                       │
│  1. 注册色板桥接（应用启动时一次）                                      │
│       ThemeManager.instance().set_palette_provider(                    │
│           lambda name: palette_from_theme(Theme(name))                 │
│       )                                                                │
│                                                                       │
│  2. 创建表盘（选预设 + 可选覆盖参数）                                    │
│       g = AnalogGauge(parent, width=240, height=240,                    │
│                       preset="temperature_c",                           │
│                       value_position="left")                           │
│                                                                       │
│  3. 设值 / 切主题                                                       │
│       g.set_value(72.5)                                                │
│       ThemeManager.instance().set_theme("nord")                        │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  【值的位置 value_position —— 最常改的参数】                            │
│                                                                       │
│    "below"  值画在圆心下方（默认）                                      │
│    "left"   值画在表盘内部左侧空白弧区（9 点钟方向，推荐）                │
│    "right"  值画在表盘内部右侧空白弧区                                  │
│    "center" 值画在正中心（会跟指针重叠，慎用）                            │
│                                                                       │
│  值 + 单位永远垂直排列（值上、单位下），整体垂直居中于该位置中心点         │
│  想调左右偏移 → 改 _draw_value 里的 0.55 系数                           │
│  想调字号 → 改 _draw_value 里的 font_scale                             │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  【Webflow 视觉特征】                                                   │
│                                                                       │
│  · 白盘 + 1px hairline (#D8D8D8) 描边，像卡片一样干净                    │
│  · Webflow layered drop-shadow（多层柔和外阴影）                        │
│  · 扁平指针（近黑 ink #080808），无配重、无玻璃                          │
│  · Inter 字体（代替 WF Visual Sans Variable）                          │
│  · 五色 accent 语义弧带：green / yellow / red = success / warning / error│
│  · 无毛玻璃、无磨砂、无金属倒角                                          │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  【要改参数去哪找】                                                     │
│                                                                       │
│  ① GaugeConfig          —— 表盘的所有可配置项                           │
│  ② GAUGE_PRESETS        —— 37 个预设                                   │
│  ③ AnalogGauge.__init__ —— 创建表盘时的入口参数                         │
│  ④ DEFAULT_PALETTE      —— 无主题时的默认配色（Webflow 色板）            │
│  ⑤ palette_from_theme  —— 主题→色板的映射规则                          │
└──────────────────────────────────────────────────────────────────────┘
"""
import math
import random
from dataclasses import dataclass, replace, asdict
from typing import Callable, List, Optional, Tuple, Union

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
# 色板工具 —— 内部函数，不用改
# ===========================================================================
def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r, g, b):
    return (f"#{max(0,min(255,int(r))):02x}"
            f"{max(0,min(255,int(g))):02x}"
            f"{max(0,min(255,int(b))):02x}")


def _shift(hex_color: str, amount: float) -> str:
    """提亮/变暗颜色。amount > 0 提亮，< 0 变暗。取值 -1.0 ~ 1.0"""
    r, g, b = _hex_to_rgb(hex_color)
    if amount >= 0:
        r = r + (255 - r) * amount
        g = g + (255 - g) * amount
        b = b + (255 - b) * amount
    else:
        r = r * (1 + amount)
        g = g * (1 + amount)
        b = b * (1 + amount)
    return _rgb_to_hex(r, g, b)


def _is_dark_color(hex_color: str, threshold: int = 128) -> bool:
    r, g, b = _hex_to_rgb(hex_color)
    return (r + g + b) / 3 < threshold


# ===========================================================================
# 【参数区 ④】DEFAULT_PALETTE —— Webflow 风格默认配色
# ===========================================================================
# 无主题时的默认配色。全部取自 Webflow 设计系统。
# 键名含义：
#   bezel_*      外圈（Webflow: 白盘 + hairline 描边）
#   face_*       表盘面（Webflow: 纯白无渐晕）
#   tick_*       刻度（minor 次刻度 / medium 中刻度 / major 主刻度）
#   number       刻度数字
#   label        单位文字
#   value_text   当前值大字
#   needle       指针
#   needle_hi    指针侧面高光线
#   hub_*        中心轴
#   arc_*        语义弧带（success / warning / error）
#   glass_*      玻璃反光（Webflow: 全部 0 = 无玻璃）
# ===========================================================================
DEFAULT_PALETTE = {
    # ---- 外圈（Webflow: 白盘 + hairline）----
    "bezel_hi":    "#FFFFFF",
    "bezel_light": "#FFFFFF",
    "bezel_dark":  "#FAFAFA",
    "bezel_lo":    "#D8D8D8",

    # ---- 表盘面（Webflow: 纯白无渐晕）----
    "face_inner":  "#FFFFFF",
    "face_mid":    "#FFFFFF",
    "face_outer":  "#FFFFFF",

    # ---- 刻度（Webflow: ink → mute-soft 三档）----
    "tick_minor":  "#ABABAB",
    "tick_medium": "#898989",
    "tick_major":  "#080808",

    # ---- 文字 ----
    "number":      "#080808",
    "label":       "#5A5A5A",
    "value_text":  "#146EF5",

    # ---- 指针 ----
    "needle":      "#080808",
    "needle_hi":   "#363636",

    # ---- 中心轴 ----
    "hub_outer":   "#080808",
    "hub_hi":      "#363636",
    "hub_inner":   "#FFFFFF",

    # ---- 语义弧带（Webflow 三色）----
    "arc_green":   "#00D722",
    "arc_yellow":  "#FFAE13",
    "arc_red":     "#EE1D36",

    # ---- 玻璃（Webflow: 全部 0 = 无玻璃）----
    "glass_a_hi":  0,
    "glass_a_mid": 0,
    "glass_tint":  0,
}


# ===========================================================================
# 【参数区 ⑤】palette_from_theme —— 主题 → Webflow 色板的映射规则
# ===========================================================================
def palette_from_theme(theme) -> dict:
    is_dark = bool(getattr(theme, "is_dark", False))
    palette = dict(DEFAULT_PALETTE)

    if is_dark:
        card = getattr(theme, "card_bg", "#1A1A1A")
        bg   = getattr(theme, "bg", "#0A0A0A")
        fg   = getattr(theme, "fg", "#F0F0F0")
        fg_mid = getattr(theme, "fg_mid", "#C0C0C0")
        fg_mute = getattr(theme, "fg_mute", "#898989")

        palette.update({
            "bezel_hi":    _shift(card, 0.10),
            "bezel_light": card,
            "bezel_dark":  _shift(card, -0.06),
            "bezel_lo":    _shift(card, -0.20),
            "face_inner":  card,
            "face_mid":    card,
            "face_outer":  bg,
            "tick_minor":  fg_mute,
            "tick_medium": fg_mid,
            "tick_major":  fg,
            "number":      fg,
            "label":       fg_mute,
            "value_text":  "#3B89FF",
            "needle":      fg,
            "needle_hi":   "#ABABAB",
            "hub_outer":   fg,
            "hub_hi":      "#FFFFFF",
            "hub_inner":   card,
        })

    return palette


# ===========================================================================
# 配置模型
# ===========================================================================
@dataclass
class GaugeZone:
    """语义区间 —— 也可直接用 (start, end, color) 元组"""
    start: float
    end: float
    color: str


ZoneSpec = Union[GaugeZone, Tuple[float, float, str]]


# ===========================================================================
# 【参数区 ①】GaugeConfig —— 表盘全部可配置项
# ===========================================================================
# 参数按修改频率排列，越靠前越常用。
# ===========================================================================
@dataclass
class GaugeConfig:
    # ================================================================
    # ★★★ 最常用 —— 值的位置（第一眼看这里）
    # ================================================================
    # "below"  值画在圆心下方（默认）
    # "left"   值画在表盘内部左侧空白弧区（9 点钟方向，最常用）
    # "right"  值画在表盘内部右侧空白弧区
    # "center" 值画在正中心（会跟指针重叠）
    #
    # 想调左右偏移 → 改 AnalogGauge._draw_value 里的 0.55 系数
    # 想调字号     → 改 AnalogGauge._draw_value 里的 font_scale
    # ================================================================
    value_position: str = "below"

    # ================================================================
    # ★★★ 最常用 —— 5 个核心参数
    # ================================================================
    min_value: float = 0.0          # 最小值（表盘起点）
    max_value: float = 100.0        # 最大值（表盘终点）
    unit: str = ""                  # 单位文字
    major_step: float = 20.0        # 主刻度间隔
    minor_step: float = 5.0         # 次刻度间隔

    # ================================================================
    # ★★ 常用 —— 名称 / 颜色 / 格式
    # ================================================================
    title: str = ""
    accent_color: Optional[str] = None   # 当前值颜色；None = 主题色
    needle_color: Optional[str] = None   # 指针颜色；None = 主题色
    decimals: int = 0

    # ================================================================
    # ★★ 常用 —— 显示开关
    # ================================================================
    show_numbers: bool = True
    show_unit: bool = True
    show_value: bool = True
    show_zones: bool = True
    show_glass: bool = False

    # ================================================================
    # ★★ 常用 —— 背景 & 阴影
    # ================================================================
    transparent: bool = True
    embed_style: str = "raised"

    # ================================================================
    # ★ 偶尔 —— 语义弧带
    # ================================================================
    zones: Optional[List[ZoneSpec]] = None

    # ================================================================
    # ★ 偶尔 —— 表盘几何
    # ================================================================
    angle_start: float = -135.0
    angle_range: float = 270.0

    # ================================================================
    # ★ 极少 —— 风格化开关（Webflow 默认值）
    # ================================================================
    frosted_face: bool = False
    mono_numbers: bool = False
    needle_shadow: bool = True
    needle_counterweight: bool = False
    three_tier_ticks: bool = False
    red_marker: bool = False
    red_marker_value: float = 0.0


# ===========================================================================
# 全局主题广播器
# ===========================================================================
class GaugeThemeManager(QObject):
    """主题总线。只广播主题名，具体色板由 palette_provider 决定"""
    theme_changed = Signal(str)
    _instance: Optional["GaugeThemeManager"] = None

    def __init__(self):
        super().__init__()
        self._theme = "light"
        self._palette_provider: Optional[Callable[[str], dict]] = None

    @classmethod
    def instance(cls) -> "GaugeThemeManager":
        if cls._instance is None:
            cls._instance = GaugeThemeManager()
        return cls._instance

    def theme(self) -> str:
        return self._theme

    def set_palette_provider(self, fn: Callable[[str], dict]):
        self._palette_provider = fn

    def get_palette(self, name: Optional[str] = None) -> dict:
        n = name or self._theme
        if self._palette_provider is None:
            return dict(DEFAULT_PALETTE)
        try:
            return self._palette_provider(n)
        except Exception:
            return dict(DEFAULT_PALETTE)

    def set_theme(self, name: str):
        if not name or name == self._theme:
            return
        self._theme = name
        self.theme_changed.emit(name)


def set_global_theme(name: str):
    ThemeManager.instance().set_theme(name)


def get_global_theme() -> str:
    return ThemeManager.instance().theme()


# ===========================================================================
# 【参数区 ②】GAUGE_PRESETS —— 37 个预设（配色用 Webflow 五色）
# ===========================================================================
GAUGE_PRESETS = {
    # ---------------- 压力 ----------------
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
    # ---------------- 温度（Webflow accent-orange）----------------
    "temperature_c": dict(unit="°C", title="TEMPERATURE",
                          min_value=-20, max_value=120, major_step=20, minor_step=5,
                          accent_color="#FF6B00", needle_color="#FF6B00"),
    "temperature_f": dict(unit="°F", title="TEMPERATURE",
                          min_value=0, max_value=250, major_step=50, minor_step=10,
                          accent_color="#FF6B00", needle_color="#FF6B00"),
    "temperature_k": dict(unit="K", title="TEMPERATURE",
                          min_value=250, max_value=400, major_step=30, minor_step=10,
                          accent_color="#FF6B00", needle_color="#FF6B00"),
    # ---------------- 转速（Webflow accent-purple）----------------
    "rpm": dict(unit="RPM", title="RPM",
                min_value=0, max_value=8000, major_step=1000, minor_step=200,
                accent_color="#7A3DFF", needle_color="#7A3DFF"),
    "rps": dict(unit="RPS", title="RPS",
                min_value=0, max_value=150, major_step=30, minor_step=5,
                accent_color="#7A3DFF", needle_color="#7A3DFF"),
    # ---------------- 湿度（Webflow accent-blue）----------------
    "humidity": dict(unit="%RH", title="HUMIDITY",
                     min_value=0, max_value=100, major_step=10, minor_step=2,
                     accent_color="#3B89FF", needle_color="#3B89FF"),
    # ---------------- 电压（Webflow accent-yellow）----------------
    "voltage_v":  dict(unit="V", title="VOLTAGE",
                       min_value=0, max_value=30, major_step=5, minor_step=1,
                       accent_color="#FFAE13", needle_color="#FFAE13", decimals=1),
    "voltage_mv": dict(unit="mV", title="VOLTAGE",
                       min_value=0, max_value=1000, major_step=200, minor_step=50,
                       accent_color="#FFAE13", needle_color="#FFAE13"),
    "voltage_kv": dict(unit="kV", title="VOLTAGE",
                       min_value=0, max_value=10, major_step=2, minor_step=0.5,
                       accent_color="#FFAE13", needle_color="#FFAE13", decimals=1),
    # ---------------- 电流（Webflow accent-yellow）----------------
    "current_a":  dict(unit="A", title="CURRENT",
                       min_value=0, max_value=20, major_step=5, minor_step=1,
                       accent_color="#FFAE13", needle_color="#FFAE13", decimals=1),
    "current_ma": dict(unit="mA", title="CURRENT",
                       min_value=0, max_value=500, major_step=100, minor_step=20,
                       accent_color="#FFAE13", needle_color="#FFAE13"),
    # ---------------- 功率（Webflow accent-red）----------------
    "power_w":  dict(unit="W", title="POWER",
                     min_value=0, max_value=5000, major_step=1000, minor_step=200,
                     accent_color="#EE1D36", needle_color="#EE1D36"),
    "power_kw": dict(unit="kW", title="POWER",
                     min_value=0, max_value=5, major_step=1, minor_step=0.2,
                     accent_color="#EE1D36", needle_color="#EE1D36", decimals=1),
    # ---------------- 百分比 / 进度 ----------------
    "percentage": dict(unit="%", title="PERCENT",
                       min_value=0, max_value=100, major_step=10, minor_step=2),
    "progress":   dict(unit="%", title="PROGRESS",
                       min_value=0, max_value=100, major_step=20, minor_step=5,
                       show_zones=False,
                       accent_color="#00D722", needle_color="#00D722"),
    # ---------------- 油量 / 电池 ----------------
    "fuel":       dict(unit="%", title="FUEL",
                       min_value=0, max_value=100, major_step=20, minor_step=5),
    "fuel_liter": dict(unit="L", title="FUEL",
                       min_value=0, max_value=60, major_step=10, minor_step=2),
    "battery":    dict(unit="%", title="BATTERY",
                       min_value=0, max_value=100, major_step=20, minor_step=5),
    # ---------------- 速度 ----------------
    "speed_kph": dict(unit="km/h", title="SPEED",
                      min_value=0, max_value=240, major_step=40, minor_step=10),
    "speed_mph": dict(unit="mph", title="SPEED",
                      min_value=0, max_value=150, major_step=30, minor_step=5),
    "speed_ms":  dict(unit="m/s", title="SPEED",
                      min_value=0, max_value=50, major_step=10, minor_step=2),
    # ---------------- 流量（Webflow accent-blue）----------------
    "flow_lpm": dict(unit="L/min", title="FLOW",
                     min_value=0, max_value=100, major_step=20, minor_step=5,
                     accent_color="#3B89FF", needle_color="#3B89FF"),
    "flow_m3h": dict(unit="m³/h", title="FLOW",
                     min_value=0, max_value=50, major_step=10, minor_step=2,
                     accent_color="#3B89FF", needle_color="#3B89FF"),
    # ---------------- 频率 ----------------
    "frequency_hz":  dict(unit="Hz", title="FREQUENCY",
                          min_value=0, max_value=100, major_step=20, minor_step=5),
    "frequency_khz": dict(unit="kHz", title="FREQUENCY",
                          min_value=0, max_value=1000, major_step=200, minor_step=50),
    # ---------------- 光照 / 噪声（Webflow accent-yellow）----------------
    "lux":      dict(unit="lx", title="LIGHT",
                     min_value=0, max_value=2000, major_step=500, minor_step=100,
                     accent_color="#FFAE13", needle_color="#FFAE13"),
    "noise_db": dict(unit="dB", title="NOISE",
                     min_value=0, max_value=120, major_step=20, minor_step=5),
}


# ===========================================================================
# 通用仪表控件
# ===========================================================================
class AnalogGauge(QWidget):
    """通用模拟仪表 —— Webflow 风格"""

    valueChanged = Signal(float)

    # ==================================================================
    # 【参数区 ③】__init__ —— 创建表盘的入口参数
    # ==================================================================
    # 四种创建方式：
    #   ① 只用预设：  AnalogGauge(parent, 240, 240, preset="temperature_c")
    #   ② 预设+覆盖： AnalogGauge(parent, 240, 240, preset="temperature_c",
    #                              max_value=200, value_position="left")
    #   ③ 完全自定义：AnalogGauge(parent, 240, 240,
    #                              min_value=0, max_value=500,
    #                              unit="kPa", major_step=100, minor_step=20)
    #   ④ 值在左侧：  AnalogGauge(parent, 240, 240, preset="rpm",
    #                              value_position="left")
    # ==================================================================
    def __init__(
        self,
        parent=None,
        width: int = 340,
        height: int = 340,
        preset: Optional[str] = None,
        config: Optional[GaugeConfig] = None,
        palette: Optional[dict] = None,
        auto_follow_theme: bool = True,
        **kwargs,
    ):
        super().__init__(parent)
        self.setFixedSize(width, height)

        self._auto_follow_theme = auto_follow_theme

        # ---- 色板初始化 ----
        self._palette = dict(DEFAULT_PALETTE)
        if palette:
            self._palette.update(palette)
        if auto_follow_theme:
            self._palette.update(GaugeThemeManager.instance().get_palette())

        # ---- 配置装配 ----
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
            config = GaugeConfig(**base)
        elif kwargs:
            config = replace(config, **kwargs)
        self._config = config

        self._value = config.min_value
        self._display_value = config.min_value

        # ---- 透明背景 ----
        if config.transparent:
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WA_NoSystemBackground, True)
            self.setAutoFillBackground(False)

        # ---- 指针动画 ----
        self._anim = QPropertyAnimation(self, b"displayValue")
        self._anim.setDuration(400)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        # ---- 订阅主题广播 ----
        if auto_follow_theme:
            GaugeThemeManager.instance().theme_changed.connect(self._on_theme_changed)

        self._setup_fonts()

    # ==================================================================
    # 主题跟随
    # ==================================================================
    def _on_theme_changed(self, name: str):
        if not self._auto_follow_theme:
            return
        self.set_palette(GaugeThemeManager.instance().get_palette(name))

    def follow_theme(self, follow: bool = True):
        mgr = GaugeThemeManager.instance()
        if follow and not self._auto_follow_theme:
            try:
                mgr.theme_changed.connect(self._on_theme_changed)
            except Exception:
                pass
            self._auto_follow_theme = True
            self.set_palette(mgr.get_palette())
        elif not follow and self._auto_follow_theme:
            try:
                mgr.theme_changed.disconnect(self._on_theme_changed)
            except Exception:
                pass
            self._auto_follow_theme = False

    def is_following_theme(self) -> bool:
        return self._auto_follow_theme

    # ==================================================================
    # 色板注入
    # ==================================================================
    def set_palette(self, palette: dict):
        if not palette:
            return
        self._palette = {**DEFAULT_PALETTE, **palette}
        self.update()

    def palette(self) -> dict:
        return dict(self._palette)

    def merge_palette(self, **overrides):
        self._palette.update(overrides)
        self.update()

    # ==================================================================
    # 字体
    # ==================================================================
    def _setup_fonts(self):
        families = set(QFontDatabase.families())

        def pick(*candidates):
            for name in candidates:
                if name in families:
                    return name
            return candidates[-1]

        self._display_family = pick("Inter", "SF Pro Display", "Helvetica Neue")
        self._text_family    = pick("Inter", "SF Pro Text",    "Helvetica Neue")
        self._mono_family = pick(
            "JetBrains Mono", "Inconsolata", "Consolas",
            "Menlo", "Courier New",
        )

    # ==================================================================
    # 动画属性
    # ==================================================================
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

    def set_unit(self, unit: str):
        self._config = replace(self._config, unit=unit)
        self.update()

    def set_value_position(self, pos: str):
        """运行时改值的位置：below / left / right / center"""
        if pos in ("below", "left", "right", "center"):
            self._config = replace(self._config, value_position=pos)
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
        self._value = max(config.min_value, min(config.max_value, self._value))
        self._display_value = self._value
        self.update()

    def config(self) -> GaugeConfig:
        return self._config

    def config_dict(self) -> dict:
        return asdict(self._config)

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

    # ==================================================================
    # 几何 / 工具
    # ==================================================================
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

        t = self._palette
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - max(10, min(w, h) * 0.055)

        if not self._config.transparent:
            p.fillRect(self.rect(), QColor(t.get("bg", "#FFFFFF")))

        # ---- 阴影 ----
        style = self._config.embed_style
        if style == "raised":
            self._draw_raised_shadow(p, cx, cy, R)
        elif style == "inset":
            self._draw_inset_ring(p, cx, cy, R)

        # ---- 白盘 + hairline ----
        self._draw_bezel(p, cx, cy, R, t)

        # ---- 表盘面 ----
        bezel_thickness = max(4, R * 0.04)
        face_R = R - bezel_thickness - 1
        self._draw_face(p, cx, cy, face_R, t)

        if self._config.frosted_face:
            self._draw_frosted_face(p, cx, cy, face_R, t)

        if self._config.red_marker:
            self._draw_red_marker(p, cx, cy, face_R, t)

        # ---- 语义弧带 ----
        arc_r_outer = face_R - R * 0.10
        arc_r_inner = arc_r_outer - max(5, R * 0.045)
        if self._config.show_zones:
            self._draw_zones(p, cx, cy, arc_r_outer, arc_r_inner, t)

        # ---- 刻度 ----
        tick_outer        = arc_r_inner - R * 0.045
        tick_major_inner  = tick_outer - R * 0.10
        tick_minor_inner  = tick_outer - R * 0.058
        tick_medium_inner = tick_outer - R * 0.080
        self._draw_ticks(p, cx, cy,
                         tick_outer,
                         tick_major_inner,
                         tick_medium_inner,
                         tick_minor_inner, t)

        # ---- 刻度数字 ----
        num_r = tick_major_inner - R * 0.10
        if self._config.show_numbers:
            self._draw_numbers(p, cx, cy, num_r, t)

        if self._config.show_glass:
            self._draw_glass(p, cx, cy, face_R, t)

        # ---- 当前值 + 单位（内部按 value_position 定位）----
        if self._config.show_value:
            self._draw_value(p, cx, cy, R, t)

        # ---- 指针 ----
        needle_len = num_r - R * 0.02
        self._draw_needle(p, cx, cy, needle_len, R, t)

        # ---- 中心轴 ----
        self._draw_hub(p, cx, cy, R, t)

        p.end()

    # ==================================================================
    # Webflow layered drop-shadow
    # ==================================================================
    def _draw_raised_shadow(self, p, cx, cy, R):
        layers = [
            (0.020, 1.08, 22),
            (0.055, 1.15, 16),
            (0.095, 1.24, 10),
            (0.150, 1.34, 5),
        ]
        p.setPen(Qt.NoPen)
        for off_y, rad, alpha in layers:
            g = QRadialGradient(QPointF(cx, cy + R * off_y), R * rad)
            g.setColorAt(0.00, QColor(0, 0, 0, 0))
            g.setColorAt(0.72, QColor(0, 0, 0, 0))
            g.setColorAt(0.80, QColor(0, 0, 0, alpha // 2))
            g.setColorAt(0.90, QColor(0, 0, 0, alpha))
            g.setColorAt(0.97, QColor(0, 0, 0, alpha // 2))
            g.setColorAt(1.00, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(cx, cy + R * off_y), R * rad, R * rad)

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

    def _draw_bezel(self, p, cx, cy, R, t):
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(t["bezel_hi"])))
        p.drawEllipse(QPointF(cx, cy), R, R)
        pen = QPen(QColor(t["bezel_lo"]))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R - 0.5, R - 0.5)

    def _draw_face(self, p, cx, cy, R, t):
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(t["face_mid"])))
        p.drawEllipse(QPointF(cx, cy), R, R)

    def _draw_frosted_face(self, p, cx, cy, R, t):
        g = QRadialGradient(QPointF(cx - R * 0.25, cy - R * 0.30), R * 1.1)
        g.setColorAt(0.0, QColor(255, 255, 255, 12))
        g.setColorAt(0.6, QColor(255, 255, 255, 3))
        g.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), R, R)

    def _draw_red_marker(self, p, cx, cy, R, t):
        angle = self._value_to_angle(self._config.red_marker_value)
        r_out = R - R * 0.045
        r_in = R - R * 0.18
        x1, y1 = self._polar(cx, cy, r_out, angle)
        x2, y2 = self._polar(cx, cy, r_in, angle)
        pen = QPen(QColor(t["arc_red"]))
        pen.setWidthF(max(1.2, R * 0.010))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

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

    def _draw_ticks(self, p, cx, cy, outer, major_in, medium_in, minor_in, t):
        cfg = self._config
        if cfg.minor_step <= 0:
            return
        if cfg.major_step / cfg.minor_step >= 10:
            medium_step = cfg.major_step / 5
        elif cfg.major_step / cfg.minor_step >= 4:
            medium_step = cfg.major_step / 2
        else:
            medium_step = None
        v = cfg.min_value
        eps = 1e-6
        while v <= cfg.max_value + eps:
            is_major = abs((v / cfg.major_step) - round(v / cfg.major_step)) < 0.01
            is_medium = (not is_major
                         and medium_step is not None
                         and abs((v / medium_step) - round(v / medium_step)) < 0.01)
            angle = self._value_to_angle(v)
            if is_major:
                r_in, width, color = major_in, 2.0, t["tick_major"]
            elif is_medium and cfg.three_tier_ticks:
                r_in, width, color = medium_in, 1.4, t["tick_medium"]
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

    def _draw_numbers(self, p, cx, cy, r, t):
        cfg = self._config
        if cfg.mono_numbers:
            font = QFont(self._mono_family)
            font.setPixelSize(max(9, int(r * 0.070)))
            font.setWeight(QFont.Weight.Medium)
        else:
            font = QFont(self._display_family)
            font.setPixelSize(max(9, int(r * 0.075)))
            font.setWeight(QFont.Weight.Medium)
        v = cfg.min_value
        while v <= cfg.max_value + 1e-6:
            is_major = abs((v / cfg.major_step) - round(v / cfg.major_step)) < 0.01
            if is_major:
                angle = self._value_to_angle(v)
                nx, ny = self._polar(cx, cy, r, angle)
                p.setPen(QPen(QColor(t["number"])))
                p.setFont(font)
                rect = QRectF(nx - 28, ny - 10, 56, 20)
                p.drawText(rect, Qt.AlignCenter, self._format_value(v))
            v += cfg.major_step

    def _draw_glass(self, p, cx, cy, R, t):
        a_hi  = t["glass_a_hi"]
        a_mid = t["glass_a_mid"]
        tint  = t["glass_tint"]
        if tint <= 0 and a_hi <= 0 and a_mid <= 0:
            return
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

    # ==================================================================
    # ★★★ 当前值 + 单位 —— 按 value_position 决定位置 ★★★
    # ==================================================================
    # ┌───────────────────────────────────────────────────────────┐
    # │  【如何修改值的位置】                                       │
    # │                                                           │
    # │  改 GaugeConfig.value_position 字段：                      │
    # │     "below"  圆心下方（默认）                              │
    # │     "left"   表盘内部左侧空白弧区（9 点钟方向）              │
    # │     "right"  表盘内部右侧空白弧区                          │
    # │     "center" 正中心                                       │
    # │                                                           │
    # │  【如何微调位置】                                           │
    # │                                                           │
    # │  · 左右偏移 —— 改下面的 0.55 系数：                          │
    # │      0.45 → 靠近中心                                       │
    # │      0.55 → 中心和边缘之间（推荐）                          │
    # │      0.65 → 靠近刻度数字                                    │
    # │                                                           │
    # │  · 上下偏移 —— 改 cy 后面的数字：                            │
    # │      center_y = cy                → 垂直居中                │
    # │      center_y = cy + R * 0.10    → 下移 10% 半径            │
    # │      center_y = cy - R * 0.10    → 上移 10% 半径            │
    # │                                                           │
    # │  · 字号 —— 改 font_scale：                                  │
    # │      0.90 → 略小（left/right 用，避免溢出）                 │
    # │      1.00 → 标准（below/center 用）                         │
    # │      1.10 → 略大                                           │
    # └───────────────────────────────────────────────────────────┘
    # ==================================================================
    def _draw_value(self, p, cx, cy, R, t):
        val_text = self._format_value(self._display_value)

        # ---- 位置中心点 + 字号系数 ----
        pos = self._config.value_position
        if pos == "left":
            # ★ 9 点钟方向 —— 中心偏左 55% 半径
            center_x = cx - R * 0.55      # ← 想更靠左改大，想更靠右改小
            center_y = cy                 # ← 想上下移动改这里
            font_scale = 0.90             # ← 想字号更大改这里
        elif pos == "right":
            center_x = cx + R * 0.55
            center_y = cy
            font_scale = 0.90
        elif pos == "center":
            center_x = cx
            center_y = cy
            font_scale = 1.00
        else:  # "below"
            center_x = cx
            center_y = cy + R * 0.10
            font_scale = 1.00

        # ---- 值字体 ----
        f_val = QFont(self._display_family)
        f_val.setPixelSize(max(14, int(R * 0.22 * font_scale)))
        f_val.setWeight(QFont.Weight.DemiBold)

        # ---- 无单位：单行居中 ----
        if not (self._config.show_unit and self._config.unit):
            p.setPen(QPen(QColor(t["value_text"])))
            p.setFont(f_val)
            fm_val = p.fontMetrics()
            val_w = fm_val.horizontalAdvance(val_text)
            baseline_y = center_y + fm_val.ascent() - fm_val.height() / 2
            p.drawText(QPointF(center_x - val_w / 2, baseline_y), val_text)
            return

        # ---- 有单位：值 + 单位垂直排列，整体垂直居中 ----
        p.setFont(f_val)
        fm_val = p.fontMetrics()
        val_w      = fm_val.horizontalAdvance(val_text)
        val_h      = fm_val.height()
        val_ascent = fm_val.ascent()

        f_unit = QFont(self._text_family)
        f_unit.setPixelSize(max(9, int(R * 0.075 * font_scale)))
        f_unit.setWeight(QFont.Weight.Medium)

        p.setFont(f_unit)
        fm_unit = p.fontMetrics()
        unit_w      = fm_unit.horizontalAdvance(self._config.unit)
        unit_h      = fm_unit.height()
        unit_ascent = fm_unit.ascent()

        gap = max(2, int(R * 0.02))
        total_h = val_h + gap + unit_h
        top_y = center_y - total_h / 2

        # 值（水平居中于 center_x）
        p.setPen(QPen(QColor(t["value_text"])))
        p.setFont(f_val)
        p.drawText(QPointF(center_x - val_w / 2, top_y + val_ascent),
                   val_text)

        # 单位（水平居中于 center_x）
        p.setPen(QPen(QColor(t["label"])))
        p.setFont(f_unit)
        p.drawText(QPointF(center_x - unit_w / 2,
                           top_y + val_h + gap + unit_ascent),
                   self._config.unit)

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

        tail_len = (12 if self._config.needle_counterweight else 6) * s
        tail_w   = 3.0 * s
        shoulder = 4.5 * s

        def pt(r, w):
            return QPointF(cx + r * cos_a + w * cos_p,
                           cy + r * sin_a + w * sin_p)

        if self._config.needle_shadow:
            shadow_off_x = 1.2 * s
            shadow_off_y = 1.8 * s
            shadow_poly = QPolygonF([
                QPointF(cx + (-tail_len) * cos_a + shadow_off_x,
                        cy + (-tail_len) * sin_a + shadow_off_y),
                QPointF(cx + (-tail_len + 1 * s) * cos_a + tail_w * cos_p + shadow_off_x,
                        cy + (-tail_len + 1 * s) * sin_a + tail_w * sin_p + shadow_off_y),
                QPointF(cx + (length * 0.30) * cos_a + shoulder * cos_p + shadow_off_x,
                        cy + (length * 0.30) * sin_a + shoulder * sin_p + shadow_off_y),
                QPointF(cx + length * cos_a + shadow_off_x,
                        cy + length * sin_a + shadow_off_y),
                QPointF(cx + (length * 0.30) * cos_a - shoulder * cos_p + shadow_off_x,
                        cy + (length * 0.30) * sin_a - shoulder * sin_p + shadow_off_y),
                QPointF(cx + (-tail_len + 1 * s) * cos_a - tail_w * cos_p + shadow_off_x,
                        cy + (-tail_len + 1 * s) * sin_a - tail_w * sin_p + shadow_off_y),
            ])
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(0, 0, 0, 45)))
            p.drawPolygon(shadow_poly)

        poly = QPolygonF([
            pt(-tail_len,         0.0),
            pt(-tail_len + 1 * s, tail_w),
            pt(length * 0.30,     shoulder),
            pt(length,            0.0),
            pt(length * 0.30,    -shoulder),
            pt(-tail_len + 1 * s, -tail_w),
        ])
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(t["needle"])))
        p.drawPolygon(poly)

        pen = QPen(QColor(t["needle_hi"]))
        pen.setWidthF(max(0.6, 0.9 * s))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        hx1, hy1 = self._polar(cx, cy, length * 0.15, angle)
        hx2, hy2 = self._polar(cx, cy, length * 0.75, angle)
        off = 1.2 * s
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
ThemeManager = GaugeThemeManager


def create_gauge(parent=None, preset: str = "percentage",
                 width: int = 260, height: int = 260, **kwargs) -> AnalogGauge:
    """便捷工厂"""
    return AnalogGauge(parent, width, height, preset=preset, **kwargs)