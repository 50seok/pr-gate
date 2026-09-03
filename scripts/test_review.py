"""pr-gate 순수 로직 검증. 네트워크 호출 없음.

    python scripts/test_review.py
"""
import re
import sys

from review import FOLLOWUP_RE, _REVIEW_ENV_ALLOWLIST, classify, parse_review, render, render_too_big


def test_classify():
    assert classify(["docs/STATUS.md", "README.md"], 500) == "skip"
    assert classify(["app.py"], 10) == "small"
    assert classify(["app.py"], 100) == "big", "경계값 100줄은 big"
    assert classify(["app.py"], 99) == "small"
    # 민감 경로는 줄 수와 무관하게 big
    assert classify(["auth/login.py"], 3) == "big"
    assert classify(["migrations/V1__init.sql"], 1) == "big"
    assert classify(["docs/x.md", "app.py"], 5) == "small", "코드가 하나라도 섞이면 스킵 아님"
    assert classify([], 0) == "small", "파일 목록이 비어도 스킵으로 새지 않음"


def test_parse_review():
    raw = '{"summary": "괜찮음", "findings": []}'
    assert parse_review(raw) == {"summary": "괜찮음", "findings": []}

    # 코드펜스와 앞뒤 잡담이 붙어도 견딘다
    fenced = '설명입니다\n```json\n{"summary": "s", "findings": [{"grade": "P2", "file": "a.py"}]}\n```\n끝'
    assert parse_review(fenced)["findings"][0]["grade"] == "P2"

    # 등급이 이상한 항목은 버리고, P1이 먼저 오도록 정렬
    messy = '{"findings": [{"grade": "P3"}, {"grade": "잡담"}, {"grade": "P1"}]}'
    assert [f["grade"] for f in parse_review(messy)["findings"]] == ["P1", "P3"]

    try:
        parse_review("JSON이 전혀 없는 응답")
    except ValueError:
        pass
    else:
        raise AssertionError("JSON 없으면 ValueError여야 함")


def test_render():
    review = {"summary": "총평", "findings": [{"grade": "P1", "file": "a.py", "line": 3,
                                             "why": "널 참조", "fix": "가드 추가"}]}
    body = render(review, "big", "claude -p", "abc1234def", followup=None)
    assert "<!-- pr-gate -->" in body, "마커가 없으면 코멘트 upsert가 매번 새로 단다"
    assert "P1 1 · P2 0 · P3 0" in body
    assert "머지가 차단" in body
    assert "`a.py:3`" in body

    # 후속 이슈 번호는 마커로 되읽을 수 있어야 한다 (멱등성의 근거)
    with_followup = render(review, "small", "claude -p", "abc1234def", followup=42)
    assert FOLLOWUP_RE.search(with_followup).group(1) == "42"

    clean = render({"summary": "", "findings": []}, "small", "c", "0" * 40)
    assert "머지가 차단" not in clean, "P1이 없으면 차단 문구가 없어야 함"


def test_render_escapes_pipe_and_newline():
    """모델이 '|'나 개행이 든 텍스트를 뱉어도 마크다운 테이블이 깨지면 안 된다."""
    review = {"summary": "", "findings": [{"grade": "P1", "file": "a|b.py", "line": 1,
                                          "why": "행1|행2\n행3", "fix": "고침"}]}
    body = render(review, "small", "c", "0" * 40)
    table_lines = [l for l in body.splitlines() if l.startswith("| **P1**")]
    assert len(table_lines) == 1, "이스케이프 안 된 '|'나 개행이 테이블 행을 쪼갬"
    assert "\\|" in table_lines[0]


def test_review_env_allowlist_excludes_gh_token():
    """diff는 신뢰할 수 없는 입력이라, 리뷰 서브프로세스에 GH_TOKEN을 물려주면 안 된다."""
    assert "GH_TOKEN" not in _REVIEW_ENV_ALLOWLIST
    assert "PR_NUMBER" not in _REVIEW_ENV_ALLOWLIST


def test_render_too_big():
    body = render_too_big(["a.py", "b.py"], 123456, "abc1234def")
    assert "<!-- pr-gate -->" in body
    assert "쪼개" in body


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print("%d/%d PASS" % (len(tests), len(tests)))
