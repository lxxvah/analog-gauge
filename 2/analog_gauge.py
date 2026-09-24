#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用模拟仪表盘 —— PySide6 / QPainter
瑞士精密仪表风格（Braun / Dieter Rams 一脉）

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
│                       preset="temperature_c")                          │
│                                                                       │
│  3. 设值 / 切主题                                                       │
│       g.set_value(72.5)                                                │
│       ThemeManager.instance().set_theme("nord")                        │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  【要改参数去哪找】                                                     │
│                                                                       │
│  ① GaugeConfig          —— 表盘的所有可配置项（量程、单位、风格开关）    │
│  ② GAUGE_PRESETS        —— 37 个预设（不改代码就能用的）                │
│  ③ AnalogGauge.__init__ —— 创建表盘时的入口参数（parent/width/preset） │
│  ④ DEFAULT_PALETTE      —— 无主题时的默认配色                          │
│  ⑤ palette_from_theme  —— 主题→色板的映射规则                         │
│                                                                       │
│  99% 情况下你只需要：                                                   │
│    · 用 preset（不改代码）                                             │
│    · 或覆盖 GaugeConfig 里几个字段                                      │
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
# 【参数区 ④】DEFAULT_PALETTE —— 无主题时的默认配色
# ===========================================================================
# 用途：如果你不注册 palette_provider，表盘会用这套色。
# 想改默认色，直接改这里的十六进制值。
# 键名含义：
#   bezel_*      金属外圈（四层渐变，光源左上）
#   face_*       表盘面（内→外三层径向渐变）
#   tick_*       刻度（minor 次刻度 / medium 中刻度 / major 主刻度）
#   number       刻度数字
#   label        单位文字
#   value_text   当前值大字
#   needle       指针
#   needle_hi    指针侧面高光线
#   hub_*        中心轴（外圈/高光/内芯）
#   arc_*        语义弧带（绿/黄/红）
#   glass_*      玻璃反光强度（alpha 0-255）
# ===========================================================================
DEFAULT_PALETTE = {
    # ---- 金属外圈（光源左上）----
    "bezel_hi":    "#FFFFFF",    # 左上最亮
    "bezel_light": "#E8E8ED",    # 亮部
    "bezel_dark":  "#C8C8CE",    # 暗部
    "bezel_lo":    "#9A9AA0",    # 右下最暗

    # ---- 表盘面（内→外）----
    "face_inner":  "#FBFBFD",    # 中心
    "face_mid":    "#F2F2F5",    # 中段
    "face_outer":  "#DEDEE4",    # 边缘

    # ---- 刻度 ----
    "tick_minor":  "#8E8E93",    # 次刻度（最细最短）
    "tick_medium": "#5A5A5E",    # 中刻度（三级刻度开启时用）
    "tick_major":  "#1D1D1F",    # 主刻度（最粗最长）

    # ---- 文字 ----
    "number":      "#1D1D1F",    # 刻度数字
    "label":       "#86868B",    # 单位
    "value_text":  "#0066CC",    # 当前值大字（强调色）

    # ---- 指针 ----
    "needle":      "#FF3B30",    # 指针主体
    "needle_hi":   "#FFB0A8",    # 指针侧面高光

    # ---- 中心轴 ----
    "hub_outer":   "#1D1D1F",    # 轴外圈
    "hub_hi":      "#5A5A5E",    # 轴左上高光
    "hub_inner":   "#FBFBFD",    # 轴内芯

    # ---- 语义弧带 ----
    "arc_green":   "#34C759",    # 安全区
    "arc_yellow":  "#FFCC00",    # 警告区
    "arc_red":     "#FF3B30",    # 危险区

    # ---- 玻璃反光（数值越大反光越强，0-255）----
    "glass_a_hi":  150,          # 主反光峰值
    "glass_a_mid": 45,           # 反光中段
    "glass_tint":  12,           # 整体白蒙版（0 = 无玻璃感）
}


