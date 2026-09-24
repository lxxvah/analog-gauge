# test_gauge.py
# ============================================================================
# 机械表模块（analog_gauge.py）完整使用示例
# ============================================================================
#
# 【模块能力】
#   · 37 个预设（压力/温度/转速/湿度/电压/电流/功率/百分比/油量/速度/流量/频率/光照）
#   · 5 个主题（light / dark / nord / solarized_light / dracula）
#   · 3 种风格（精密仪表 / 经典 Apple / 极简）
#   · 平滑指针动画 · 透明背景 · 镶嵌效果 · valueChanged 信号
#
# 【核心三步 —— 使用本模块只需记住这三句】
#
#   1. 注册色板桥接（应用启动时一次）
#        ThemeManager.instance().set_palette_provider(
#            lambda name: palette_from_theme(Theme(name))
#        )
#
#   2. 创建表盘（选预设，可选覆盖量程/单位）
#        g = AnalogGauge(parent, width=240, height=240, preset="temperature_c")
#
#   3. 切主题（一行广播，所有表盘自动跟）
#        ThemeManager.instance().set_theme("nord")
#
# 【本示例演示的用法】
#   ✓ 从预设创建 6 个表盘
#   ✓ 动态改预设（下拉框）
#   ✓ 动态改风格（3 种风格一键切）
#   ✓ 动态改主题（5 个主题一键切）
#   ✓ 程序设值 + 指针平滑动画
#   ✓ 订阅 valueChanged 信号（状态栏实时显示）
#   ✓ QTimer 模拟实时传感器数据刷新
#   ✓ 从表盘读回单位/量程做显示
#
# 【快捷键】
#   Ctrl+T  循环切主题
#   Ctrl+S  循环切风格
#   Ctrl+L  开/关实时数据模拟
#   Ctrl+R  随机值
#   Ctrl+0  归零
#   Ctrl+M  拉满
#
# ============================================================================

import sys
import random
from datetime import datetime
from dataclasses import replace

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QFrame, QLabel, QPushButton, QComboBox, QSizePolicy,
)

# ----------------------------------------------------------------------------
# 【导入模块】—— 只用这 5 个名字
# ----------------------------------------------------------------------------
from theme import Theme, list_themes, THEME_CYCLE
from analog_gauge import (
    AnalogGauge,          # ★ 仪表控件本体
    ThemeManager,         # ★ 全局主题广播器
    GAUGE_PRESETS,        # ★ 37 个预设字典
    GaugeConfig,          # ★ 配置数据类
    palette_from_theme,   # ★ 桥接：主题对象 → 色板字典
)


# ============================================================================
# 【桥接函数】—— 把 theme.py 的 Theme 对象转成仪表色板
# ============================================================================
# 用途：ThemeManager 不知道 theme.py 的存在，只认"主题名 → 色板"这个函数
# 你只要把这个函数注册进去，仪表就能自动跟随 theme.py 的颜色
# ============================================================================
def _palette_provider(theme_name: str) -> dict:
    return palette_from_theme(Theme(theme_name))


# ============================================================================
# 【预设分组】—— 给下拉框分组显示，让用户方便选
# ============================================================================
# 每一项：(分组名, [(显示标签, preset 键), ...])
# preset 键必须存在于 analog_gauge.GAUGE_PRESETS
# ============================================================================
PRESET_GROUPS = [
    ("压力",   [("mmHg", "pressure_mmhg"), ("kPa", "pressure_kpa"),
                ("PSI", "pressure_psi"), ("bar", "pressure_bar"),
                ("MPa", "pressure_mpa")]),
    ("温度",   [("°C", "temperature_c"), ("°F", "temperature_f"),
                ("K", "temperature_k")]),
    ("转速",   [("RPM", "rpm"), ("RPS", "rps")]),
    ("湿度",   [("%RH", "humidity")]),
    ("电压",   [("V", "voltage_v"), ("mV", "voltage_mv"), ("kV", "voltage_kv")]),
    ("电流",   [("A", "current_a"), ("mA", "current_ma")]),
    ("功率",   [("W", "power_w"), ("kW", "power_kw")]),
    ("百分比", [("PERCENT", "percentage"), ("PROGRESS", "progress")]),
    ("油量",   [("FUEL %", "fuel"), ("FUEL L", "fuel_liter"),
                ("BATTERY", "battery")]),
    ("速度",   [("km/h", "speed_kph"), ("mph", "speed_mph"), ("m/s", "speed_ms")]),
    ("流量",   [("L/min", "flow_lpm"), ("m³/h", "flow_m3h")]),
    ("频率",   [("Hz", "frequency_hz"), ("kHz", "frequency_khz")]),
    ("光照",   [("lx", "lux"), ("dB", "noise_db")]),
]


