# 아키텍처 안내 (신규자용)

이 문서는 **이 코드를 처음 보는 사람**이 "무엇이 어디 있고, 화면이 어떻게 바뀌는지"를
빨리 파악하도록 돕는다. 입문자가 가장 헷갈려 하는 **이벤트 흐름**에 초점을 둔다.

> 한 문장 요약: **바탕화면에 떠 있는 캐릭터 + 할일 말풍선** 데스크톱 앱이다.
> 각 부품은 서로를 직접 부르지 않고, 가운데 **EventBus(신호 게시판)** 를 통해서만 대화한다.

---

## 1. 큰 그림 — 4개 계층

```
┌─────────────────────────────────────────────────────────┐
│  UI 계층 (ui/)         보이는 것: 캐릭터·말풍선·패널·설정창   │
│     ↕ (호출은 아래로, 통지는 EventBus 로)                    │
│  Service 계층 (services/)   규칙·로직: 할일/타이머/반복/알림   │
│     ↕                                                      │
│  Data 계층 (data/)     SQLite 를 아는 유일한 곳 (repository) │
│     ↕                                                      │
│  Domain 계층 (domain/)  순수 규칙·상수 (Qt·DB 의존 없음)      │
└─────────────────────────────────────────────────────────┘
        ↘ core/events.py = EventBus (모든 계층이 공유하는 신호 게시판)
        ↘ main.py = 위 부품들을 한 곳에서 조립(DI)하고 실행
```

**핵심 원칙 2가지**
1. **아래 계층은 위 계층을 모른다.** `data` 는 `ui` 를 import 하지 않는다. 의존은 항상 위→아래 한 방향.
2. **가로 통신은 EventBus 로만.** 예: 할일을 추가하면 `todo_service` 가 신호를 쏘고,
   캐릭터·말풍선이 각자 그 신호를 듣고 알아서 갱신한다. 서로 직접 부르지 않는다.

---

## 2. 입문자가 꼭 알아야 할 것 — EventBus

가장 큰 진입장벽. `self._events.todo_added.emit()` 한 줄이 **누구를 깨우는지 코드에 안 보인다.**
원리는 신문 구독과 같다:

- **emit(발행)** = "할일 추가됨!" 이라고 게시판에 외친다. 누가 듣는지 신경 안 쓴다.
- **connect(구독)** = 시작할 때 "할일 추가되면 나(이 함수)한테 알려줘" 하고 등록해 둔다.

신호 정의는 전부 [core/events.py](core/events.py) 한 파일에 있다. 구독 등록(`.connect`)은
보통 각 위젯의 `__init__` 안에 모여 있다(예: [ui/character_widget.py:115](ui/character_widget.py) 근처).

### 흐름을 추적하는 법 (실전 팁)
어떤 신호가 무슨 일을 하는지 알고 싶으면:
1. 신호 이름을 [core/events.py](core/events.py) 에서 찾아 **무슨 뜻인지** 주석을 읽는다.
2. `그신호이름.emit` 을 전체 검색 → **누가 쏘는지**.
3. `그신호이름.connect` 을 전체 검색 → **누가 듣고 무슨 함수를 실행하는지**.

---

## 3. 신호 지도 (누가 쏘고 → 누가 듣나)

| 신호 | 언제 쏘나 (emit) | 누가 듣나 (connect → 실행) |
|---|---|---|
| `todos_changed(날짜)` | 할일 추가/완료/이동/삭제, 자정 넘김 | 말풍선(다시 그림)·밀린할일패널·캐릭터(상황 재계산)·타이머 유효성 검사 |
| `todo_added` | 할일 추가 순간 | 캐릭터(추가 리액션 이미지) |
| `todo_completed` | 할일 완료 체크 순간 | 캐릭터(완료 리액션 이미지) |
| `delete_undo_available(bool)` | 삭제 직후/되돌린 후 | 캐릭터(우클릭 '되돌리기' 활성화) |
| `bubble_opened` / `bubble_closed` | 말풍선 열림/닫힘 | 캐릭터(열림·닫힘 이미지, 풍선 동기화) |
| `overdue_panel_changed(bool)` | 밀린할일 표시 토글(메뉴/✕/단축키) | 말풍선(패널 표시 갱신) |
| `timer_panel_changed(bool)` | 타이머패널 토글(메뉴/✕/단축키/자동) | 말풍선(패널 표시 갱신) |
| `timer_started/tick/paused/resumed/finished/stopped` | TimerService 가 매초/상태변화 시 | 타이머패널·타이머풍선·캐릭터(work/pause 이미지)·main(완료 알림) |
| `theme_changed` | 설정에서 테마 변경 | 말풍선·패널·타이머풍선(스타일 다시 적용) |
| `character_image_changed` / `character_scale_changed` | 설정에서 이미지·크기 변경 | 캐릭터(다시 로드) |
| `todo_count_bubble_changed(bool)` | 설정에서 '할일 n개' 풍선 토글 | 캐릭터(풍선 동기화) |
| `hotkeys_changed` | 설정에서 단축키 변경 | main(전역 단축키 재등록) |

