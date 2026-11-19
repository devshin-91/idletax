# IdleTax

이 프로젝트는 `small-app-harness` 스킬의 공통 규칙을 따른다. 아래는 이 프로젝트에만 해당하는 내용이다.
개인 정보(계정, 로컬 경로)는 `CLAUDE.local.md`, 진행 상태는 `PROGRESS.md`에 있다 (둘 다 gitignore).
이 파일은 공개 저장소에 올라가도 괜찮은 내용만 쓴다.

## 무엇인가

돈 내고 안 쓰는 구독과 미뤄 둔 결정 때문에 잃는 돈을 주·월·연 금액으로 보여 주는 포터블 Windows 앱.
개인이 무엇을 해지하고 무엇을 먼저 처리할지 판단할 근거로 쓴다. 정량적인 것만 다룬다.

## 명령

| 할 일 | 명령 |
|---|---|
| 테스트 | `.venv\Scripts\python.exe -X utf8 test_core.py` |
| 소스로 실행 | `.venv\Scripts\python.exe app.py` |
| 빌드 (테스트 포함) | `build.bat` → `dist\IdleTax.exe` |
| 샘플 데이터 | `python -X utf8 tools\make_sample.py <폴더> [en\|ko]` |
| 모바일 화면 프로토타입 | `python -X utf8 tools\build_mobile_proto.py <pyodide@0.26.4 npm 패키지 폴더>` → `build\mobile-proto\` (`page.html`은 Artifact용, `index.html`은 로컬 서버용) |

모바일 프로토타입(`tools\mobile_proto\`)은 Pyodide로 `core.py`·`i18n.py`를 브라우저에서 그대로 돌린다.
`bridge.py`는 엔진 함수를 불러 값을 고르고 형식만 맞춘다. 숫자를 따로 계산하는 코드를 넣지 않는다.

## 데이터

- 사용자 데이터: `idletax-data.json` (exe 옆, gitignore). 버전 3. 버전 1·2 파일은 불러올 때 올린다.
- 앱 이름이 2026-11-20에 StallMeter에서 IdleTax로 바뀌었다. 옛 `stallmeter-data.json`과 `%APPDATA%\StallMeter`는 처음 켤 때 새 이름으로 옮긴다(`core.data_path`, 테스트가 확인). 모바일 프로토타입은 옛 localStorage 키를 옮긴다.
- 항목은 `kind`가 `sub`(구독) 또는 `decision`(미결 사항)이다. 탭 목록은 `categories`에 따로 저장하고(빈 탭 가능), 항목의 `category`가 그 탭 이름이다.
- 구독의 `billing`은 `monthly`, `yearly`, `prepaid`, `installment` 넷이다. `installment`만 `months`(할부 개월 수)를 쓴다.
- 샘플 항목은 `sample: true`로 표시한다. 샘플 내용은 `i18n.SAMPLE`에 있고 `core.load_sample` / `clear_sample`이 넣고 뺀다.

## 이 프로젝트의 불변 조건

- 손실 규칙은 `doc/how-it-works.md`와 같아야 한다. 규칙을 바꾸면 문서(영·한), `r_formula`·`f_hint`·`f_sub_hint` 문구, 테스트를 함께 바꾼다.
- 구독: 목표를 더는 채울 수 없게 된 날만 손실이다. 오늘은 빠진 날이 아니다. 한 번도 안 쓴 주의 손실은 그 주 요금과 같다.
- 할부의 손실은 매달 내는 할부금이 아니라 총액 ÷ 이용 기간 날 수로 센다.
- 탭 삭제와 샘플 지우기는 사용자가 직접 넣은 항목을 지우지 않는다 (테스트가 확인).
- 화면 색과 글꼴은 `app.py` 맨 위 상수와 `App.style`에만 둔다. 버튼은 `App.button`으로 만든다.
- 미결 사항: 주말은 세지 않는다. 결정된 항목의 비용은 결정 시각에서 멈춘다.
- 사용한 날은 사용자가 직접 표시한다. 다른 앱의 달력·사용 기록·계정을 읽지 않는다.
- `core.py`는 표준 라이브러리만 쓰고 tkinter를 import하지 않는다. `decimal`, `hashlib`, `statistics`, `uuid`처럼 빌드에서 뺀 모듈을 끌어오는 import도 쓰지 않는다.
- UI 문구는 `i18n.py`에만 둔다. en과 ko의 키와 자리표시자가 같아야 한다 (테스트가 확인).
- 네트워크를 쓰지 않는다.

## 하지 말 것

- 숫자를 "측정값"이라고 표현하지 않는다. 사용자가 넣은 값으로 계산한 것이다.
- 건강 효과처럼 금액으로 셀 수 없는 것에 금액을 붙이지 않는다.
- 실제 서비스 이름과 요금을 샘플이나 기본값으로 넣지 않는다. 요금은 바뀌고, 사용자가 직접 넣는 값이다.
