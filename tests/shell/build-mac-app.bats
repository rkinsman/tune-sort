#!/usr/bin/env bats
# Tests for scripts/build-mac-app.

setup() {
  load 'test_helper/common'
  SCRIPT="$REPO/scripts/build-mac-app"
}

# Make a directory of symlinks to the given commands and print its path.
make_tool_dir() {
  local dir="$BATS_TEST_TMPDIR/tools" tool path
  mkdir -p "$dir"
  for tool in "$@"; do
    path="$(command -v "$tool")" || continue
    ln -sf "$path" "$dir/$tool"
  done
  echo "$dir"
}

# Assert the bundle at $1 carries a valid app icon referenced from Info.plist.
assert_icon() {
  local out="$1" icon="$1/Contents/Resources/AppIcon.icns"
  [ -s "$icon" ]
  run head -c 4 "$icon"
  assert_output "icns"
  run /usr/libexec/PlistBuddy -c 'Print :CFBundleIconFile' "$out/Contents/Info.plist"
  assert_success
  assert_output "AppIcon"
}

# Build a fake repo in the test tmp dir containing a copy of the script and
# the real Info.plist (and, if $1 is "icon", a dummy AppIcon.icns), with fake
# swift/codesign on PATH, and an existing bundle at <fake>/Old.app.
make_fake_repo() {
  FAKE="$BATS_TEST_TMPDIR/fake"
  mkdir -p "$FAKE/scripts" "$FAKE/mac/Resources" "$FAKE/bin" "$FAKE/Old.app/Contents"
  cp "$REPO/scripts/build-mac-app" "$FAKE/scripts/build-mac-app"
  chmod +x "$FAKE/scripts/build-mac-app"
  cp "$REPO/mac/Resources/Info.plist" "$FAKE/mac/Resources/Info.plist"
  if [ "${1:-}" = "icon" ]; then
    printf 'icns' > "$FAKE/mac/Resources/AppIcon.icns"
  fi
  printf '#!/bin/sh\nexit 0\n' > "$FAKE/bin/swift"
  printf '#!/bin/sh\nexit 0\n' > "$FAKE/bin/codesign"
  chmod +x "$FAKE/bin/swift" "$FAKE/bin/codesign"
  : > "$FAKE/Old.app/Contents/marker"
}

BASIC_TOOLS=(bash sh env dirname basename mkdir rm cp mv cat pwd ls ln chmod touch sed grep awk tr uname mktemp cut head tail sort printf readlink realpath find xargs plutil)

@test "--help prints usage mentioning --out and exits 0" {
  run "$SCRIPT" --help
  assert_success
  assert_output --partial "--out"
  assert_output --partial "sage"
}

@test "-h prints usage mentioning --out and exits 0" {
  run "$SCRIPT" -h
  assert_success
  assert_output --partial "--out"
}

@test "--help creates no bundle at the --out location" {
  run "$SCRIPT" --out "$BATS_TEST_TMPDIR/Help.app" --help
  assert_success
  [ ! -e "$BATS_TEST_TMPDIR/Help.app" ]
}

@test "unknown argument exits 2 and names it" {
  run "$SCRIPT" --bogus-flag
  assert_failure 2
  assert_output --partial "--bogus-flag"
}

@test "--out without a value is an error" {
  run "$SCRIPT" --out
  assert_failure
  refute_output --partial "Built"
}

@test "missing swift is reported before building" {
  local dir
  dir="$(make_tool_dir "${BASIC_TOOLS[@]}" codesign)"
  [ -x "$dir/codesign" ]
  [ ! -e "$dir/swift" ]
  PATH="$dir" run "$SCRIPT" --out "$BATS_TEST_TMPDIR/NoSwift.app"
  assert_failure
  assert_output --partial "swift"
  [ ! -e "$BATS_TEST_TMPDIR/NoSwift.app" ]
}

@test "missing codesign is reported before building" {
  local dir
  dir="$(make_tool_dir "${BASIC_TOOLS[@]}" swift)"
  [ -x "$dir/swift" ]
  [ ! -e "$dir/codesign" ]
  PATH="$dir" run "$SCRIPT" --out "$BATS_TEST_TMPDIR/NoSign.app"
  assert_failure
  assert_output --partial "codesign"
  [ ! -e "$BATS_TEST_TMPDIR/NoSign.app" ]
}

@test "missing AppIcon.icns fails before touching an existing bundle" {
  make_fake_repo
  [ ! -e "$FAKE/mac/Resources/AppIcon.icns" ]
  PATH="$FAKE/bin:$PATH" run "$FAKE/scripts/build-mac-app" --out "$FAKE/Old.app"
  assert_failure
  assert_output --partial "AppIcon.icns"
  [ -e "$FAKE/Old.app/Contents/marker" ]
}

@test "missing Info.plist fails before touching an existing bundle" {
  make_fake_repo icon
  rm "$FAKE/mac/Resources/Info.plist"
  PATH="$FAKE/bin:$PATH" run "$FAKE/scripts/build-mac-app" --out "$FAKE/Old.app"
  assert_failure
  assert_output --partial "Info.plist"
  [ -e "$FAKE/Old.app/Contents/marker" ]
}

@test "full build produces a signed bundle with icon, and can be re-run" {
  local out="$BATS_TEST_TMPDIR/Out.app"

  run "$SCRIPT" --out "$out"
  assert_success
  assert_output --partial "Built"

  [ -x "$out/Contents/MacOS/TuneSort" ]
  [ -f "$out/Contents/Info.plist" ]

  run /usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$out/Contents/Info.plist"
  assert_success
  assert_output "com.rkinsman.TuneSort"

  run /usr/libexec/PlistBuddy -c 'Print :NSAppleEventsUsageDescription' "$out/Contents/Info.plist"
  assert_success
  assert_output "TuneSort controls Music to read your playlists and add songs to tuning playlists."

  assert_icon "$out"

  run codesign -v "$out"
  assert_success

  # Re-run to the same location: replaces the bundle and succeeds.
  run "$SCRIPT" --out "$out"
  assert_success
  assert_output --partial "Built"
  [ -x "$out/Contents/MacOS/TuneSort" ]
  assert_icon "$out"
  run codesign -v "$out"
  assert_success
}

@test "runs from another working directory" {
  cd "$BATS_TEST_TMPDIR"
  run "$SCRIPT" --help
  assert_success
  assert_output --partial "--out"
}
