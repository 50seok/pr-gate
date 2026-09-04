# pr-gate

PR을 열면 diff를 AI 에이전트 CLI에 태워 **P1~P3 등급**을 매기고, P1이 있으면 머지를 막는 GitHub Actions 봇.

API 키를 쓰지 않는다. Claude 구독 토큰으로 돈다.

## 동작

```
PR 열림(base=dev 또는 main)
  ├ Draft 상태           → 리뷰 생략 (Ready for review로 바꿀 때까지)
  ├ fork에서 온 PR       → 리뷰 생략 (시크릿이 안 넘어옴)
  ├ 문서만 변경          → 리뷰 생략 (한도 소모 0)
  ├ diff 8만자 초과      → "PR을 쪼개세요" + 머지 차단
  └ 그 외                → 티어 판정 → 에이전트 CLI 리뷰
                            ├ P1 있음      → job 실패 → 머지 차단 + ai:p1-blocked
                            ├ 민감 영역     → job 실패 → 자동머지 보류 + ai:needs-human
                            └ 둘 다 아님    → check 통과 → GitHub auto-merge가 머지
```

### 검수 지점은 두 곳이다

`dev` 대상 PR만 보는 게 아니라 **`dev`→`main` 승격 PR도 검수한다.** 승격 시점의 누적 diff는
개별 PR 어디서도 본 적 없는 조합이라, 각각 P1이 없어도 합치면 회귀가 날 수 있다. 배포 직전이
가장 비싼 지점이므로 여기를 비워두지 않는다. 단 `main`에는 auto-merge를 켜지 않으므로,
통과해도 머지는 언제나 사람이 한다.

**작업 중인 PR은 Draft로 열어두세요.** 커밋을 반복해서 밀 때마다 리뷰가 도는데, 이 리뷰는
본인 Claude 구독의 주간 사용량 한도를 다른 Claude Code 세션과 공유한다. Draft 상태에선
아예 안 돌고, "Ready for review"로 바꾸는 순간부터 돈다.

**이 봇은 머지하지 않는다.** check를 통과/실패시킬 뿐이고, 실제 머지는 GitHub의 네이티브
auto-merge가 한다. 봇에 머지 권한을 주지 않아도 되고 머지 로직도 없다.

### 티어

| 조건 | 실행 명령 |
|---|---|
| `docs/**`·`*.md`만 변경 | 리뷰 안 함 |
| 인증·시크릿·DB 관련 경로 포함 | `REVIEW_CMD_BIG` |
| 변경 100줄 이상 | `REVIEW_CMD_BIG` |
| 그 외 | `REVIEW_CMD_SMALL` |

### 라벨

- `ai:p1-blocked` — P1 발견. 머지 차단
- `ai:p2-followup` — P2 발견. 후속 이슈를 **정확히 1개** 자동 생성
- `ai:needs-human` — 인증·시크릿·DB 등 민감 경로 포함. **P1이 0이어도** check를 실패시켜
  자동머지를 보류한다. AI 리뷰는 P1을 놓칠 수 있고(이 봇이 자기 P1을 2라운드에 나눠 찾은
  실측이 있다), 놓쳤을 때 비용이 큰 영역은 "AI 통과 = 머지"가 아니라 "AI 통과 = 사람 검토
  대기"여야 하기 때문. **사람은 그대로 직접 머지할 수 있다** — 막는 건 자동머지뿐이다

후속 이슈 중복 방지는 검색에 기대지 않는다. 생성한 이슈 번호를 봇이 쓴 PR 코멘트에
`<!-- pr-gate-followup:N -->` 마커로 남기고, 다음 실행 때 그 마커를 읽는다.

## 설치

### 1회만 — 토큰 발급 (계정 단위, 레포 단위 아님)

```bash
claude setup-token   # Claude 구독 필요. 나온 값을 로컬 셸에 보관해둔다.
```

이 토큰은 **여러 레포에 재사용**한다. 새 프로젝트마다 다시 받을 필요 없다.

