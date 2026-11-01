# 0.3.69 Windows 검증 및 한계

## 적용

- origin/main `b303c87` / v0.3.68 확인 후 `codex/claude-0.3.69-lag`에서 패치를 적용했다.
- 소스 충돌은 없었다. 안내된 4개 소스/문서 외에 패치에 포함된 Python .pyc 파일은
  `git am --exclude='scripts/__pycache__/*'`로 제외했다. 기존 미추적 캐시와 사용자 파일은 보존했다.
- 패치 뒤 Windows 검토에서 필요한 스레드 수명 보완과 테스트 보완을 별도 커밋으로 추가한다.

## Watch 검토와 보완

| 공유 상태/자원 | 처리 |
|---|---|
| DebugActiveProcess / WaitForDebugEvent / ContinueDebugEvent / DebugActiveProcessStop | 같은 전용 디버거 스레드에서 호출 |
| 디버그 이벤트 버퍼 | 디버거 스레드 내부에서 생성·해제. 텔레메트리 예외로 먼저 해제되는 경로 제거 |
| Process 객체 | 텔레메트리와 디버거가 별도 객체 사용. Refresh/Modules 캐시 공유 회피 |
| lastConstructionGuard 및 trace 파일 | traceGate 안에서 읽기·갱신·저장 |
| handledExceptions | Interlocked 증가/읽기 |
| 마지막 예외 코드·주소 | 하나의 64비트 값으로 합쳐 Interlocked 교환/읽기. 서로 다른 이벤트의 코드·주소 혼합 방지 |
| sawUnhandledException / debugExit | 디버거만 기록, 주 스레드는 Join 뒤 최종 보고에서 읽기 |
| origins | 잠금, 최대 64개. reportedOrigins는 텔레메트리 스레드만 접근 |
| 연결 완료 | ManualResetEvent로 attachResult 전달 |
| 종료/감시 오류 | stop 신호 → 디버거 스레드에서 detach → Join → 이벤트 객체 해제 |
| 연결 실패 | telemetry-only로 계속 수집. 다른 디버거를 해제하지 않음 |

패치 원안은 텔레메트리 스레드가 예외로 종료될 때 외부 finally에서 버퍼를 해제할 수 있었다.
디버거가 아직 그 버퍼를 사용하는 경우를 막도록 소유권을 옮겼다. 백그라운드 스레드의 초기
연결 예외도 처리하고, 디버거 스레드가 조기에 끝나면 살아 있는 프로세스의 텔레메트리는 유지한다.

초기 디버거 연결 breakpoint만 기존처럼 처리하며, 나머지 예외는 기존 `0x80010001 NOT_HANDLED`를
유지한다. 두 번째 기회 예외의 덤프 수집과 충돌/종료 시점 캡처도 유지했다.
충돌/종료 캡처는 의도적으로 정지된 상태에서 수행하므로 디스크 작업 없는 경로라고 주장하지 않는다.
동기화 검사, 오류 카운터, 게임 승패 판정은 수정하지 않았다.

## 동일 부하 비교

Windows x86 fixture에서 합성 C++ 형태의 예외를 7초 동안 발생시켰다. 테스트는 순차 실행했고,
기존 0.3.68 배포 EXE와 새 0.3.69 EXE에 동일한 fixture를 사용했다.
표의 최대 간격은 예외 처리와 의도한 2ms 간격을 포함하는 반복 간격이며, 디버거의 순수 정지 시간만은 아니다.

| 버전 | 실행 | 최대 간격 ms | 반복 횟수 | 150ms 미만 |
|---|---:|---:|---:|---|
| 0.3.68 | 1 | 17 | 3385 | 통과 |
| 0.3.68 | 2 | 17 | 3376 | 통과 |
| 0.3.68 | 3 | 15 | 3376 | 통과 |
| 0.3.69 | 1 | 6 | 3391 | 통과 |
| 0.3.69 | 2 | 7 | 3392 | 통과 |
| 0.3.69 | 3 | 6 | 3375 | 통과 |
| 0.3.69 | 최종 배포 빌드 | 7 | 3391 | 통과 |

0.3.68도 통과했다. 테스트에서는 새 버전의 최대 간격이 작았지만, 실제 경기 렉 해결의 증거로
일반화하지 않는다. fixture는 게임의 실제 5.6MB trace 읽기 경로를 활성화하지 않으며,
실제 게임 프레임 시간/네트워크 지연/FPS 측정도 아니다.

처음에는 패치 그대로 `Sleep(2)`를 사용해 7초에 460회, 최대 17ms였다. Windows 타이머 간격의
영향으로 1,000회 기준에 미달해 테스트가 실패했다. 기준을 낮추지 않고 Stopwatch 기준 2ms
SpinWait로 바꿨으며, 위 표의 양 버전 모두 그 수정된 동일한 부하를 사용했다.
0.3.68은 origin 이벤트가 없으므로 `-Baseline` 모드에서는 지연을 측정하고 그 차이를 명시한다.

## 테스트

- `test-diagnostics.ps1`: clean, burst, latency, crash 모두 통과.
  예외 집계, kernel32.dll 메타데이터 소유권 기록, 미처리 .NET 예외 덤프와 ExceptionStream 검증.
- 추가 lifecycle 테스트: 별도의 시험 디버거가 붙은 자식에 대해 telemetry-only 수집/종료 통과.
  ready 파일 쓰기를 의도적으로 실패시켜 감시 스레드가 종료되어도 자식이 죽거나 멈추지 않고
  두 스레드가 정리되는 것을 확인했다.
- lifecycle 첫 시도에서는 자식 CLR 초기화 전에 붙어 MainModule 읽기가 실패했다.
  시험 자식의 초기화 완료 신호를 기다리도록 fixture를 보완한 뒤 통과했다.
- `test-selection-runtime.py`: 빌드 EXE 내 설치 후크/재배치, 실제 MFP의 AI 계획 9종 포함 통과.
- `test-sync-trace-reports.py`, `test-game-music.py`, `test-replay.ps1` 통과.
- `test-input-recovery.py`: HD 전체 입력/레이아웃 통과. 원본 EXE는 별도의 `--input-only` 통과이며
  이를 원본 전체 레이아웃 검증으로 보고하지 않는다.
- `test-update.ps1`: 최종 패키지의 설치/체크섬/설정 보존/잠긴 파일 롤백/인계/재시작 확인.
- Windows csc 빌드. 기존 ZIP/체크섬/매니페스트 형식과 `AmagadonLauncher-0.3.69.exe` 엔트리포인트 유지.

## 실제 경기 확인 여부

5분 이상 실제 멀티플레이 또는 두 인스턴스 경기는 수행하지 않았다. 따라서 실제 경기의
first-chance-summary 발생 수, origin 모듈, 5초 구간별 cpuMs 및 0.3.68 대비 결과는 미측정이다.
전달받은 03:21 경기의 상관계수 -0.9 분석을 이번 검증에서 독립적으로 재현한 것은 아니다.

fixture의 kernel32.dll 기록은 해당 모듈 안의 주소를 합성 ThrowInfo로 지정한 시험이다.
kernel32.dll이 실제 게임의 문제 원인이라는 뜻이 아니다. 실제 first-chance-origin 역시
예외 메타데이터가 속한 모듈을 가리키며, 호출 스택 없이 예외를 일으킨 프로그램을 단정할 수 없다.

사용자 게임/서버는 종료하지 않았고, 테스트가 만든 자식만 정리했다.
리포트·덤프·토큰·게임 데이터와 Python 캐시는 커밋 및 릴리스 패키지에 포함하지 않는다.
