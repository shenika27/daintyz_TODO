# Character TODO

바탕화면 위에 캐릭터가 떠 있는 데스크톱 할일(투두) 앱. 캐릭터를 클릭하면
말풍선이 열리고, 일간 → 주간 → 월간으로 확장하며 할일을 관리합니다. (PyQt6 / SQLite)

## 주요 기능

- 프레임리스·투명·항상 위 캐릭터, 드래그 이동, 위치 저장/복원(화면 안으로 clamp)
- 좌클릭: 말풍선 토글 / 우클릭: 설정·트레이 최소화·종료
- 말풍선: 확장(일→주→월 순환)·최소화·되돌리기 버튼 + 하단 입력(Enter 추가)
- 할일: 체크박스 토글(취소선), hover 연필로 인라인 편집, 드래그로 정렬·날짜이동,
  앱 밖으로 드롭 시 삭제(+되돌리기). 반복 회차 삭제는 숨김 처리(tombstone).
- 주간(일~토 7열, 날짜 표기), 월간(7×6 고정, 월/일 표기, 미완료 개수 점)
- 반복 할일: 설정에서 매일/매주/매월 추가. **조회 시점 생성** 방식
- 설정: 캐릭터 이미지 경로, 미완료 정책(keep/rollover), 월 말일 규칙(skip/clamp),
  자동시작(Windows), 백업 내보내기/복원
- 시스템 트레이 상주, 알림 서비스 골격(시간 입력 UI만 붙이면 동작)

## 실행 (개발)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     /  macOS·Linux: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

데이터는 사용자 폴더에 저장됩니다.
- Windows: `%APPDATA%\CharacterTodo\todo.db`
- macOS: `~/Library/Application Support/CharacterTodo/todo.db`
- Linux: `~/.local/share/CharacterTodo/todo.db`

## 빌드 (Windows 단일 .exe)

```bat
build\build.bat
```

- 산출물: **`dist\CharacterTodo.exe` 단일 파일** (PyInstaller onefile). 이 exe 하나만 전달하면 됩니다.
  - 코드·리소스가 exe 안에 포함되어 실행 시 임시폴더로 풀려 동작합니다.
  - 단, onefile은 "숨김"이지 암호화가 아닙니다(전용 도구로 추출 가능).
- 빌드 시 묻는 항목:
  - **캐릭터 변경 지원 여부 (Y/n)**: `Y`(기본)=설정에서 캐릭터 이미지 변경 가능 / `n`=변경 칸 숨김(고정 캐릭터).
    환경변수로도 지정: `set CHARACTER_EDIT=0` 후 빌드.
- **상황별 캐릭터 이미지(번들 폴백)**: 설정에서 지정하지 않으면 `resources\` 의 아래 파일을 사용합니다.
  잠금 빌드(`CHARACTER_EDIT=0`)에서도 파일만 넣으면 적용됩니다. 확장자는 `.png` → `.gif` 순으로 찾습니다.

  | 상황 | 파일명(베이스) | 필수 |
  |------|---------------|------|
  | 기본(오늘·평상시) | `character_default.png` / `.gif` | 필수(없으면 코드로 그린 기본 캐릭터) |
  | 밀린 할일 있을 때 | `character_overdue.png` / `.gif` | 선택(없으면 기본으로 폴백) |
  | 삭제(캐릭터에 끌어다 둘 때) | `character_delete.png` / `.gif` | 선택(없으면 기본으로 폴백) |
  | 비활성(마지막 활동 후 n시간 초과) | `character_idle.png` / `.gif` | 선택(없으면 기본으로 폴백) |
  | 완료 리액션(체크 시 잠깐) | `character_done.png` / `.gif` | 선택(없으면 리액션 생략) |

  우선순위는 삭제 > 완료 리액션 > 밀린 할일 > 비활성 > 기본. 투명 배경 권장이며 앱이 비율 유지로 축소합니다.
  **GIF는 애니메이션으로 재생됩니다**(현재 상황의 GIF만 재생). PNG는 정지 이미지입니다.
- 설치본(선택): Inno Setup 설치 후 `set MAKE_INSTALLER=1` 로 빌드하면
  `build\installer_out\CharacterTodo-Setup-x.y.z.exe` 도 생성됩니다(보통은 불필요).
- 트레이/exe 아이콘을 바꾸려면 `resources\app.ico` 를 추가하세요(없어도 동작).

## 테스트

```bash
python tests/test_policies.py     # 순수 로직 (PyQt6 불필요)
# 또는: python -m pytest -q
```

## 아키텍처 (결합도 낮게 · 계층 분리)

```
domain/    순수 모델·규칙 (Qt/DB 의존 없음) → 단독 테스트
data/      SQLite 영속성 + 마이그레이션 러너
services/  응용 로직 (Repository 조합 + 도메인 정책)
ui/        위젯만 (비즈니스 로직 없음)
core/      events(시그널 허브) · paths · logging
main.py    의존성 조립(DI) 한 곳
```

- UI ↔ Service 는 `core/events.py` 시그널 허브로만 통신 → 한쪽을 바꿔도 안 깨짐.
- `domain` 은 아무것도 의존하지 않는 가장 안쪽 계층.

## 버전 관리 / 마이그레이션

- 스키마는 `data/migrations/NNNN_*.sql`. 부팅 시 `PRAGMA user_version` 을 읽어
  밀린 마이그레이션만 순서대로 적용합니다(별도 버전 테이블 없음).
- 큰 패치로 스키마가 바뀌면 `0002_*.sql` 처럼 새 파일을 추가하면 됩니다.
  기존 사용자 `.db` 가 안전하게 올라갑니다.
- 앱 버전은 `VERSION` 파일.

## 알려진 제약 / 다듬을 부분

- 외부 드롭 삭제 시 "체크박스→휴지통 아이콘 전환·텍스트 회색" 같은 드래그 중 시각 효과는
  기능(삭제+되돌리기) 위주로 구현되어 있고, 시각 연출은 추후 보강 대상입니다.
- 알림은 골격만 동작합니다(remind_at 입력 UI 미연결).
