# test_gauge.py
# PySide6 —— 万能模拟仪表 Demo · 可在 UI 里选择任意预设
import sys
import random
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QLabel,
)

from analog_gauge import (
    AnalogGauge, ThemeManager, GAUGE_PRESETS, GaugeConfig,
)


# ===========================================================================
# 预设分组 —— (分组名, [(显示标签, preset 键), ...])
# ===========================================================================
PRESET_GROUPS = [
    ("压力", [("mmHg", "pressure_mmhg"),
              ("kPa",  "pressure_kpa"),
              ("PSI",  "pressure_psi"),
              ("bar",  "pressure_bar"),
              ("MPa",  "pressure_mpa")]),
    ("温度", [("°C", "temperature_c"),
              ("°F", "temperature_f"),
              ("K",  "temperature_k")]),
    ("转速", [("RPM", "rpm"),
              ("RPS", "rps")]),
    ("湿度", [("%RH", "humidity")]),
    ("电压", [("V",  "voltage_v"),
              ("mV", "voltage_mv"),
              ("kV", "voltage_kv")]),
    ("电流", [("A",  "current_a"),
              ("mA", "current_ma")]),
    ("功率", [("W",  "power_w"),
              ("kW", "power_kw")]),
    ("百分比", [("PERCENT",  "percentage"),
                ("PROGRESS", "progress")]),
    ("油量电池", [("FUEL %", "fuel"),
                  ("FUEL L", "fuel_liter"),
                  ("BATTERY", "battery")]),
    ("速度", [("km/h", "speed_kph"),
              ("mph",  "speed_mph"),
              ("m/s",  "speed_ms")]),
    ("流量", [("L/min", "flow_lpm"),
              ("m³/h",  "flow_m3h")]),
    ("频率", [("Hz",  "frequency_hz"),
              ("kHz", "frequency_khz")]),
    ("光照噪声", [("lx", "lux"),
                  ("dB", "noise_db")]),
]


