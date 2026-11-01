# 2026-11-01 양측 멀티플레이 리포트 분석

두 보고서 모두 런처 0.3.49와 같은 HD EXE SHA256을 사용했다.
경기 clock 10363, sequence 10351에서 플레이어 1은 local=11/remote=45,
플레이어 2는 local=45/remote=11을 기록했다. fingerprintMismatches=61,
missingHistory=0이며 lobby connection은 당시 연결 상태였다.
네이티브 오류 임계치에서 Lost connection 화면이 표시되었다.
게임 프로세스의 최종 종료 코드는 0이었다. 이 사례를 접근 위반 크래시나
패킷 유실만으로 단정할 근거가 없다. 상태가 처음 갈라진 명령은 기존 ZIP으로
확정할 수 없으므로 동기화 문제 해결 완료로 표기하지 않는다.

0.3.50은 첫 오류 관찰 시 유닛 ID/type/owner/alive/x/y/health와 명령 패킷,
샘플 전후 simulation clock을 first-sync-divergence 이벤트에 기록한다.
비동기 읽기이므로 전후 clock이 다를 때는 같은 tick의 원자적 스냅샷이 아니다.
네이티브 오류 검사는 그대로 유지한다.

부가 수정: 첫 HUD 프레임의 소유 건물 카메라 초기화, 중립 자원 마커 색상,
공통/진영별 DIK 입력 재배치, 빈 음악 경로 기본값, Elca/EAD 채취 소리 분류.
검증: 컴파일된 x86 runtime 에뮬레이션, 정지된 원본/HD 자식 패치 적용,
자체 검사, 핫키 창 열기/저장 및 설정 파일의 4개 프로필 확인.
실제 양측 장시간 전투 및 현장 BGM 청취 검증은 미실시.