# ============================================================================
# 【三种风格】—— 每个风格就是一组 GaugeConfig 开关
# ============================================================================
# 切换风格时通过 replace(config, **style_dict) 只改这些开关
# 不影响预设、量程、单位、主题
# ============================================================================
STYLE_PRESETS = {
    "精密仪表": dict(
        frosted_face=True,
        mono_numbers=True,
        needle_shadow=True,
        needle_counterweight=True,
        three_tier_ticks=True,
        show_zones=True,
        show_glass=True,
    ),
    "经典 Apple": dict(
        frosted_face=False,
        mono_numbers=False,
        needle_shadow=False,
        needle_counterweight=False,
        three_tier_ticks=False,
        show_zones=True,
        show_glass=True,
    ),
    "极简": dict(
        frosted_face=False,
        mono_numbers=True,
        needle_shadow=False,
        needle_counterweight=False,
        three_tier_ticks=False,
        show_zones=False,
        show_glass=False,
    ),
}

STYLE_ORDER = ["精密仪表", "经典 Apple", "极简"]


# ============================================================================
# 【表盘卡片】—— 表盘 + 预设选择器 组合成一张卡片
# ============================================================================
class GaugeCard(QFrame):
    """
    一个卡片 = 一个表盘 + 一个预设下拉框

    ★ 使用要点：
        · 通过 AnalogGauge(...) 创建表盘，只需指定 preset
        · 通过 gauge.set_value(v) 设值（自动动画）
        · 通过 replace(gauge.config(), ...) + gauge.set_config(...) 改配置
    """

    def __init__(self, default_preset="pressure_mmhg", parent=None):
        super().__init__(parent)
        self.setObjectName("gauge_card")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        # -------------------------------------------------------------------
        # ★ 步骤 1：创建表盘
        # -------------------------------------------------------------------
        # AnalogGauge(parent, width, height, preset=...)
        #   parent   父组件
        #   width    宽度（像素）
        #   height   高度（像素）
        #   preset   预设名，一行搞定单位/量程/刻度/配色
        # -------------------------------------------------------------------
        self.gauge = AnalogGauge(
            self,
            width=230,
            height=230,
            preset=default_preset,     # ← 想画什么表，改这一个参数
        )
        layout.addWidget(self.gauge, alignment=Qt.AlignCenter)

        # -------------------------------------------------------------------
        # 预设选择器 —— 让用户随时切到别的单位
        # -------------------------------------------------------------------
        self.combo = QComboBox()
        self.combo.setFixedWidth(230)
        self.combo.setFixedHeight(32)
        self.combo.setCursor(Qt.PointingHandCursor)

        idx = 0
        for group_name, items in PRESET_GROUPS:
            for label, key in items:
                self.combo.addItem(f"{group_name} · {label}", key)
                if key == default_preset:
                    idx = self.combo.count() - 1
        self.combo.setCurrentIndex(idx)

        self.combo.currentIndexChanged.connect(self._on_preset_changed)
        layout.addWidget(self.combo, alignment=Qt.AlignCenter)

    # ------------------------------------------------------------------
    # 切预设 —— 从 GAUGE_PRESETS 生成新配置，保留风格开关
    # ------------------------------------------------------------------
    def _on_preset_changed(self, _idx):
        preset = self.combo.currentData()
        if not preset or preset not in GAUGE_PRESETS:
            return

        # ★ 从预设生成配置
        base = GaugeConfig(**GAUGE_PRESETS[preset])

        # ★ 读取当前配置，保留风格开关 + 显示开关
        current = self.gauge.config()

        # ★ 合并：预设决定量程/单位/配色；当前配置决定风格/透明/镶嵌
        new_config = replace(
            base,
            transparent=current.transparent,
            embed_style=current.embed_style,
            show_numbers=current.show_numbers,
            show_unit=current.show_unit,
            show_value=current.show_value,
            show_zones=current.show_zones,
            show_glass=current.show_glass,
            frosted_face=current.frosted_face,
            mono_numbers=current.mono_numbers,
            needle_shadow=current.needle_shadow,
            needle_counterweight=current.needle_counterweight,
            three_tier_ticks=current.three_tier_ticks,
            red_marker=current.red_marker,
            red_marker_value=current.red_marker_value,
        )

        # ★ 应用到表盘
        self.gauge.set_config(new_config)

        # ★ 指针滑到量程 55% 位置
        mid = new_config.min_value + (new_config.max_value - new_config.min_value) * 0.55
        self.gauge.set_value(mid, animate=True)

    # ------------------------------------------------------------------
    # 应用风格 —— 只改风格开关，不动量程/单位/预设
    # ------------------------------------------------------------------
    def apply_style(self, style_dict: dict):
        cfg = self.gauge.config()
        new_cfg = replace(cfg, **style_dict)
        self.gauge.set_config(new_cfg)


