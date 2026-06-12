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

## 빌드 (Windows 설치본 .exe)

```bat
build\build.bat
```

- 1차 산출물: `dist\CharacterTodo\CharacterTodo.exe` (PyInstaller)
- 2차 산출물: `build\installer_out\CharacterTodo-Setup-x.y.z.exe` (Inno Setup 설치 시)
  - Inno Setup 6 미설치면 이 단계는 건너뛰고 exe 만 생성됩니다.
  - 다운로드: https://jrsoftware.org/isdl.php
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
