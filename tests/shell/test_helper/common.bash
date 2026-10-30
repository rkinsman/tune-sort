# Shared setup for the bats tests.
load 'test_helper/bats-support/load'
load 'test_helper/bats-assert/load'

REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
export REPO