# ===========================================================================
# 【参数区 ⑤】palette_from_theme —— 主题 → 色板的映射规则
# ===========================================================================
# 用途：把外部主题对象（如 theme.py 的 Theme）转成仪表色板。
# 要求 theme 对象至少有这些属性：
#   is_dark, card_bg, bg, bg_deep, fg, fg_mid, fg_mute,
#   primary, danger, warning, success
#
# 想改某个元素对应到主题的哪个颜色？改这里的映射即可。
# ===========================================================================
def palette_from_theme(theme) -> dict:
    is_dark = bool(getattr(theme, "is_dark", False))
    card    = getattr(theme, "card_bg", "#FFFFFF")
    bg      = getattr(theme, "bg", "#FFFFFF")
    bg_deep = getattr(theme, "bg_deep", bg)

    return {
        # 金属外圈 → 卡片色派生
        "bezel_hi":    _shift(card,  0.10 if not is_dark else -0.10),
        "bezel_light": card,
        "bezel_dark":  _shift(card, -0.15 if not is_dark else -0.25),
        "bezel_lo":    bg_deep,

        # 表盘 → 卡片色派生
        "face_inner":  _shift(card,  0.04 if not is_dark else 0.02),
        "face_mid":    card,
        "face_outer":  bg,

        # 刻度 → 前景色三档
        "tick_minor":  getattr(theme, "fg_mute", "#888888"),
        "tick_medium": getattr(theme, "fg_mid", "#555555"),
        "tick_major":  getattr(theme, "fg", "#000000"),

        # 文字
        "number":      getattr(theme, "fg", "#000000"),
        "label":       getattr(theme, "fg_mute", "#888888"),
        "value_text":  getattr(theme, "primary", "#007AFF"),  # 强调色用主题 primary

        # 指针 → 主题 danger 色
        "needle":      getattr(theme, "danger", "#FF3B30"),
        "needle_hi":   _shift(getattr(theme, "danger", "#FF3B30"), 0.30),

        # 中心轴
        "hub_outer":   getattr(theme, "fg", "#000000"),
        "hub_hi":      getattr(theme, "fg_mid", "#666666"),
        "hub_inner":   card,

        # 弧带 → 主题语义色
        "arc_green":   getattr(theme, "success", "#34C759"),
        "arc_yellow":  getattr(theme, "warning", "#FFCC00"),
        "arc_red":     getattr(theme, "danger",  "#FF3B30"),

        # 玻璃反光（暗色主题减弱）
        "glass_a_hi":  90 if is_dark else 150,
        "glass_a_mid": 30 if is_dark else 45,
        "glass_tint":  8  if is_dark else 12,
    }


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
# 这是表盘的"数据模型"。所有可调参数都在这里。
# 创建表盘时通过关键字参数传入，运行时通过 replace() 修改。
#
# 参数分四档（按修改频率从高到低）：
#   ★★★ 最常用 —— 90% 场景只改这 5 个
#   ★★  常用   —— 特殊需求会改
#   ★   偶尔   —— 知道有就行
# ===========================================================================
@dataclass
class GaugeConfig:
    # ================================================================
    # ★★★ 最常用 —— 5 个核心参数（90% 场景只改这里）
    # ================================================================
    min_value: float = 0.0          # 最小值（表盘起点）
    max_value: float = 100.0        # 最大值（表盘终点）
    unit: str = ""                  # 单位文字，如 "mmHg"、"°C"、"RPM"
    major_step: float = 20.0        # 主刻度间隔（带数字的那条）
    minor_step: float = 5.0         # 次刻度间隔（最细的那条）

    # ================================================================
    # ★★ 常用 —— 名称 / 颜色 / 格式
    # ================================================================
    title: str = ""                 # 表盘名称（元数据，默认不画在盘上）
    accent_color: Optional[str] = None   # 当前值颜色；None = 用主题色
    needle_color: Optional[str] = None   # 指针颜色；None = 用主题色
    decimals: int = 0               # 小数位数。0=整数，1=一位，2=两位

    # ================================================================
    # ★★ 常用 —— 显示开关
    # ================================================================
    show_numbers: bool = True       # 是否画刻度数字
    show_unit: bool = True          # 是否画单位
    show_value: bool = True         # 是否画当前值大字
    show_zones: bool = True         # 是否画语义弧带
    show_glass: bool = True         # 是否画毛玻璃罩

    # ================================================================
    # ★★ 常用 —— 背景 & 镶嵌
    # ================================================================
    transparent: bool = True        # True=背景透明（镶嵌在父面板上）
    embed_style: str = "inset"      # "inset"=镶嵌 / "raised"=浮起 / "none"=无

    # ================================================================
    # ★ 偶尔 —— 语义弧带
    # ================================================================
    # None   → 默认三档（绿 60% / 黄 80% / 红 100%）
    # []     → 不画弧带
    # [...]  → 自定义，如 [(0, 50, "#00FF00"), (50, 100, "#FF0000")]
    zones: Optional[List[ZoneSpec]] = None

    # ================================================================
    # ★ 偶尔 —— 表盘几何
    # ================================================================
    angle_start: float = -135.0     # 起始角（度）。0°=右，90°=下
    angle_range: float = 270.0      # 总跨度（度）。270=标准表盘

    # ================================================================
    # ★ 极少 —— 风格化开关
    # ================================================================
    frosted_face: bool = True       # 磨砂盘面（极淡径向噪点）
    mono_numbers: bool = True       # 等宽数字（刷新时不抖动）
    needle_shadow: bool = True      # 指针投影（浮起感）
    needle_counterweight: bool = True   # 指针尾部配重
    three_tier_ticks: bool = True       # 三级刻度（主/中/次）
    red_marker: bool = False            # 盘面红线标记（默认关）
    red_marker_value: float = 0.0       # 红线对应的值


