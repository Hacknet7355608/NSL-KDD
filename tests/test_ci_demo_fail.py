"""故意的失败用例：仅用于演示 CI 失败时 PR 无法合并。演示后删除。"""


def test_intentionally_failing():
    assert False, "CI demo: 这条用例故意失败"