# ============================================================================
# 【主窗口】
# ============================================================================
class GaugeTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Analog Gauge Test · 完整功能演示")
        self.resize(1080, 760)

        # ---- 当前主题 / 风格索引 ----
        self._theme_index = 0
        self._style_index = 0
        self.theme = Theme(THEME_CYCLE[self._theme_index])

        # ---- 卡片名称（用于状态栏显示）----
        self._card_names = ["压力", "温度", "转速", "湿度", "电压", "油量"]

        # ====================================================================
        # ★ 步骤 1：注册色板桥接
        # ====================================================================
        # 必须在创建任何表盘之前调用一次。
        # 之后所有 auto_follow_theme=True 的表盘都会自动拉取主题色板。
        # ====================================================================
        ThemeManager.instance().set_palette_provider(_palette_provider)

        # 设置初始主题（也会触发一次广播）
        ThemeManager.instance().set_theme(self.theme.mode)

        # ---- 主体布局 ----
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(14)

        # ---- 顶部标题 ----
        header = QHBoxLayout()
        header.setSpacing(12)

        self.title = QLabel("Analog Gauge Module Test")
        self.title.setObjectName("title")

        self.hint = QLabel(
            "Ctrl+T 主题 · Ctrl+S 风格 · Ctrl+L 实时 · "
            "Ctrl+R 随机 · Ctrl+0 归零 · Ctrl+M 拉满"
        )
        self.hint.setObjectName("hint")

        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.hint)
        root.addLayout(header)

        # ====================================================================
        # ★ 步骤 2：创建 6 个表盘卡片
        # ====================================================================
        grid = QGridLayout()
        grid.setSpacing(16)

        self.cards = [
            GaugeCard("pressure_mmhg", self),    # 压力表 0-300 mmHg
            GaugeCard("temperature_c", self),    # 温度表 -20-120 °C
            GaugeCard("rpm",           self),    # 转速表 0-8000 RPM
            GaugeCard("humidity",      self),    # 湿度表 0-100 %RH
            GaugeCard("voltage_v",     self),    # 电压表 0-30 V
            GaugeCard("fuel",          self),    # 油量表 0-100 %
        ]

        for i, card in enumerate(self.cards):
            grid.addWidget(card, i // 3, i % 3)

        root.addLayout(grid)

        # ====================================================================
        # ★ 订阅 valueChanged —— 演示表盘向外"报告"值变化
        # ====================================================================
        for i, card in enumerate(self.cards):
            card.gauge.valueChanged.connect(
                lambda v, idx=i, c=card: self._on_gauge_value_changed(idx, c, v)
            )

        # ---- 底部控制栏 ----
        bar = QHBoxLayout()
        bar.setSpacing(8)

        # 数值操作按钮
        self.btn_random = QPushButton("随机值")
        self.btn_zero   = QPushButton("归零")
        self.btn_max    = QPushButton("拉满")
        for b in (self.btn_random, self.btn_zero, self.btn_max):
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(34)
            b.clicked.connect(self._on_btn_clicked)
            bar.addWidget(b)

        # ★ 实时数据开关（可勾选按钮）
        self.btn_live = QPushButton("▶ 实时数据")
        self.btn_live.setCursor(Qt.PointingHandCursor)
        self.btn_live.setFixedHeight(34)
        self.btn_live.setCheckable(True)
        self.btn_live.setObjectName("btn_live")
        self.btn_live.toggled.connect(self._toggle_live)
        bar.addWidget(self.btn_live)

        bar.addStretch(1)

        # ---- 风格下拉框 ----
        self.style_label = QLabel("风格:")
        bar.addWidget(self.style_label)

        self.style_combo = QComboBox()
        for name in STYLE_ORDER:
            self.style_combo.addItem(name, name)
        self.style_combo.setCurrentIndex(self._style_index)
        self.style_combo.setFixedWidth(130)
        self.style_combo.setFixedHeight(34)
        self.style_combo.setCursor(Qt.PointingHandCursor)
        self.style_combo.currentIndexChanged.connect(self._on_style_combo)
        bar.addWidget(self.style_combo)

        bar.addSpacing(10)

        # ---- 主题下拉框 ----
        self.theme_label = QLabel("主题:")
        bar.addWidget(self.theme_label)

        self.theme_combo = QComboBox()
        for mode in list_themes():
            self.theme_combo.addItem(mode.replace('_', ' ').title(), mode)
        self.theme_combo.setCurrentIndex(self._theme_index)
        self.theme_combo.setFixedWidth(170)
        self.theme_combo.setFixedHeight(34)
        self.theme_combo.setCursor(Qt.PointingHandCursor)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_combo)
        bar.addWidget(self.theme_combo)

        root.addLayout(bar)

        # ====================================================================
        # ★ 状态栏 —— 实时显示最新收到的事件
        # ====================================================================
        self.status = QLabel("就绪 · 等待数据")
        self.status.setObjectName("status")
        self.status.setFixedHeight(28)
        root.addWidget(self.status)

        # ---- 快捷键 ----
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self._cycle_theme)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._cycle_style)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._toggle_live_shortcut)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._set_random)
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self._set_zero)
        QShortcut(QKeySequence("Ctrl+M"), self, activated=self._set_max)

        # ====================================================================
        # ★ 步骤 3：给表盘设初值
        # ====================================================================
        initial_values = [180, 72, 4200, 45, 12.6, 62]
        for card, v in zip(self.cards, initial_values):
            card.gauge.set_value(v, animate=False)

        # ---- 应用初始主题 + 风格 ----
        self._apply_theme()
        self._apply_style(self._style_index)

        # ====================================================================
        # ★ QTimer 实时数据模拟 —— 演示传感器驱动的场景
        # ====================================================================
        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._live_tick)

    # ======================================================================
    # 【valueChanged 信号处理】—— 演示表盘向外报告值变化
    # ======================================================================
    def _on_gauge_value_changed(self, idx: int, card: GaugeCard, value: float):
        """
        每当一个表盘的值发生变化，都会回调这里。
        实际项目中可以：
            · 写数据库
            · 发消息到 MQTT / WebSocket
            · 触发告警判断
            · 更新日志
        这里只在状态栏显示。
        """
        g = card.gauge
        unit = g.unit or ""
        name = self._card_names[idx]
        ts = datetime.now().strftime("%H:%M:%S")

        # 格式化：整数省小数点
        if abs(value - round(value)) < 0.05:
            v_str = f"{int(round(value))}"
        else:
            v_str = f"{value:.1f}"

        self.status.setText(
            f"● [{name}] 最新值 {v_str} {unit}   ·   {ts}"
        )

    # ======================================================================
    # 【实时数据】—— QTimer 模拟传感器数据
    # ======================================================================
    def _toggle_live_shortcut(self):
        """Ctrl+L —— 切换实时数据开关"""
        self.btn_live.setChecked(not self.btn_live.isChecked())

    def _toggle_live(self, checked: bool):
        """按钮勾选状态变化时调用"""
        if checked:
            self._live_timer.start(800)         # 每 800ms 一刷
            self.btn_live.setText("⏸ 实时数据")
            self.status.setText("● 实时数据已开启（每 800ms 刷新一次）")
        else:
            self._live_timer.stop()
            self.btn_live.setText("▶ 实时数据")
            self.status.setText("● 实时数据已关闭")

    def _live_tick(self):
        """每个时间片围绕当前值小幅波动 —— 比完全随机更像真实传感器"""
        for card in self.cards:
            g = card.gauge
            cur = g.get_value()
            span = g.max_value - g.min_value
            # 每次最多 ±6% 量程，模拟平滑波动
            delta = random.uniform(-span * 0.06, span * 0.06)
            new_val = max(g.min_value, min(g.max_value, cur + delta))
            g.set_value(new_val)

    # ======================================================================
    # 【主题操作】
    # ======================================================================
    def _cycle_theme(self):
        """Ctrl+T —— 循环切主题"""
        idx = (self._theme_index + 1) % len(THEME_CYCLE)
        self._theme_index = idx
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.blockSignals(False)
        self._apply_theme()

    def _on_theme_combo(self, idx: int):
        self._theme_index = idx
        self._apply_theme()

    def _apply_theme(self):
        """
        ★ 核心：一行广播主题，所有表盘自动刷新色板

        链路：
            set_theme("nord")
              ↓ 发射 theme_changed 信号
            每个 AnalogGauge._on_theme_changed()
              ↓ 调 ThemeManager.get_palette()
              ↓ 调 _palette_provider("nord")
              ↓ 调 palette_from_theme(Theme("nord"))
              ↓ set_palette(...) → update() → 重绘
        """
        mode = THEME_CYCLE[self._theme_index]
        self.theme = Theme(mode)

        # ★★★ 这一行就是"切主题"的全部 ★★★
        ThemeManager.instance().set_theme(mode)

        # 外壳 QSS（窗口/卡片/按钮/状态栏）单独刷
        self._apply_shell_qss()

    def _apply_shell_qss(self):
        """外壳样式（窗口背景、卡片、按钮、下拉框、状态栏）"""
        t = self.theme
        self.setStyleSheet(f"""
            QWidget#central {{
                background-color: {t.bg};
            }}
            QMainWindow {{
                background-color: {t.bg};
            }}
            QLabel#title {{
                color: {t.fg};
                font-family: 'Microsoft YaHei UI', 'Inter', sans-serif;
                font-size: 20px;
                font-weight: 600;
                background: transparent;
            }}
            QLabel#hint {{
                color: {t.fg_mute};
                font-family: 'Microsoft YaHei UI', 'Inter', sans-serif;
                font-size: 12px;
                background: transparent;
            }}
            QLabel#status {{
                color: {t.fg_mid};
                background-color: {t.card_bg};
                border: 1px solid {t.hairline};
                border-radius: 8px;
                padding: 4px 12px;
                font-family: 'Consolas', 'SF Mono', monospace;
                font-size: 12px;
            }}
            QLabel {{
                color: {t.fg_mid};
                font-family: 'Microsoft YaHei UI', 'Inter', sans-serif;
                font-size: 13px;
                background: transparent;
            }}
            QFrame#gauge_card {{
                background-color: {t.card_bg};
                border: 1px solid {t.hairline};
                border-radius: 16px;
            }}
            QPushButton {{
                background-color: {t.neutral_bg};
                color: {t.neutral_fg};
                border: none;
                border-radius: 8px;
                padding: 6px 14px;
                font-family: 'Microsoft YaHei UI', 'Inter', sans-serif;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {t.neutral_hover};
            }}
            QPushButton:pressed {{
                background-color: {t.primary};
                color: #ffffff;
            }}
            QPushButton#btn_live:checked {{
                background-color: {t.primary};
                color: #ffffff;
            }}
            QComboBox {{
                background-color: {t.input_bg};
                color: {t.input_fg};
                border: 1px solid {t.hairline};
                border-radius: 8px;
                padding: 6px 12px;
                font-family: 'Microsoft YaHei UI', 'Inter', sans-serif;
                font-size: 12px;
            }}
            QComboBox:hover {{
                border: 1px solid {t.primary};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {t.input_bg};
                color: {t.fg};
                border: 1px solid {t.hairline};
                border-radius: 8px;
                selection-background-color: {t.primary};
                selection-color: #ffffff;
                outline: none;
                padding: 4px;
            }}
        """)

    # ======================================================================
    # 【风格操作】
    # ======================================================================
    def _cycle_style(self):
        """Ctrl+S —— 循环切风格"""
        idx = (self._style_index + 1) % len(STYLE_ORDER)
        self._style_index = idx
        self.style_combo.blockSignals(True)
        self.style_combo.setCurrentIndex(idx)
        self.style_combo.blockSignals(False)
        self._apply_style(idx)

    def _on_style_combo(self, idx: int):
        self._style_index = idx
        self._apply_style(idx)

    def _apply_style(self, idx: int):
        """
        ★ 风格切换：通过 replace(config, **style_dict) 只改风格开关
        不影响预设、量程、单位、主题
        """
        name = STYLE_ORDER[idx]
        style_dict = STYLE_PRESETS[name]
        for card in self.cards:
            card.apply_style(style_dict)

    # ======================================================================
    # 【数值操作】
    # ======================================================================
    def _on_btn_clicked(self):
        sender = self.sender()
        if sender is self.btn_random:
            self._set_random()
        elif sender is self.btn_zero:
            self._set_zero()
        elif sender is self.btn_max:
            self._set_max()

    def _set_random(self):
        """在量程内随机取值"""
        for card in self.cards:
            g = card.gauge
            g.set_value(random.uniform(g.min_value, g.max_value))

    def _set_zero(self):
        """归零到最小值"""
        for card in self.cards:
            card.gauge.set_value(card.gauge.min_value)

    def _set_max(self):
        """拉满到最大值"""
        for card in self.cards:
            card.gauge.set_value(card.gauge.max_value)


# ============================================================================
# 【入口】
# ============================================================================
def main():
    app = QApplication(sys.argv)
    win = GaugeTestWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()