# ===========================================================================
# 全局主题广播器 —— 一般不用改
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
        """注册桥接函数：fn(主题名) → 色板字典"""
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
# 【参数区 ②】GAUGE_PRESETS —— 37 个预设（不改代码就能用）
# ===========================================================================
# 每个预设就是一组 GaugeConfig 参数。
# 想加自己的预设？照抄一行改值即可，比如：
#     "torque_nm": dict(unit="N·m", title="TORQUE",
#                       min_value=0, max_value=500,
#                       major_step=100, minor_step=20),
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
    # ---------------- 温度 ----------------
    "temperature_c": dict(unit="°C", title="TEMPERATURE",
                          min_value=-20, max_value=120, major_step=20, minor_step=5,
                          accent_color="#FF9500", needle_color="#FF9500"),
    "temperature_f": dict(unit="°F", title="TEMPERATURE",
                          min_value=0, max_value=250, major_step=50, minor_step=10,
                          accent_color="#FF9500", needle_color="#FF9500"),
    "temperature_k": dict(unit="K", title="TEMPERATURE",
                          min_value=250, max_value=400, major_step=30, minor_step=10,
                          accent_color="#FF9500", needle_color="#FF9500"),
    # ---------------- 转速 ----------------
    "rpm": dict(unit="RPM", title="RPM",
                min_value=0, max_value=8000, major_step=1000, minor_step=200,
                accent_color="#FF9500", needle_color="#FF9500"),
    "rps": dict(unit="RPS", title="RPS",
                min_value=0, max_value=150, major_step=30, minor_step=5,
                accent_color="#FF9500", needle_color="#FF9500"),
    # ---------------- 湿度 ----------------
    "humidity": dict(unit="%RH", title="HUMIDITY",
                     min_value=0, max_value=100, major_step=10, minor_step=2,
                     accent_color="#64D2FF", needle_color="#64D2FF"),
    # ---------------- 电压 ----------------
    "voltage_v":  dict(unit="V", title="VOLTAGE",
                       min_value=0, max_value=30, major_step=5, minor_step=1,
                       accent_color="#FFCC00", needle_color="#FFCC00", decimals=1),
    "voltage_mv": dict(unit="mV", title="VOLTAGE",
                       min_value=0, max_value=1000, major_step=200, minor_step=50,
                       accent_color="#FFCC00", needle_color="#FFCC00"),
    "voltage_kv": dict(unit="kV", title="VOLTAGE",
                       min_value=0, max_value=10, major_step=2, minor_step=0.5,
                       accent_color="#FFCC00", needle_color="#FFCC00", decimals=1),
    # ---------------- 电流 ----------------
    "current_a":  dict(unit="A", title="CURRENT",
                       min_value=0, max_value=20, major_step=5, minor_step=1,
                       accent_color="#FFCC00", needle_color="#FFCC00", decimals=1),
    "current_ma": dict(unit="mA", title="CURRENT",
                       min_value=0, max_value=500, major_step=100, minor_step=20,
                       accent_color="#FFCC00", needle_color="#FFCC00"),
    # ---------------- 功率 ----------------
    "power_w":  dict(unit="W", title="POWER",
                     min_value=0, max_value=5000, major_step=1000, minor_step=200,
                     accent_color="#FF6B00", needle_color="#FF6B00"),
    "power_kw": dict(unit="kW", title="POWER",
                     min_value=0, max_value=5, major_step=1, minor_step=0.2,
                     accent_color="#FF6B00", needle_color="#FF6B00", decimals=1),
    # ---------------- 百分比 / 进度 ----------------
    "percentage": dict(unit="%", title="PERCENT",
                       min_value=0, max_value=100, major_step=10, minor_step=2),
    "progress":   dict(unit="%", title="PROGRESS",
                       min_value=0, max_value=100, major_step=20, minor_step=5,
                       show_zones=False,
                       accent_color="#30D158", needle_color="#30D158"),
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
    # ---------------- 流量 ----------------
    "flow_lpm": dict(unit="L/min", title="FLOW",
                     min_value=0, max_value=100, major_step=20, minor_step=5,
                     accent_color="#64D2FF", needle_color="#64D2FF"),
    "flow_m3h": dict(unit="m³/h", title="FLOW",
                     min_value=0, max_value=50, major_step=10, minor_step=2,
                     accent_color="#64D2FF", needle_color="#64D2FF"),
    # ---------------- 频率 ----------------
    "frequency_hz":  dict(unit="Hz", title="FREQUENCY",
                          min_value=0, max_value=100, major_step=20, minor_step=5),
    "frequency_khz": dict(unit="kHz", title="FREQUENCY",
                          min_value=0, max_value=1000, major_step=200, minor_step=50),
    # ---------------- 光照 / 噪声 ----------------
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
    """通用模拟仪表 —— 单个表盘控件"""

    valueChanged = Signal(float)     # 值变化信号（新值）

    # ==================================================================
    # 【参数区 ③】__init__ —— 创建表盘的入口参数
    # ==================================================================
    # 参数说明（按常用度排序）：
    #
    #   parent              —— 父组件（必传，通常是 QWidget 或布局所属的容器）
    #   width, height       —— 表盘像素尺寸（正方形效果最好）
    #   preset              —— ★★★ 预设名（37 个可选，见 GAUGE_PRESETS）
    #                          只需给这一个，单位/量程/刻度/配色全自动
    #
    #   config              —— GaugeConfig 对象（想完全自定义时用）
    #   palette             —— 色板字典（想手动指定颜色时用）
    #   auto_follow_theme   —— 是否自动跟随全局主题（默认 True）
    #
    #   **kwargs            —— 剩下所有关键字参数会直接传给 GaugeConfig
    #                          比如 min_value=0, max_value=500, unit="kPa"
    #
    # 三种创建方式：
    #   ① 只用预设：  AnalogGauge(parent, 240, 240, preset="temperature_c")
    #   ② 预设+覆盖： AnalogGauge(parent, 240, 240, preset="temperature_c",
    #                              max_value=200)
    #   ③ 完全自定义：AnalogGauge(parent, 240, 240,
    #                              min_value=0, max_value=500,
    #                              unit="kPa", major_step=100, minor_step=20)
    # ==================================================================
    def __init__(
        self,
        parent=None,                    # 父组件
        width: int = 340,               # ★ 宽度（像素）
        height: int = 340,              # ★ 高度（像素）
        preset: Optional[str] = None,   # ★★★ 预设名
        config: Optional[GaugeConfig] = None,  # 完整配置对象
        palette: Optional[dict] = None,        # 手动色板
        auto_follow_theme: bool = True,        # 是否跟随主题
        **kwargs,                              # 其余透传给 GaugeConfig
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

        # ---- 配置装配（priority: kwargs > preset > config 默认值）----
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
        # 时长 600ms，缓动曲线 OutCubic（快起慢停，Apple 风格）
        # 想改动画速度？改 setDuration(毫秒)
        # 想改缓动感觉？改 setEasingCurve(...)
        self._anim = QPropertyAnimation(self, b"displayValue")
        self._anim.setDuration(600)                        # ★ 动画时长
        self._anim.setEasingCurve(QEasingCurve.OutCubic)   # ★ 缓动曲线

        # ---- 订阅主题广播 ----
        if auto_follow_theme:
            GaugeThemeManager.instance().theme_changed.connect(self._on_theme_changed)

        self._setup_fonts()

        # 磨砂噪点种子（固定，避免每帧随机）
        self._noise_seeds = [random.Random(0x5A17 + i) for i in range(4)]

    # ==================================================================
    # 主题跟随
    # ==================================================================
    def _on_theme_changed(self, name: str):
        if not self._auto_follow_theme:
            return
        self.set_palette(GaugeThemeManager.instance().get_palette(name))

    def follow_theme(self, follow: bool = True):
        """开启/关闭全局主题跟随"""
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
    # 色板注入接口
    # ==================================================================
    def set_palette(self, palette: dict):
        """整套替换色板（只给部分键也行，其余走 DEFAULT_PALETTE）"""
        if not palette:
            return
        self._palette = {**DEFAULT_PALETTE, **palette}
        self.update()

    def palette(self) -> dict:
        return dict(self._palette)

    def merge_palette(self, **overrides):
        """只覆盖几个色板键"""
        self._palette.update(overrides)
        self.update()

    # ==================================================================
    # 字体（按优先级从系统里挑）
    # ==================================================================
    # 想换字体？改下面的候选列表。
    # pick() 会从前往后找第一个系统里存在的字体。
    # ==================================================================
    def _setup_fonts(self):
        families = set(QFontDatabase.families())

        def pick(*candidates):
            for name in candidates:
                if name in families:
                    return name
            return candidates[-1]

        # ★ 显示字体（数值大字）—— 按优先级从前往后挑
        self._display_family = pick("SF Pro Display", "Inter", "Helvetica Neue")

        # ★ 正文字体（单位、标签）
        self._text_family    = pick("SF Pro Text",    "Inter", "Helvetica Neue")

        # ★ 等宽字体（刻度数字、等宽模式下的数值）
        self._mono_family = pick(
            "SF Mono", "JetBrains Mono", "Roboto Mono",
            "Consolas", "Menlo", "Courier New",
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
        """
        设置当前值。
            animate=True  → 600ms 缓动动画（默认）
            animate=False → 立即跳转（初始化时用）
        """
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
        """单独换单位"""
        self._config = replace(self._config, unit=unit)
        self.update()

    def set_range(self, min_value: float, max_value: float,
                  major_step: Optional[float] = None,
                  minor_step: Optional[float] = None):
        """运行时改量程（可选同时改刻度）"""
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
        """整套替换配置"""
        self._config = config
        self._value = max(config.min_value, min(config.max_value, self._value))
        self._display_value = self._value
        self.update()

    def config(self) -> GaugeConfig:
        return self._config

    def config_dict(self) -> dict:
        """配置转字典（可序列化）"""
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

    # ==================================================================
    # 几何 / 工具
    # ==================================================================
    def _value_to_angle(self, v: float) -> float:
        """值 → 角度（-135° 到 +135°）"""
        span = self._config.max_value - self._config.min_value
        ratio = 0.0 if span == 0 else (v - self._config.min_value) / span
        ratio = max(0.0, min(1.0, ratio))
        return self._config.angle_start + ratio * self._config.angle_range

    @staticmethod
    def _polar(cx, cy, r, angle_deg):
        """极坐标 → 直角坐标"""
        rad = math.radians(angle_deg)
        return cx + r * math.cos(rad), cy + r * math.sin(rad)

    def _format_value(self, v: float) -> str:
        """按 decimals 格式化数值"""
        d = self._config.decimals
        if d <= 0:
            return f"{int(round(v))}"
        return f"{v:.{d}f}"

    # ==================================================================
    # 绘制入口 —— 下面全是内部绘制，一般不用改
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

        style = self._config.embed_style
        if style == "inset":
            self._draw_inset_ring(p, cx, cy, R)
        elif style == "raised":
            self._draw_raised_shadow(p, cx, cy, R)

        self._draw_bezel(p, cx, cy, R, t)

        bezel_thickness = max(4, R * 0.04)
        face_R = R - bezel_thickness - 1
        self._draw_face(p, cx, cy, face_R, t)

        if self._config.frosted_face:
            self._draw_frosted_face(p, cx, cy, face_R, t)

        if self._config.red_marker:
            self._draw_red_marker(p, cx, cy, face_R, t)

        arc_r_outer = face_R - R * 0.10
        arc_r_inner = arc_r_outer - max(5, R * 0.045)
        if self._config.show_zones:
            self._draw_zones(p, cx, cy, arc_r_outer, arc_r_inner, t)

        tick_outer        = arc_r_inner - R * 0.045
        tick_major_inner  = tick_outer - R * 0.10
        tick_minor_inner  = tick_outer - R * 0.058
        tick_medium_inner = tick_outer - R * 0.080
        self._draw_ticks(p, cx, cy,
                         tick_outer,
                         tick_major_inner,
                         tick_medium_inner,
                         tick_minor_inner, t)

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

    # ---------- 下面所有 _draw_xxx 都是内部绘制实现，一般不用改 ----------

    def _draw_frosted_face(self, p, cx, cy, R, t):
        base = QColor(t["face_outer"])
        for ring_i, seed in enumerate(self._noise_seeds):
            r = R * (0.35 + ring_i * 0.16)
            n_segments = 32 + ring_i * 8
            rng = seed
            pen = QPen(QColor(base.red(), base.green(), base.blue(),
                              max(3, 8 - ring_i)))
            pen.setWidthF(max(0.4, R * 0.004))
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            seg_arc = 360.0 / n_segments
            for i in range(n_segments):
                if rng.random() < 0.45:
                    continue
                start = i * seg_arc + rng.uniform(-seg_arc * 0.3, seg_arc * 0.3)
                span = seg_arc * rng.uniform(0.25, 0.75)
                rect = QRectF(cx - r, cy - r, r * 2, r * 2)
                path = QPainterPath()
                path.arcMoveTo(rect, start)
                path.arcTo(rect, start, span)
                p.drawPath(path)

        g = QRadialGradient(QPointF(cx - R * 0.25, cy - R * 0.30), R * 1.1)
        g.setColorAt(0.0, QColor(255, 255, 255, 18))
        g.setColorAt(0.6, QColor(255, 255, 255, 4))
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

    def _draw_raised_shadow(self, p, cx, cy, R):
        g = QRadialGradient(QPointF(cx, cy + R * 0.06), R * 1.20)
        g.setColorAt(0.00, QColor(0, 0, 0, 70))
        g.setColorAt(0.80, QColor(0, 0, 0, 40))
        g.setColorAt(0.94, QColor(0, 0, 0, 10))
        g.setColorAt(1.00, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy + R * 0.06), R * 1.20, R * 1.20)

    def _draw_bezel(self, p, cx, cy, R, t):
        g = QRadialGradient(QPointF(cx - R * 0.38, cy - R * 0.38), R * 1.55)
        g.setColorAt(0.00, QColor(t["bezel_hi"]))
        g.setColorAt(0.35, QColor(t["bezel_light"]))
        g.setColorAt(0.72, QColor(t["bezel_dark"]))
        g.setColorAt(1.00, QColor(t["bezel_lo"]))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), R, R)

    def _draw_face(self, p, cx, cy, R, t):
        g = QRadialGradient(QPointF(cx, cy), R)
        g.setColorAt(0.00, QColor(t["face_inner"]))
        g.setColorAt(0.72, QColor(t["face_mid"]))
        g.setColorAt(1.00, QColor(t["face_outer"]))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), R, R)

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
            font.setWeight(QFont.Weight.Normal)
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

    def _draw_value(self, p, cx, cy, R, t):
        val_text = self._format_value(self._display_value)
        if self._config.mono_numbers:
            f_val = QFont(self._mono_family)
            f_val.setPixelSize(max(16, int(R * 0.20)))
            f_val.setWeight(QFont.Weight.DemiBold)
        else:
            f_val = QFont(self._display_family)
            f_val.setPixelSize(max(16, int(R * 0.22)))
            f_val.setWeight(QFont.Weight.Light)
        p.setPen(QPen(QColor(t["value_text"])))
        p.setFont(f_val)
        if self._config.show_unit and self._config.unit:
            fm = p.fontMetrics()
            val_w = fm.horizontalAdvance(val_text)
            f_unit = QFont(self._text_family)
            f_unit.setPixelSize(max(9, int(R * 0.075)))
            f_unit.setWeight(QFont.Weight.Medium)
            p.setFont(f_unit)
            fm_unit = p.fontMetrics()
            unit_w = fm_unit.horizontalAdvance(self._config.unit)
            unit_h = fm_unit.height()
            total_w = val_w + max(4, R * 0.02) + unit_w
            base_x = cx - total_w / 2
            base_y = cy + R * 0.10
            p.setPen(QPen(QColor(t["value_text"])))
            p.setFont(f_val)
            fm_val = p.fontMetrics()
            p.drawText(QPointF(base_x, base_y + fm_val.ascent()), val_text)
            p.setPen(QPen(QColor(t["label"])))
            p.setFont(f_unit)
            unit_x = base_x + val_w + max(4, R * 0.02)
            unit_y = base_y + fm_val.ascent() + (fm_val.height() - unit_h) * 0.55
            p.drawText(QPointF(unit_x, unit_y), self._config.unit)
        else:
            p.drawText(
                QRectF(cx - R * 0.7, cy + R * 0.06, R * 1.4, R * 0.30),
                Qt.AlignCenter, val_text,
            )

    def _draw_needle(self, p, cx, cy, length, R, t):
        angle = self._value_to_angle(self._display_value)
        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        perp = math.radians(angle + 90)
        cos_p, sin_p = math.cos(perp), math.sin(perp)
        s = R / 150.0
        tail_len = (14 if self._config.needle_counterweight else 8) * s
        tail_w   = 4.0 * s
        shoulder = 4.5 * s

        def pt(r, w):
            return QPointF(cx + r * cos_a + w * cos_p,
                           cy + r * sin_a + w * sin_p)

        if self._config.needle_shadow:
            shadow_off_x = 1.6 * s
            shadow_off_y = 2.2 * s
            shadow_poly = QPolygonF([
                QPointF(cx + (-tail_len) * cos_a + 0 * cos_p + shadow_off_x,
                        cy + (-tail_len) * sin_a + 0 * sin_p + shadow_off_y),
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
            p.setBrush(QBrush(QColor(0, 0, 0, 50)))
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

        if self._config.needle_counterweight:
            cw_r = 2.6 * s
            cw_x = cx - (tail_len - 2 * s) * cos_a
            cw_y = cy - (tail_len - 2 * s) * sin_a
            p.setBrush(QBrush(QColor(t["needle"])))
            p.drawEllipse(QPointF(cw_x, cw_y), cw_r, cw_r)

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