---

## 4. 구체 시나리오 2개 (끝까지 따라가 보기)

### A. 할일을 입력하고 Enter

```
입력창(InputBar) → todo_service.add()
   → repo.add()                 # DB 에 INSERT (data 계층)
   → events.todos_changed.emit  # "오늘 데이터 바뀜!"
   → events.todo_added.emit     # "방금 추가됨!"
        ↘ 말풍선: todos_changed 듣고 → 오늘 목록 다시 그림
        ↘ 캐릭터: todos_changed 듣고 → 밀린할일 여부 재계산
        ↘ 캐릭터: todo_added 듣고  → '추가' 리액션 이미지 잠깐 표시
```
입력창은 캐릭터·말풍선의 존재를 **모른다.** 신호만 쏠 뿐이다. 이게 느슨한 결합의 핵심.

### B. 할일 타이머 시작

```
할일 행의 타이머 버튼 → TimerService.start()
   → 매초 events.timer_tick.emit(남은초)
        ↘ 타이머패널: 남은 시간 숫자 갱신
        ↘ 타이머풍선: 최소화 상태일 때 남은 시간 표시
   → events.timer_started.emit
        ↘ 캐릭터: 'work'(작업 중) 이미지로 전환
   → (시간 끝) events.timer_finished.emit
        ↘ 캐릭터: 'timer_done' 리액션
        ↘ main: 트레이 알림 + (옵션) 할일 자동 완료
```

---

## 5. 파일 지도 (어디를 열까?)

| 하고 싶은 일 | 볼 파일 |
|---|---|
| 앱이 어떻게 켜지고 부품이 어떻게 조립되나 | [main.py](main.py) — `AppController.__init__` |
| 신호 종류가 궁금하다 | [core/events.py](core/events.py) |
| 할일 추가/완료/삭제 규칙 | [services/todo_service.py](services/todo_service.py) |
| 실제 DB SQL | [data/todo_repository.py](data/todo_repository.py) |
| 날짜·주차·반복 계산 (순수 함수) | [domain/policies.py](domain/policies.py) |
| 바탕화면 캐릭터(이미지·드래그·클릭) | [ui/character_widget.py](ui/character_widget.py) |
| 할일 목록 말풍선(일/주/월 뷰, 패널 배치) | [ui/bubble/bubble_widget.py](ui/bubble/bubble_widget.py) |
| 밀린할일/타이머 독립 패널의 공통 틀 | [ui/bubble/panel_base.py](ui/bubble/panel_base.py) |
| 설정 창 | [ui/settings_dialog.py](ui/settings_dialog.py) |
| 떠 있는 창들의 공통 설정(투명·항상위) | [ui/qt_helpers.py](ui/qt_helpers.py) |

---

## 6. 알아두면 덜 헷갈리는 것들

- **`KEY_...` 상수** 는 전부 [domain/policies.py](domain/policies.py) 상단에 모여 있다.
  설정값을 읽고 쓸 때 문자열 오타를 막으려고 상수로 둔 것이다.
- **PyQt 용어**: `QWidget`(화면 조각), `pyqtSignal`(신호 정의), `QTimer`(주기 실행),
  `hideEvent`(숨겨질 때 자동 호출). 이건 앱 코드가 아니라 GUI 프레임워크(PyQt6) 지식이라
  처음 보면 검색이 필요하다 — 코드가 어려운 게 아니다.
- **코드 속 `#1`, `#12` 같은 번호 주석** 은 과거 버그를 고친 이유를 표시한 흔적이다.
  "왜 이렇게 했지?" 싶으면 그 주석을 먼저 읽자.
- **그리드 표시 상태**(말풍선/패널이 보이는지)는 이 앱에서 가장 까다로운 부분이다.
  판정은 `BubbleWidget.any_grid_visible()`, 설정 의도는 `grid_intent()` 로 모아 두었으니
  거기서부터 읽으면 된다.
