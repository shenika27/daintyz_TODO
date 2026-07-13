from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
)

from domain import policies


class DeadlineDateDialog(QDialog):
    def __init__(self, initial_iso: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("마감일 설정")
        self.setModal(True)

        try:
            initial = date.fromisoformat(initial_iso)
        except ValueError:
            initial = date.today()

        outer = QVBoxLayout(self)
        form = QFormLayout()

        self.year = QSpinBox()
        self.year.setRange(1, 9999)
        self.year.setValue(initial.year)
        self.year.setSuffix("년")

        self.month = QSpinBox()
        self.month.setRange(1, 12)
        self.month.setValue(initial.month)
        self.month.setSuffix("월")

        self.day = QSpinBox()
        self.day.setRange(1, 31)
        self.day.setValue(initial.day)
        self.day.setSuffix("일")

        form.addRow("연", self.year)
        form.addRow("월", self.month)
        form.addRow("일", self.day)
        outer.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.year.valueChanged.connect(self._sync_day_max)
        self.month.valueChanged.connect(self._sync_day_max)
        self._sync_day_max()

    def selected_iso(self) -> str:
        return date(self.year.value(), self.month.value(), self.day.value()).isoformat()

    def _sync_day_max(self) -> None:
        max_day = policies.monthly_target_day(self.year.value(), self.month.value(), 31)
        self.day.setMaximum(max_day)
