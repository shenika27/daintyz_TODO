"""ui/settings_dialog.py — 설정 화면.

이미지 경로 · 미완료/월간 정책 · 자동시작 · 백업(내보내기/복원) · 반복 할일 관리.
"""
from __future__ import annotations

import logging
from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
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


def _app_version() -> str:
    from core import paths

    try:
        return (paths.app_root() / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return "?"


class SettingsDialog(QDialog):
    def __init__(self, settings_repo, events, backup_service, autostart_service,
                 recurring_repo, todo_service, parent=None):
        super().__init__(parent)
        self._settings = settings_repo
        self._events = events
        self._backup = backup_service
        self._autostart = autostart_service
        self._rules = recurring_repo
        self._todo_service = todo_service

        self.setWindowTitle(f"설정 — v{_app_version()}")
        self.resize(420, 480)

        tabs = QTabWidget()
        tabs.addTab(self._build_general(), "일반")
        # 캐릭터 이미지 변경이 허용된 빌드에서만 '이미지' 탭 노출
        if feature_flags.character_edit_enabled():
            tabs.addTab(self._build_images(), "이미지")
        tabs.addTab(self._build_shortcuts(), "단축키")
        tabs.addTab(self._build_recurring(), "반복 할일")

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        root.addWidget(close)

    # 상황별 이미지: (표시명, 설정키, resources 폴백 베이스명)
    _IMAGE_ROWS = [
        ("기본", policies.KEY_IMAGE_PATH, "character_default"),
        ("밀린 할일", policies.KEY_IMAGE_OVERDUE, "character_overdue"),
        ("삭제 시", policies.KEY_IMAGE_DELETE, "character_delete"),
        ("비활성", policies.KEY_IMAGE_IDLE, "character_idle"),
        ("완료 리액션", policies.KEY_IMAGE_DONE, "character_done"),
        ("타이머 중", policies.KEY_IMAGE_WORK, "character_work"),
        ("타이머 정지", policies.KEY_IMAGE_PAUSE, "character_pause"),
        ("타이머 완료", policies.KEY_IMAGE_TIMER_DONE, "character_timer_done"),
        ("목록 열림", policies.KEY_IMAGE_OPEN, "character_open"),
        ("목록 닫힘", policies.KEY_IMAGE_CLOSED, "character_closed"),
        ("할일 추가 리액션", policies.KEY_IMAGE_ADD, "character_add"),
    ]

    # ── 이미지 탭 ───────────────────────────────────────────
    def _build_images(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        intro = QLabel("상황별 캐릭터 이미지. 비우면 resources 의 기본 파일로 표시됩니다.")
        intro.setObjectName("subText")
        intro.setWordWrap(True)
        form.addRow(intro)
        for name, key, base in self._IMAGE_ROWS:
            self._add_image_row(form, name, key, base)
        return w

    # ── 일반 탭 ─────────────────────────────────────────────
    def _build_general(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        # 캐릭터 크기(%)
        self._char_scale = QSpinBox()
        self._char_scale.setRange(50, 200)
        self._char_scale.setSingleStep(10)
        self._char_scale.setSuffix(" %")
        self._char_scale.setValue(int(self._settings.get(policies.KEY_CHAR_SCALE, "100") or "100"))
        self._char_scale.valueChanged.connect(self._on_scale_changed)
        form.addRow("캐릭터 크기", self._char_scale)

        # 비활성 판정 시간 (0 = 기능 끔)
        self._idle_hours = QSpinBox()
        self._idle_hours.setRange(0, 168)
        self._idle_hours.setSuffix(" 시간  (0 = 끔)")
        self._idle_hours.setValue(int(self._settings.get(policies.KEY_IDLE_HOURS, "0") or "0"))
        self._idle_hours.valueChanged.connect(
            lambda v: self._settings.set(policies.KEY_IDLE_HOURS, str(v))
        )
        form.addRow("비활성 기준 시간", self._idle_hours)

        # 밀린 할일 패널 위치
        self._panel_side = QComboBox()
        self._panel_side.addItem("오른쪽", "right")
        self._panel_side.addItem("왼쪽", "left")
        self._select_data(self._panel_side, self._settings.get(policies.KEY_OVERDUE_PANEL_SIDE, "right"))
        self._panel_side.currentIndexChanged.connect(
            lambda: self._settings.set(policies.KEY_OVERDUE_PANEL_SIDE, self._panel_side.currentData())
        )
        form.addRow("밀린 할일 위치", self._panel_side)

        # 미완료 처리
        self._incomplete = QComboBox()
        self._incomplete.addItem("그 날짜에 유지 (keep)", "keep")
        self._incomplete.addItem("다음 날로 이월 (rollover)", "rollover")
        self._select_data(self._incomplete, self._settings.get(policies.KEY_INCOMPLETE, "keep"))
        self._incomplete.currentIndexChanged.connect(
            lambda: self._settings.set(policies.KEY_INCOMPLETE, self._incomplete.currentData())
        )
        form.addRow("미완료 할일", self._incomplete)

        # 타이머 −/+ 증감 간격 (1분 미만은 항상 5초 고정)
        self._timer_step = QComboBox()
        for label, secs in (
            ("10초", 10), ("20초", 20), ("30초", 30),
            ("1분", 60), ("5분", 300), ("10분", 600),
        ):
            self._timer_step.addItem(label, secs)
        self._select_data(
            self._timer_step,
            self._settings.get_int(policies.KEY_TIMER_STEP, policies.DEFAULT_TIMER_STEP),
        )
        self._timer_step.currentIndexChanged.connect(
            lambda: self._settings.set(
                policies.KEY_TIMER_STEP, str(self._timer_step.currentData())
            )
        )
        form.addRow("타이머 증감 간격", self._timer_step)

        # 폰트 서체
        font_row = QHBoxLayout()
        self._font_combo = QFontComboBox()
        self._font_combo.setWritingSystem(QFontDatabase.WritingSystem.Korean)
        saved_font = self._settings.get(policies.KEY_FONT, "")
        if saved_font:
            self._font_combo.setCurrentFont(QFont(saved_font))
        self._font_combo.currentFontChanged.connect(self._on_font_changed)
        font_reset = QPushButton("기본")
        font_reset.setFixedWidth(44)
        font_reset.setToolTip("시스템 기본 폰트로 되돌리기")
        font_reset.clicked.connect(self._reset_font)
        font_row.addWidget(self._font_combo)
        font_row.addWidget(font_reset)
        form.addRow("폰트", font_row)

        # 테마
        self._theme = QComboBox()
        self._theme.addItem("자동 (시스템)", "system")
        self._theme.addItem("밝게", "light")
        self._theme.addItem("어둡게", "dark")
        self._select_data(self._theme, self._settings.get(policies.KEY_THEME, "system"))
        self._theme.currentIndexChanged.connect(self._change_theme)
        form.addRow("테마", self._theme)

        # 트레이 최소화 시 타이머 풍선 유지
        self._timer_tray_cb = QCheckBox("트레이로 최소화해도 타이머 풍선 유지")
        self._timer_tray_cb.setChecked(
            self._settings.get_bool(policies.KEY_TIMER_TRAY_SHOW, True)
        )
        self._timer_tray_cb.toggled.connect(
            lambda on: self._settings.set_bool(policies.KEY_TIMER_TRAY_SHOW, on)
        )
        form.addRow("", self._timer_tray_cb)

        # 최소화 시 '할일 n개' 풍선 표시
        self._todo_bubble_cb = QCheckBox("최소화 시 '할일 n개' 풍선 표시")
        self._todo_bubble_cb.setChecked(
            self._settings.get_bool(policies.KEY_TODO_COUNT_BUBBLE, True)
        )
        self._todo_bubble_cb.toggled.connect(self._toggle_todo_bubble)
        form.addRow("", self._todo_bubble_cb)

        # 팝업 열기/닫기 페이드 애니메이션
        self._anim_cb = QCheckBox("팝업 열기/닫기 애니메이션")
        self._anim_cb.setChecked(
            self._settings.get_bool(policies.KEY_BUBBLE_ANIMATION, True)
        )
        self._anim_cb.toggled.connect(
            lambda on: self._settings.set_bool(policies.KEY_BUBBLE_ANIMATION, on)
        )
        form.addRow("", self._anim_cb)

        # 자동시작
        self._autostart_cb = QCheckBox("부팅 시 자동 시작")
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

    def _resource_filename(self, base: str) -> str:
        """resources 에 있는 폴백 파일명(png→gif). 없으면 'base.* (없음)'."""
        from core import paths

        try:
            res_dir = paths.resource_dir()
            for ext in (".png", ".gif"):
                if (res_dir / (base + ext)).exists():
                    return base + ext
        except Exception:  # noqa: BLE001
            pass
        return f"{base}.* (없음)"

    def _make_image_label(self, name: str, base: str) -> QWidget:
        """항목명 + 그 하단에 resources 파일명을 작은 회색 글씨로."""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        title = QLabel(name)
        fname = QLabel(self._resource_filename(base))
        fname.setObjectName("subText")
        f = fname.font()
        f.setPointSize(max(7, f.pointSize() - 1))
        fname.setFont(f)
        v.addWidget(title)
        v.addWidget(fname)
        return box

    def _add_image_row(self, form: QFormLayout, name: str, key: str, base: str) -> None:
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
        form.addRow(self._make_image_label(name, base), row)

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

    def _on_font_changed(self, font: QFont) -> None:
        self._settings.set(policies.KEY_FONT, font.family())
        f = QApplication.instance().font()
        f.setFamily(font.family())
        QApplication.instance().setFont(f)
        self._events.theme_changed.emit()

    def _reset_font(self) -> None:
        self._settings.set(policies.KEY_FONT, "")
        QApplication.instance().setFont(QFont())
        self._font_combo.setCurrentFont(QApplication.instance().font())
        self._events.theme_changed.emit()

    def _change_theme(self) -> None:
        self._settings.set(policies.KEY_THEME, self._theme.currentData())
        self._events.theme_changed.emit()

    def _on_scale_changed(self, v: int) -> None:
        self._settings.set(policies.KEY_CHAR_SCALE, str(v))
        self._events.character_scale_changed.emit()

    def _toggle_todo_bubble(self, on: bool) -> None:
        self._settings.set_bool(policies.KEY_TODO_COUNT_BUBBLE, on)
        self._events.todo_count_bubble_changed.emit(on)

    # ── 단축키 탭 ───────────────────────────────────────────
    def _build_shortcuts(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        form = QFormLayout()
        v.addLayout(form)

        # (라벨, 설정키, 기본값)
        self._hotkey_defs = [
            ("투두 목록 토글", policies.KEY_HOTKEY_TODO, policies.DEFAULT_HOTKEY_TODO),
            ("캐릭터 토글", policies.KEY_HOTKEY_CHARACTER, policies.DEFAULT_HOTKEY_CHARACTER),
            ("오늘로 이동", policies.KEY_HOTKEY_TODAY, policies.DEFAULT_HOTKEY_TODAY),
            ("밀린할일 패널 토글", policies.KEY_HOTKEY_OVERDUE, policies.DEFAULT_HOTKEY_OVERDUE),
            ("타이머 패널 토글", policies.KEY_HOTKEY_TIMER, policies.DEFAULT_HOTKEY_TIMER),
        ]
        self._hotkey_edits: dict[str, QKeySequenceEdit] = {}
        for label, key, default in self._hotkey_defs:
            seq = self._settings.get(key, default) or default
            edit = QKeySequenceEdit(QKeySequence(seq))
            edit.setMaximumSequenceLength(1)  # 한 조합만
            edit.editingFinished.connect(lambda k=key: self._save_hotkey(k))
            self._hotkey_edits[key] = edit
            form.addRow(label, edit)

        reset = QPushButton("기본값으로 되돌리기")
        reset.clicked.connect(self._reset_hotkeys)
        v.addWidget(reset)

        info = QLabel("입력란을 클릭하고 원하는 조합을 누르세요. 같은 조합은 중복될 수 없습니다.")
        info.setObjectName("subText")
        info.setWordWrap(True)
        v.addWidget(info)
        v.addStretch(1)
        return w

    def _save_hotkey(self, key: str) -> None:
        seq = self._hotkey_edits[key].keySequence().toString()
        default = next(d for _l, k, d in self._hotkey_defs if k == key)
        # 중복 검사: 다른 항목과 같은 조합이면 되돌림
        for other, edit in self._hotkey_edits.items():
            if other != key and seq and edit.keySequence().toString() == seq:
                QMessageBox.warning(self, "단축키", "이미 사용 중인 조합입니다.")
                prev = self._settings.get(key, default) or default
                self._hotkey_edits[key].setKeySequence(QKeySequence(prev))
                return
        self._settings.set(key, seq)
        self._events.hotkeys_changed.emit()

    def _reset_hotkeys(self) -> None:
        for _label, key, default in self._hotkey_defs:
            self._settings.set(key, default)
            self._hotkey_edits[key].setKeySequence(QKeySequence(default))
        self._events.hotkeys_changed.emit()

    def _toggle_autostart(self, on: bool) -> None:
        self._autostart.set_enabled(on)
        self._settings.set_bool(policies.KEY_AUTOSTART, on)

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
        for name in policies.WEEKDAYS_KR:
            cb = QCheckBox(name)
            self._wd_checks.append(cb)
            wk_row.addWidget(cb)
        self._wd_widget = QWidget()
        self._wd_widget.setLayout(wk_row)
        form.addRow("요일", self._wd_widget)

        self._dom = QSpinBox()
        self._dom.setRange(1, 31)
        dom_note = QLabel("해당 월에 지정한 날이 없으면 말일에 생성됩니다.\n(예: 31일 설정 시 2월은 28일 또는 29일에 생성)")
        dom_note.setObjectName("subText")
        dom_note.setWordWrap(True)
        form.addRow("매월 일", self._dom)
        form.addRow("", dom_note)

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
        # 새 규칙이 오늘에 해당하면 즉시 생성하고 목록 갱신(반복은 '당일 생성')
        self._todo_service.ensure_today_recurring()
        self._events.todos_changed.emit(date.today().isoformat())
        self._r_content.clear()
        self._reload_rules()

    def _delete_rule(self) -> None:
        it = self._rule_list.currentItem()
        if not it:
            return
        rule_id = it.data(Qt.ItemDataRole.UserRole)

        # 이미 생성된 반복 할일 처리 선택: 전체 삭제 / 남기기 / 취소
        box = QMessageBox(self)
        box.setWindowTitle("반복 할일 삭제")
        box.setText("규칙을 삭제합니다.\n이미 생성된 반복 할일도 함께 삭제할까요?")
        del_all = box.addButton("전체 삭제", QMessageBox.ButtonRole.DestructiveRole)
        keep = box.addButton("남기기", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked not in (del_all, keep):
            return  # 취소
        if clicked is del_all:
            self._todo_service.delete_recurring_todos(rule_id)
        self._rules.delete(rule_id)
        self._reload_rules()
