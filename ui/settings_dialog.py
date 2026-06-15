"""ui/settings_dialog.py — 설정 화면.

이미지 경로 · 미완료/월간 정책 · 자동시작 · 백업(내보내기/복원) · 반복 할일 관리.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core import feature_flags
from domain import policies

log = logging.getLogger(__name__)
_WD = ["일", "월", "화", "수", "목", "금", "토"]


def _app_version() -> str:
    from core import paths

    try:
        return (paths.app_root() / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return "?"


class SettingsDialog(QDialog):
    def __init__(self, settings_repo, events, backup_service, autostart_service,
                 recurring_repo, parent=None):
        super().__init__(parent)
        self._settings = settings_repo
        self._events = events
        self._backup = backup_service
        self._autostart = autostart_service
        self._rules = recurring_repo

        self.setWindowTitle(f"설정 — v{_app_version()}")
        self.resize(420, 480)

        tabs = QTabWidget()
        tabs.addTab(self._build_general(), "일반")
        tabs.addTab(self._build_recurring(), "반복 할일")

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        root.addWidget(close)

    # ── 일반 탭 ─────────────────────────────────────────────
    def _build_general(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        # 캐릭터 이미지 (상황별). 비우면 기본 이미지로 표시됨.
        # 빌드에서 캐릭터 변경을 끈 경우(미지원) 이미지 칸을 숨긴다.
        if feature_flags.character_edit_enabled():
            self._add_image_row(form, "이미지 · 기본", policies.KEY_IMAGE_PATH)
            self._add_image_row(form, "이미지 · 밀린 할일", policies.KEY_IMAGE_OVERDUE)
            self._add_image_row(form, "이미지 · 삭제 시", policies.KEY_IMAGE_DELETE)

        # 미완료 처리
        self._incomplete = QComboBox()
        self._incomplete.addItem("그 날짜에 유지 (keep)", "keep")
        self._incomplete.addItem("다음 날로 이월 (rollover)", "rollover")
        self._select_data(self._incomplete, self._settings.get(policies.KEY_INCOMPLETE, "keep"))
        self._incomplete.currentIndexChanged.connect(
            lambda: self._settings.set(policies.KEY_INCOMPLETE, self._incomplete.currentData())
        )
        form.addRow("미완료 할일", self._incomplete)

        # 월간 오버플로
        self._overflow = QComboBox()
        self._overflow.addItem("없는 달은 건너뜀 (skip)", "skip")
        self._overflow.addItem("말일로 당김 (clamp)", "clamp")
        self._select_data(self._overflow, self._settings.get(policies.KEY_MONTH_OVERFLOW, "skip"))
        self._overflow.currentIndexChanged.connect(
            lambda: self._settings.set(policies.KEY_MONTH_OVERFLOW, self._overflow.currentData())
        )
        form.addRow("월 마지막날 규칙", self._overflow)

        # 테마
        self._theme = QComboBox()
        self._theme.addItem("자동 (시스템)", "system")
        self._theme.addItem("밝게", "light")
        self._theme.addItem("어둡게", "dark")
        self._select_data(self._theme, self._settings.get(policies.KEY_THEME, "system"))
        self._theme.currentIndexChanged.connect(self._change_theme)
        form.addRow("테마", self._theme)

        # 자동시작
        self._autostart_cb = QCheckBox("로그인 시 자동 시작")
        if self._autostart.supported:
            self._autostart_cb.setChecked(self._autostart.is_enabled())
            self._autostart_cb.toggled.connect(self._toggle_autostart)
        else:
            self._autostart_cb.setEnabled(False)
            self._autostart_cb.setToolTip("이 OS 에서는 미지원")
        form.addRow("", self._autostart_cb)

        # 백업
        backup_box = QGroupBox("데이터 백업")
        bl = QHBoxLayout(backup_box)
        b_exp = QPushButton("내보내기")
        b_exp.clicked.connect(self._export)
        b_imp = QPushButton("복원(가져오기)")
        b_imp.clicked.connect(self._import)
        bl.addWidget(b_exp)
        bl.addWidget(b_imp)
        form.addRow(backup_box)

        return w

    def _select_data(self, combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _add_image_row(self, form: QFormLayout, label: str, key: str) -> None:
        edit = QLineEdit(self._settings.get(key, "") or "")
        edit.editingFinished.connect(lambda: self._apply_image(key, edit.text().strip(), edit))
        browse = QPushButton("찾아보기")
        browse.clicked.connect(lambda: self._pick_image(key, edit))
        clear = QPushButton("지움")
        clear.setToolTip("비우면 기본 이미지로 표시")
        clear.clicked.connect(lambda: self._apply_image(key, "", edit))
        row = QHBoxLayout()
        row.addWidget(edit)
        row.addWidget(browse)
        row.addWidget(clear)
        form.addRow(label, row)

    def _pick_image(self, key: str, edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "캐릭터 이미지 선택", "", "이미지 (*.png *.jpg *.jpeg *.gif *.webp)"
        )
        if path:
            self._apply_image(key, path, edit)

    def _apply_image(self, key: str, path: str, edit: QLineEdit) -> None:
        edit.setText(path)
        self._settings.set(key, path)
        self._events.character_image_changed.emit(path)

    def _change_theme(self) -> None:
        self._settings.set(policies.KEY_THEME, self._theme.currentData())
        self._events.theme_changed.emit()

    def _toggle_autostart(self, on: bool) -> None:
        self._autostart.set_enabled(on)
        self._settings.set(policies.KEY_AUTOSTART, "1" if on else "0")

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "백업 내보내기", "character_todo_backup.db", "SQLite (*.db)"
        )
        if not path:
            return
        try:
            self._backup.export(path)
            QMessageBox.information(self, "백업", f"내보냈습니다:\n{path}")
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "오류", str(ex))

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "백업 복원", "", "SQLite (*.db)")
        if not path:
            return
        if QMessageBox.question(
            self, "복원", "현재 데이터를 덮어씁니다. 계속할까요?\n(복원 후 앱을 재시작하세요)"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._backup.import_(path)
            QMessageBox.information(self, "복원", "복원했습니다. 앱을 재시작하세요.")
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "오류", str(ex))

    # ── 반복 할일 탭 ────────────────────────────────────────
    def _build_recurring(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        self._rule_list = QListWidget()
        v.addWidget(self._rule_list, 1)

        del_btn = QPushButton("선택 규칙 삭제")
        del_btn.clicked.connect(self._delete_rule)
        v.addWidget(del_btn)

        box = QGroupBox("새 반복 추가")
        form = QFormLayout(box)
        self._r_content = QLineEdit()
        form.addRow("내용", self._r_content)

        self._r_type = QComboBox()
        self._r_type.addItem("매일", "daily")
        self._r_type.addItem("매주", "weekly")
        self._r_type.addItem("매월", "monthly")
        self._r_type.currentIndexChanged.connect(self._sync_type_inputs)
        form.addRow("주기", self._r_type)

        wk_row = QHBoxLayout()
        self._wd_checks: list[QCheckBox] = []
        for name in _WD:
            cb = QCheckBox(name)
            self._wd_checks.append(cb)
            wk_row.addWidget(cb)
        self._wd_widget = QWidget()
        self._wd_widget.setLayout(wk_row)
        form.addRow("요일", self._wd_widget)

        self._dom = QSpinBox()
        self._dom.setRange(1, 31)
        form.addRow("매월 일", self._dom)

        add_btn = QPushButton("추가")
        add_btn.clicked.connect(self._add_rule)
        form.addRow(add_btn)

        v.addWidget(box)
        self._sync_type_inputs()
        self._reload_rules()
        return w

    def _sync_type_inputs(self) -> None:
        t = self._r_type.currentData()
        self._wd_widget.setEnabled(t == "weekly")
        self._dom.setEnabled(t == "monthly")

    def _reload_rules(self) -> None:
        self._rule_list.clear()
        for rule in self._rules.list_all():
            it = QListWidgetItem(f"{rule.content}  —  {rule.describe()}")
            it.setData(Qt.ItemDataRole.UserRole, rule.id)
            self._rule_list.addItem(it)

    def _add_rule(self) -> None:
        content = self._r_content.text().strip()
        if not content:
            return
        t = self._r_type.currentData()
        weekdays = day_of_month = None
        if t == "weekly":
            sel = [str(i) for i, cb in enumerate(self._wd_checks) if cb.isChecked()]
            if not sel:
                QMessageBox.warning(self, "반복", "요일을 하나 이상 선택하세요.")
                return
            weekdays = ",".join(sel)
        elif t == "monthly":
            day_of_month = self._dom.value()
        self._rules.add(content, t, weekdays=weekdays, day_of_month=day_of_month)
        self._r_content.clear()
        self._reload_rules()

    def _delete_rule(self) -> None:
        it = self._rule_list.currentItem()
        if not it:
            return
        rule_id = it.data(Qt.ItemDataRole.UserRole)
        self._rules.delete(rule_id)
        self._reload_rules()
