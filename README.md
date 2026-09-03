# pr-gate

PR을 열면 diff를 AI 에이전트 CLI에 태워 **P1~P3 등급**을 매기고, P1이 있으면 머지를 막는 GitHub Actions 봇.

API 키를 쓰지 않는다. Claude 구독 토큰으로 돈다.

## 동작

```
PR 열림(base=dev)
  ├ 문서만 변경          → 리뷰 생략 (한도 소모 0)
  ├ diff 8만자 초과      → "PR을 쪼개세요" + 머지 차단
  └ 그 외                → 티어 판정 → 에이전트 CLI 리뷰
                            ├ P1 있음 → job 실패 → 머지 차단 + ai:p1-blocked
                            └ P1 없음 → check 통과 → GitHub auto-merge가 머지
```

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

후속 이슈 중복 방지는 검색에 기대지 않는다. 생성한 이슈 번호를 봇이 쓴 PR 코멘트에
`<!-- pr-gate-followup:N -->` 마커로 남기고, 다음 실행 때 그 마커를 읽는다.

## 설치

1. **토큰 발급** — 로컬에서 `claude setup-token` (Claude 구독 필요)
2. **레포 시크릿 등록** — `CLAUDE_CODE_OAUTH_TOKEN`
3. **파일 복사** — `.github/workflows/pr-gate.yml`, `scripts/review.py`를 대상 레포에
4. **레포 설정 2개**
   - Settings → General → **Allow auto-merge** 켜기
   - Settings → Branches → `dev` 보호 규칙에 `pr-gate / review`를 **required check**로 등록

이후 PR에서 `gh pr merge --auto --squash`를 걸어두면 P1 없는 PR은 사람 손 없이 머지된다.

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
- **fork PR은 검수하지 않는다.** 시크릿이 넘어오지 않아 인증이 안 된다
- **base가 `dev`인 PR만 본다.** `main` 자동 머지는 배포를 건드리므로 사람이 승격한다
- 리뷰 품질은 검증된 적 없다. **처음에는 auto-merge를 켜지 말고 라벨만 관찰**할 것
