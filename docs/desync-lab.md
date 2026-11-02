# 개발용 동기화 회귀 실험 도구

`scripts/desync-lab.py`는 수정 전후 EXE를 같은 시험으로 반복 실행하고 종료 코드,
시간, 출력, EXE SHA256을 저장한다. 게임/런처를 찾아 종료하거나 설치 폴더를 수정하지 않는다.
시험은 순차 실행하여 서로의 CPU 부하를 피한다. 각 실행은 새 출력 폴더를 사용하며
기존 결과 폴더에는 덮어쓰지 않는다. 실패/시간 초과/결과 누락은 성공으로 처리하지 않는다.

## 실행

프로젝트 루트에서 사용한다. `desync-lab.example.json`을 `.tools` 아래 복사하고
baseline/candidate 경로를 시험할 EXE로 설정한다. 프로세스를 실행하는 argv는 신뢰할 수 있는
개발용 설정만 사용한다. `--self-test`는 제품 단위 테스트이며 실제 경기가 아니다.

```powershell
python scripts/test-desync-lab.py
python scripts/desync-lab.py run scripts/desync-lab.example.json --out .tools/lab-run-001
python scripts/desync-lab.py compare player1.zip player2.zip --out .tools/lab-evidence-001
```

`native-replay-transport`는 기존 `scripts/test-replay.ps1`가 생성한
`.tools/ReplayTransportFixture.exe`를 사용한다. 없으면 격리된 probe로
`scripts/prepare-replay-fixture.py`를 먼저 실행한다. 임의의 게임 EXE로 대체하지 않는다.
네이티브 자식의 기록/재생 일치, 불일치 시 중단, 취소, 이벤트/폴링 경로를 검사한다.

설정의 argv는 `{build}`, `{python}`, `{root}`, `{out}`을 치환한다. 쉘을 사용하지 않는다.
임의 스크립트의 리터럴 중괄호는 `{{`와 `}}`로 이스케이프한다.
시험 어댑터가 두 실행의 trace ZIP을 생성한다면 `tracePair: ["left.zip", "right.zip"]`을
지정한다. `{out}` 안에 새로 생성된 파일만 인정하며 최초 상태 차이를 results.json에 기록한다.
시간 초과는 직접 실행한 시험 프로세스에만 적용된다. 임의 어댑터가 만든 자식들의 정리는
어댑터 책임이며, 도구는 프로세스 이름으로 게임을 일괄 종료하지 않는다.

## 결과 해석

- `results.json`: 반복별 baseline/candidate 결과, 종료 코드, 실행 시간, 파일 해시.
- 각 실행 폴더: stdout.txt, stderr.txt. 실제 경기 진단은 런처의 기존 진단 위치에도 남는다.
- `comparison.json`: 공통 프레임 수, 최초 유닛/명령/숨은 상태 차이, 버전 및 입력 해시.
- compare의 종료 코드 1은 차이 또는 비교 불가, 2는 입력 오류다.
- 같은 기록끼리 비교한 성공은 게임 수정 성공의 증거가 아니다.

## 현재 한계와 다음 연결 지점

이 도구는 전체 멀티플레이 엔진 재생기가 아니다. 기존 ZIP에는 시작 상태와 전체 명령이
없어 2026-11-03 경기를 재실행할 수 없다. 기록된 상태를 다시 비교하는 기능과 실제
네이티브 테스트 프로세스 실행은 별개다. 프로세스 테스트도 합성 부하이므로 유닛 236의
실제 길찾기를 재현하지 않는다. 실제 경기의 수정 효과는 아직 검증되지 않았다.

완전한 자동 재현에는 동일 틱의 엔진/경로/선택 상태 스냅샷, 전체 동기화 명령과
외부 API 경계를 재현하는 실행 어댑터가 추가로 필요하다. 이 어댑터는 tracePair 계약으로
연결할 수 있다. 이 기능을 구현하기 전에는 사용자 경기를 자동 재현했다고 보고하지 않는다.

리포트 ZIP, 메모리/게임 데이터, 실행 결과는 `.tools` 등 비공개 로컬 경로에 보관하고
저장소나 릴리스에 추가하지 않는다. 이 도구 자체는 업로드하지 않는다.
