# amagadon

아마게돈 Windows 런처. 게임 데이터는 포함하지 않습니다.

## 실행

`dist/AmagadonLauncher.exe`를 실행하고 게임 설치 폴더를 지정합니다.
기본 경로: `C:\Users\seo\Downloads\armaggeddon\armaggeddon`.
배포 ZIP은 전체를 풀어 사용합니다. `compat`, `apply-update.ps1` 파일도 필요합니다.

- **게임 실행**: 게임 폴더를 작업 디렉터리로 지정해 실행합니다.
- **맵 에디터 실행**: 런처가 적용한 래퍼를 원복한 뒤 ACE를 실행합니다. ACE에서 cnc-ddraw를 사용하면 화면이 깨져 별도로 처리합니다.
- **내부 해상도**: 원본 800×600 또는 실제 1024×768(4:3) 시야 확장 시험 모드. 별도 Armageddon.HD-preview.exe를 생성하며 원본은 보존합니다. 기본 출력은 전체 화면 늘리기(레터박스 없음)입니다. 와이드 모니터에서는 가로로 늘어납니다. 출력 확대·종횡비·창/전체 화면·렌더러·커서 제한도 선택할 수 있습니다.
- **그래픽 호환성**: cnc-ddraw 7.1.0, 단일 CPU, 프레임 제한, 비독점 창 모드. 모든 크래시 해결을 보장하지 않습니다.
- **호환성 복원**: 원래 DLL/설정을 복원합니다. 백업은 게임 폴더 `LauncherBackups`에 유지됩니다.
- **업데이트**: 이 저장소의 최신 GitHub Release를 확인합니다. ZIP과 SHA-256 검증 파일이 있어야 설치됩니다. 기존 파일을 백업한 뒤 런처를 교체합니다.
- **패치노트**: 동봉한 PATCHNOTES.md를 표시합니다.

설정/로그: `%LOCALAPPDATA%\AmagadonLauncher`. 게임과 에디터는 동시에 실행하지 않습니다.

## 게임 리플레이 (0.3.0-preview · 실험)

1. 내부 해상도 **1024×768**을 선택하고 **싱글플레이 리플레이 자동 기록**을 켭니다.
2. 게임을 실행해 싱글플레이를 진행합니다. 대전 종료 또는 정상 게임 종료 후 `.agr` 파일을 자동 저장합니다.
3. **리플레이 저장 폴더**에서 파일을 확인하고 **리플레이 재생**으로 선택합니다. 재생은 시작 상태를 자동으로 불러옵니다. 중단할 때는 런처의 **재생 중단**을 누릅니다.

저장 위치는 `%LOCALAPPDATA%\AmagadonLauncher\Replays`입니다. 게임 데이터와 패치 버전, 사용자 맵이 기록 당시와 일치해야 합니다. 리플레이는 영상 파일이 아닙니다. 초기 저장본과 프레임별 입력·명령을 사용합니다. 시작 시 게임 저장·불러오기 과정을 거쳐 상태를 맞추며, 실행 중인 기존 게임에는 연결하지 않습니다. 런처는 게임 종료까지 열어두어야 합니다.

멀티플레이 및 800×600 기록은 지원하지 않습니다. 수동 불러오기는 새 기록으로 나뉘며, 재생 중 사용자 저장·불러오기 명령은 중단 처리합니다. 기록 용량 한도(명령 512MiB 또는 100만 프레임)에 도달하면 자동 기록을 중단합니다. 비정상 종료된 기록은 게임 폴더의 `LauncherReplayWork`에 남으며 완성된 리플레이 목록에 넣지 않습니다. 실제 전투·장시간 재현 검증은 아직 남아 있습니다.

## 빌드 및 검사

Windows의 .NET Framework 4.x C# 컴파일러를 사용합니다. 별도 SDK 설치가 필요 없습니다.

```powershell
.\scripts\fetch-compat.ps1
.\scripts\build.ps1
$test = Start-Process .\dist\AmagadonLauncher.exe -ArgumentList '--self-test' -PassThru -Wait -WindowStyle Hidden
if ($test.ExitCode -ne 0) { throw 'Self-test failed' }
```

자동 검사: 해상도 설정, 반복 적용 시 원본 백업 유지, 기존 DLL 및 미존재 DLL 복원, 필수 게임 파일 누락.
0.3.0-preview는 싱글플레이 리플레이 기록·재생을 추가했습니다. 기계어 검증 22개 범주와 별도 프로세스의 기록·재생 검사를 통과했지만 실제 전투 재현은 미검증입니다. [HD 분석 및 검증 범위](docs/hd-resolution-status.md)를 참고하세요. 시험 모드는 기본적으로 꺼져 있습니다.

`--verify-native "원본 EXE 경로"`는 패치 결과와 시험본 생성·재사용·제거, 변조 거부, 원본 보존을 검사합니다. 배포 ZIP에는 버전별 AmagadonLauncher-0.3.0-preview.exe도 포함됩니다. 기존 시험본은 게임 종료 후 다음 실행에서 해시 확인·백업 후 교체됩니다.

## 릴리스

버전은 `src/Launcher.cs`와 PATCHNOTES.md에서 변경합니다. `v0.1.1` 같은 버전 태그를 푸시하면 GitHub Actions가 빌드하고 ZIP/체크섬을 GitHub Release에 올립니다. 최초 0.1.0은 로컬 빌드로 제공됩니다.

참고 프로젝트: [FunkyFr3sh/cnc-ddraw](https://github.com/FunkyFr3sh/cnc-ddraw), MIT 라이선스. 바이너리는 버전과 SHA-256을 고정해 가져옵니다. 원본 게임 실행 파일은 보존하며 배포하지 않습니다. HD 레시피는 해당 EXE를 직접 분석한 것입니다. main 푸시는 빌드 아티팩트를 만들며 preview의 안정판 Release는 게시하지 않았습니다.