### 새 레포마다 — `install.py` 한 줄

```bash
$env:CLAUDE_CODE_OAUTH_TOKEN = "<발급받은 값>"     # PowerShell. 이 셸에서만 유효
python scripts/install.py <owner>/<repo> --auto-merge --require-check
```

dev 브랜치 생성 → 워크플로우 파일 커밋 → 시크릿 등록 → (선택) auto-merge·required check까지
로컬 클론 없이 한 번에 끝낸다. 토큰 값은 로컬 환경변수에서 읽어 `gh secret set`에 그대로
넘길 뿐, 어디에도 출력하지 않는다.

플래그 없이 실행하면 auto-merge/required check는 건너뛴다 — 처음엔 라벨만 관찰하고
싶을 때. 나중에 다시 실행해서 켤 수 있다(멱등적).

## 다른 에이전트로 바꾸기

모델 SDK를 코드에 박지 않았다. 워크플로우의 환경변수 두 줄만 바꾼다.

```yaml
REVIEW_CMD_SMALL: codex exec
REVIEW_CMD_BIG: codex exec --model o3
```

프롬프트를 stdin으로 받아 JSON을 stdout으로 뱉는 CLI면 무엇이든 된다.

## 테스트

```bash
python scripts/test_review.py
```

네트워크 호출 없이 티어 판정·JSON 파싱·코멘트 렌더링만 검증한다. pytest 불필요.

## 알려진 한계

- **diff는 신뢰할 수 없는 입력이다.** 리뷰 CLI에 Read/Grep 권한을 준 상태라, PR 작성자가
  diff 안에 프롬프트 인젝션을 심으면 파일시스템·프로세스 환경의 일부를 읽어 findings
  텍스트에 담을 수 있다. 서브프로세스 env는 화이트리스트로 최소화했고(`CLAUDE_CODE_OAUTH_TOKEN`만
  남음 — 리뷰 CLI 인증에 필요해서 뺄 수 없다), `.git/config` 자격증명도 `persist-credentials: false`로
  없앴지만, **완전한 차단은 아니다.** 대신 `redact_secrets()`가 공개 코멘트/이슈로 나가기 직전에
  시크릿 모양 문자열을 마지막으로 걸러낸다 — 입력 경로를 다 막기보다 출력을 막는 쪽. 알려진
  토큰 형식만 잡으므로 100% 방어는 아니다. 더 강한 격리(도구 접근 자체를 없애거나 별도
  샌드박스 job으로 분리)는 개인 포트폴리오 규모에선 과함 — 트래픽·신뢰 범위가 커지면 재검토
- **주간 사용량 한도를 본인 Claude Code 세션과 공유한다.** 봇이 많이 돌면 본인 작업 한도가 줄어든다. 문서 전용 PR 스킵 규칙이 그래서 중요하다
- **fork PR은 검수하지 않는다.** 시크릿이 넘어오지 않아 인증이 안 된다 — 개인 레포에서
  이건 동시에 트리거 표면 제한이기도 하다: 그 레포에 브랜치를 밀 수 있는 사람(=본인)만
  리뷰를 발생시킬 수 있다는 뜻
- **base가 `dev`인 PR만 본다.** `main` 자동 머지는 배포를 건드리므로 사람이 승격한다
- **draft PR은 검수하지 않는다.** Ready for review로 바꾸기 전까지 커밋을 아무리 밀어도
  안 돈다 — 위 사용량 한도 공유 항목 때문에 넣은 안전장치
- **킬스위치는 claude.ai에 있다.** `CLAUDE_CODE_OAUTH_TOKEN`을 폐기하면 이 봇이 붙어 있는
  모든 레포에서 즉시 멈춘다. 워크플로우 파일을 지울 필요 없음
- 리뷰 품질은 검증된 적 없다. **처음에는 auto-merge를 켜지 말고 라벨만 관찰**할 것