# ===========================================================================
# 一个表盘 + 预设选择器
# ===========================================================================
class GaugeColumn(QWidget):
    """一列 —— 表盘 + 它的预设下拉框"""

    def __init__(self, default_preset="pressure_mmhg", parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ---- 表盘 ----
        self.gauge = AnalogGauge(self, width=250, height=250,
                                 preset=default_preset)
        layout.addWidget(self.gauge, alignment=Qt.AlignCenter)

        # ---- 预设选择器 ----
        self.combo = QComboBox()
        self.combo.setFixedWidth(250)
        self.combo.setFixedHeight(34)
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
    def _on_preset_changed(self, _idx):
        preset = self.combo.currentData()
        if not preset or preset not in GAUGE_PRESETS:
            return

        # 1. 从预设生成基础 config
        base = GaugeConfig(**GAUGE_PRESETS[preset])

        # 2. 保留当前表盘的显示开关 / 透明设置 / 主题（跟随状态）
        current = self.gauge.config()
        new_config = replace(
            base,
            theme=current.theme,
            transparent=current.transparent,
            embed_style=current.embed_style,
            show_numbers=current.show_numbers,
            show_unit=current.show_unit,
            show_value=current.show_value,
            show_zones=current.show_zones,
            show_glass=current.show_glass,
        )
        self.gauge.set_config(new_config)

        # 3. 重设到量程的 55% 位置 —— 换预设后指针位置合理
        mid = new_config.min_value + (new_config.max_value - new_config.min_value) * 0.55
        self.gauge.set_value(mid, animate=True)

    def preset(self) -> str:
        return self.combo.currentData()


# ===========================================================================
# Demo 主窗口
# ===========================================================================
class GaugeDemo(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Universal Analog Gauge — Preset Selector")
        self.resize(920, 480)

        self._bg_light = "#F5F5F7"
        self._bg_dark  = "#1C1C1E"

        # ---------------- 主布局 ----------------
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(14)

        # ---------------- 标题 ----------------
        self.title = QLabel("Universal Analog Gauges")
        self.title.setAlignment(Qt.AlignCenter)
        root.addWidget(self.title)

        # ---------------- 三列表盘 ----------------
        row = QHBoxLayout()
        row.setSpacing(20)

        self.columns = [
            GaugeColumn("pressure_mmhg", self),
            GaugeColumn("temperature_c", self),
            GaugeColumn("rpm",           self),
        ]
        for col in self.columns:
            row.addWidget(col)

        root.addLayout(row)
        root.addStretch(1)

        # ---------------- 控制栏 ----------------
        bar = QHBoxLayout()
        bar.setSpacing(8)

        def make_btn(text, cb, width=96):
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(36)
            b.setFixedWidth(width)
            b.clicked.connect(cb)
            return b

        bar.addWidget(make_btn("Random", self._set_random))
        bar.addWidget(make_btn("Zero",   self._set_zero))
        bar.addWidget(make_btn("Max",    self._set_max))

        bar.addStretch(1)

        self.theme_label = QLabel("Theme:")
        bar.addWidget(self.theme_label)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["light", "dark"])
        self.theme_combo.setFixedWidth(110)
        self.theme_combo.setFixedHeight(34)
        self.theme_combo.setCursor(Qt.PointingHandCursor)
        self.theme_combo.currentTextChanged.connect(self._on_theme_change)
        bar.addWidget(self.theme_combo)

        root.addLayout(bar)

        # ---------------- 初始值 ----------------
        for col in self.columns:
            g = col.gauge
            mid = g.min_value + (g.max_value - g.min_value) * 0.55
            g.set_value(mid, animate=False)

        self._apply_window_theme("light")

    # ------------------------------------------------------------------
    # 控制按钮
    # ------------------------------------------------------------------
    def _set_random(self):
        for col in self.columns:
            g = col.gauge
            g.set_value(random.uniform(g.min_value, g.max_value))

    def _set_zero(self):
        for col in self.columns:
            col.gauge.set_value(col.gauge.min_value)

    def _set_max(self):
        for col in self.columns:
            col.gauge.set_value(col.gauge.max_value)

    # ------------------------------------------------------------------
    # 主题
    # ------------------------------------------------------------------
    def _on_theme_change(self, theme: str):
        # ★ 一行让所有跟随主题的表盘切过去
        ThemeManager.instance().set_theme(theme)
        self._apply_window_theme(theme)

    def _apply_window_theme(self, theme: str):
        dark  = (theme == "dark")
        bg       = self._bg_dark  if dark else self._bg_light
        fg       = "#E5E5EA"      if dark else "#1D1D1F"
        muted    = "#98989D"      if dark else "#6E6E73"
        border   = "#48484A"      if dark else "#D2D2D7"
        input_bg = "#2C2C2E"      if dark else "#FFFFFF"

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
            }}
            QLabel {{
                color: {muted};
                background: transparent;
                font-family: 'SF Pro Text', 'Inter', sans-serif;
                font-size: 13px;
            }}
            QPushButton {{
                background-color: #0066CC;
                color: #FFFFFF;
                border: none;
                border-radius: 18px;
                font-family: 'SF Pro Text', 'Inter', sans-serif;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:pressed {{ background-color: #0055AA; }}
            QPushButton:hover   {{ background-color: #0071E3; }}

            QComboBox {{
                background-color: {input_bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 6px 12px;
                font-family: 'SF Pro Text', 'Inter', sans-serif;
                font-size: 13px;
            }}
            QComboBox:hover {{
                border: 1px solid #0066CC;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 22px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {input_bg};
                color: {fg};
                selection-background-color: #0066CC;
                selection-color: #FFFFFF;
                border: 1px solid {border};
                outline: none;
                padding: 4px;
            }}
        """)

        # 标题单独样式
        self.title.setStyleSheet(
            f"color: {fg}; background: transparent;"
            "font-family: 'SF Pro Display', 'Inter', sans-serif;"
            "font-size: 22px; font-weight: 600;"
        )


# ===========================================================================
def main():
    app = QApplication(sys.argv)
    win = GaugeDemo()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()