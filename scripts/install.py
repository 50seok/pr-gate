#!/usr/bin/env python3
"""pr-gate를 새 레포에 부착한다. 로컬 클론 없이 gh CLI/API만으로 동작한다.

    python scripts/install.py <owner>/<repo> [--auto-merge] [--require-check]

사전 준비:
  - 이미 발급받은 CLAUDE_CODE_OAUTH_TOKEN 값을 로컬 셸 환경변수로 export/설정해둔다.
    (claude setup-token은 레포마다 다시 받을 필요 없다 — 계정 단위 토큰이라 재사용한다.)
    PowerShell: $env:CLAUDE_CODE_OAUTH_TOKEN = "<claude setup-token 출력값>"
  - 이 스크립트는 그 값을 읽어 gh secret set에 그대로 넘길 뿐, 화면에 출력하지 않는다.
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

PR_GATE_ROOT = Path(__file__).parent.parent
FILES = {
    ".github/workflows/pr-gate.yml": PR_GATE_ROOT / ".github/workflows/pr-gate.yml",
    "scripts/review.py": PR_GATE_ROOT / "scripts/review.py",
}


def gh(*args, input_bytes=None, check=True):
    r = subprocess.run(["gh", *args], input=input_bytes, capture_output=True, check=False)
    if check and r.returncode != 0:
        raise RuntimeError("gh %s 실패: %s" % (" ".join(args), r.stderr.decode("utf-8", "replace").strip()))
    return r


def put_file(repo, branch, path, local_path):
    """Contents API로 파일을 커밋한다. 이미 있으면 sha를 조회해 갱신, 없으면 새로 생성."""
    # gh api는 -f 필드를 주면 -X를 명시하지 않는 한 기본 메서드를 GET이 아니라 POST로
    # 바꾼다 — 명시 안 하면 이 존재 확인이 늘 404로 오탐하고, PUT이 기존 파일의 sha를
    # 못 받아 "sha wasn't supplied"로 실패한다(pokedex-rag 부착 때 실제로 겪음).
    existing = gh("api", "-X", "GET", "repos/%s/contents/%s" % (repo, path),
                  "-f", "ref=%s" % branch, check=False)
    sha = json.loads(existing.stdout).get("sha") if existing.returncode == 0 else None

    content_b64 = base64.b64encode(local_path.read_bytes()).decode("ascii")
    args = [
        "api", "-X", "PUT", "repos/%s/contents/%s" % (repo, path),
        "-f", "message=chore: pr-gate 부착 (%s)" % path,
        "-f", "content=%s" % content_b64,
        "-f", "branch=%s" % branch,
    ]
    if sha:
        args += ["-f", "sha=%s" % sha]
    gh(*args)
    print("[install] %s -> %s@%s" % (path, repo, branch))


def ensure_dev_branch(repo):
    r = gh("api", "repos/%s/branches/dev" % repo, check=False)
    if r.returncode == 0:
        print("[install] dev 브랜치 이미 있음")
        return
    default = json.loads(gh("api", "repos/%s" % repo).stdout)["default_branch"]
    base_sha = json.loads(gh("api", "repos/%s/git/refs/heads/%s" % (repo, default)).stdout)["object"]["sha"]
    gh("api", "-X", "POST", "repos/%s/git/refs" % repo, "-f", "ref=refs/heads/dev", "-f", "sha=%s" % base_sha)
    print("[install] dev 브랜치 생성 (%s에서 분기)" % default)


def register_secret(repo):
    import os
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if not token:
        print("[install] CLAUDE_CODE_OAUTH_TOKEN 환경변수가 없습니다.\n"
              "  PowerShell: $env:CLAUDE_CODE_OAUTH_TOKEN = \"<토큰>\"\n"
              "  (이미 발급받은 값을 재사용 — claude setup-token을 다시 받을 필요 없음)", file=sys.stderr)
        sys.exit(1)
    gh("secret", "set", "CLAUDE_CODE_OAUTH_TOKEN", "-R", repo, "--body", token, input_bytes=b"")
    print("[install] 시크릿 등록 완료 (값은 로그에 남기지 않음)")


def enable_auto_merge(repo):
    gh("api", "-X", "PATCH", "repos/%s" % repo, "-f", "allow_auto_merge=true")
    print("[install] auto-merge 활성화")


def require_check(repo):
    # pr-gate.yml의 job 이름이 GitHub check 컨텍스트 이름이 된다.
    payload = json.dumps({
        "required_status_checks": {"strict": True, "contexts": ["review"]},
        "enforce_admins": False,
        "required_pull_request_reviews": None,
        "restrictions": None,
    }).encode("utf-8")
    gh("api", "-X", "PUT", "repos/%s/branches/dev/protection" % repo, "--input", "-", input_bytes=payload)
    print("[install] dev 브랜치 required check 등록 (review)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    repo = sys.argv[1]
    flags = sys.argv[2:]

    ensure_dev_branch(repo)
    for path, local_path in FILES.items():
        put_file(repo, "dev", path, local_path)
    register_secret(repo)
    if "--auto-merge" in flags:
        enable_auto_merge(repo)
    if "--require-check" in flags:
        require_check(repo)

    print("\n[install] 완료. %s 에서 dev로 향하는 PR을 열면 pr-gate가 돕니다." % repo)


if __name__ == "__main__":
    main()
