"""ui/character_sound.py — 상황별 캐릭터 wav 사운드 재생."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from core import asset_pack, feature_flags, paths
from domain import policies

log = logging.getLogger(__name__)

SOUND_MODE_ONCE = "once"
SOUND_MODE_LOOP = "loop"
SOUND_EXTS = (".wav", ".flac")


@dataclass(frozen=True)
class SoundSpec:
    situation: str
    label: str
    path_key: str
    volume_key: str
    mode_key: str
    base: str


SOUND_SPECS: tuple[SoundSpec, ...] = (
    SoundSpec(
        "overdue",
        "밀린 할일",
        policies.KEY_SOUND_OVERDUE,
        policies.KEY_SOUND_OVERDUE_VOLUME,
        policies.KEY_SOUND_OVERDUE_MODE,
        "character_overdue",
    ),
    SoundSpec(
        "delete",
        "삭제 시",
        policies.KEY_SOUND_DELETE,
        policies.KEY_SOUND_DELETE_VOLUME,
        policies.KEY_SOUND_DELETE_MODE,
        "character_delete",
    ),
    SoundSpec(
        "idle",
        "비활성",
        policies.KEY_SOUND_IDLE,
        policies.KEY_SOUND_IDLE_VOLUME,
        policies.KEY_SOUND_IDLE_MODE,
        "character_idle",
    ),
    SoundSpec(
        "done",
        "완료 리액션",
        policies.KEY_SOUND_DONE,
        policies.KEY_SOUND_DONE_VOLUME,
        policies.KEY_SOUND_DONE_MODE,
        "character_done",
    ),
    SoundSpec(
        "work",
        "타이머 중",
        policies.KEY_SOUND_WORK,
        policies.KEY_SOUND_WORK_VOLUME,
        policies.KEY_SOUND_WORK_MODE,
        "character_work",
    ),
    SoundSpec(
        "pause",
        "타이머 정지",
        policies.KEY_SOUND_PAUSE,
        policies.KEY_SOUND_PAUSE_VOLUME,
        policies.KEY_SOUND_PAUSE_MODE,
        "character_pause",
    ),
    SoundSpec(
        "timer_done",
        "타이머 완료",
        policies.KEY_SOUND_TIMER_DONE,
        policies.KEY_SOUND_TIMER_DONE_VOLUME,
        policies.KEY_SOUND_TIMER_DONE_MODE,
        "character_timer_done",
    ),
    SoundSpec(
        "open",
        "목록 열림",
        policies.KEY_SOUND_OPEN,
        policies.KEY_SOUND_OPEN_VOLUME,
        policies.KEY_SOUND_OPEN_MODE,
        "character_open",
    ),
    SoundSpec(
        "closed",
        "목록 닫힘",
        policies.KEY_SOUND_CLOSED,
        policies.KEY_SOUND_CLOSED_VOLUME,
        policies.KEY_SOUND_CLOSED_MODE,
        "character_closed",
    ),
    SoundSpec(
        "add",
        "할일 추가 리액션",
        policies.KEY_SOUND_ADD,
        policies.KEY_SOUND_ADD_VOLUME,
        policies.KEY_SOUND_ADD_MODE,
        "character_add",
    ),
)

SOUND_SPEC_BY_SITUATION = {spec.situation: spec for spec in SOUND_SPECS}


def bundled_sound_source(situation: str) -> str | None:
    """상황별 기본 사운드 소스를 찾는다. 암호화 빌드는 pak:<name>, 일반 빌드는 파일 경로."""
    spec = SOUND_SPEC_BY_SITUATION.get(situation)
    if spec is None:
        return None
    for ext in SOUND_EXTS:
        names = (f"sound/{spec.base}{ext}", f"{spec.base}{ext}")
        if asset_pack.is_encrypted_build():
            for name in names:
                if asset_pack.has(name):
                    return f"pak:{name}"
            continue
        for res_dir in (paths.sound_resource_dir(), paths.resource_dir()):
            path = res_dir / f"{spec.base}{ext}"
            if path.exists():
                return str(path)
    return None


def bundled_sound_filename(base: str) -> str:
    """설정 화면 표시용 resources 파일명."""
    try:
        for ext in SOUND_EXTS:
            names = (f"sound/{base}{ext}", f"{base}{ext}")
            if asset_pack.is_encrypted_build():
                for name in names:
                    if asset_pack.has(name):
                        return name
                continue
            for res_dir in (paths.sound_resource_dir(), paths.resource_dir()):
                if (res_dir / f"{base}{ext}").exists():
                    return f"{base}{ext}"
    except Exception:  # noqa: BLE001
        pass
    return f"{base}.wav/.flac (없음)"


class CharacterSoundPlayer(QObject):
    """상황별 사운드를 캐시하고 현재 상황 전환에 맞춰 재생/정지한다."""

    def __init__(self, settings_repo, parent=None):
        super().__init__(parent)
        self._settings = settings_repo
        self._players: dict[str, QMediaPlayer] = {}
        self._outputs: dict[str, QAudioOutput] = {}
        self._sources: dict[str, str] = {}
        self._buffers: dict[str, tuple[QByteArray, QBuffer]] = {}
        self._current_situation = ""

    def reload(self) -> None:
        self.stop()
        for player in self._players.values():
            player.setSource(QUrl())
            player.deleteLater()
        for output in self._outputs.values():
            output.deleteLater()
        for _ba, buf in self._buffers.values():
            buf.close()
            buf.deleteLater()
        self._players.clear()
        self._outputs.clear()
        self._sources.clear()
        self._buffers.clear()

    def has_source(self, situation: str) -> bool:
        return self._enabled() and self._resolve_source(situation) is not None

    def set_situation(self, situation: str, restart: bool = False) -> None:
        if situation == self._current_situation and not restart:
            return
        if situation != self._current_situation:
            self.stop()
        if situation in SOUND_SPEC_BY_SITUATION:
            self.play(situation)
            self._current_situation = situation
        else:
            self._current_situation = ""

    def play(self, situation: str, force: bool = False) -> None:
        if not force and not self._enabled():
            return
        player = self._player_for(situation)
        if player is None:
            return
        spec = SOUND_SPEC_BY_SITUATION[situation]
        mode = self._settings.get(spec.mode_key, SOUND_MODE_ONCE) or SOUND_MODE_ONCE
        player.setLoops(
            QMediaPlayer.Loops.Infinite
            if mode == SOUND_MODE_LOOP
            else QMediaPlayer.Loops.Once
        )
        output = self._outputs.get(situation)
        if output is not None:
            output.setVolume(self._volume(situation))
        player.stop()
        player.setPosition(0)
        player.play()

    def preview(self, situation: str) -> None:
        self.stop()
        self._current_situation = situation
        self.play(situation, force=True)

    def stop(self) -> None:
        for player in self._players.values():
            player.stop()
        self._current_situation = ""

    def _enabled(self) -> bool:
        return self._settings.get_bool(policies.KEY_SOUND_ENABLED, False)

    def _resolve_source(self, situation: str) -> str | None:
        spec = SOUND_SPEC_BY_SITUATION.get(situation)
        if spec is None:
            return None
        custom = self._settings.get(spec.path_key, "") if feature_flags.character_edit_enabled() else ""
        if custom:
            path = Path(custom)
            if path.is_file() and path.suffix.lower() in SOUND_EXTS:
                return str(path)
        return bundled_sound_source(situation)

    def _player_for(self, situation: str) -> QMediaPlayer | None:
        source = self._resolve_source(situation)
        if not source:
            return None
        if self._sources.get(situation) == source:
            return self._players.get(situation)

        self._dispose_situation(situation)

        player = QMediaPlayer(self)
        output = QAudioOutput(self)
        player.setAudioOutput(output)
        try:
            if source.startswith("pak:"):
                name = source[4:]
                data = asset_pack.get_bytes(name)
                if data is None:
                    return None
                ba = QByteArray(data)
                buf = QBuffer(ba, self)
                buf.open(QIODevice.OpenModeFlag.ReadOnly)
                player.setSourceDevice(buf, QUrl.fromLocalFile(name))
                self._buffers[situation] = (ba, buf)
            else:
                player.setSource(QUrl.fromLocalFile(source))
        except Exception:  # noqa: BLE001
            log.exception("사운드 로드 실패: %s", source)
            return None

        self._players[situation] = player
        self._outputs[situation] = output
        self._sources[situation] = source
        return player

    def _dispose_situation(self, situation: str) -> None:
        player = self._players.pop(situation, None)
        if player is not None:
            player.stop()
            player.setSource(QUrl())
            player.deleteLater()
        output = self._outputs.pop(situation, None)
        if output is not None:
            output.deleteLater()
        buffer_refs = self._buffers.pop(situation, None)
        if buffer_refs is not None:
            _ba, buf = buffer_refs
            buf.close()
            buf.deleteLater()
        self._sources.pop(situation, None)

    def _volume(self, situation: str) -> float:
        spec = SOUND_SPEC_BY_SITUATION[situation]
        global_volume = self._clamp(self._settings.get_int(policies.KEY_SOUND_VOLUME, 70))
        situation_volume = self._clamp(self._settings.get_int(spec.volume_key, 100))
        return (global_volume / 100.0) * (situation_volume / 100.0)

    @staticmethod
    def _clamp(value: int) -> int:
        return max(0, min(100, int(value)))
