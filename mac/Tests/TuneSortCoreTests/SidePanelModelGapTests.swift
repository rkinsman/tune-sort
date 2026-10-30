import XCTest
@testable import TuneSortCore

@MainActor
final class SidePanelModelGapTests: XCTestCase {
    private func ts(_ a: String, _ t: String) -> TrackState {
        TrackState(track: Track(artist: a, title: t, persistentId: "id-\(a)-\(t)"), state: .unknown)
    }

    private func make(extra: (inout FakeHelperAPI.State) -> Void = { _ in }) async throws
        -> (SidePanelModel, AppModel, FakeHelperAPI) {
        let api = FakeHelperAPI()
        api.configure { s in
            s.tracks["PL"] = .success([self.ts("A", "One"), self.ts("B", "Two")])
            extra(&s)
        }
        let app = AppModel(api: api)
        await app.select(.playlist("PL"))
        app.selectedRowID = try XCTUnwrap(app.rows.first { $0.artist == "A" }).id
        return (SidePanelModel(api: api, app: app), app, api)
    }

    private func waitUntil(_ what: String, timeout: Double = 5, _ cond: () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while !cond() {
            if Date() > deadline { XCTFail("timed out waiting for \(what)"); throw TestTimeout() }
            try await Task.sleep(nanoseconds: 2_000_000)
        }
    }

    // 1. Non-bad_tuning describe errors go to the banner.
    func testMusicErrorFromDescribeSetsBannerAndLeavesResultNil() async throws {
        let (p, app, _) = try await make { s in
            s.describeResults["x"] = .failure(ClientError.helper(kind: "music", message: "Music is not running"))
        }
        p.typed = "x"
        try await withTimeout { await p.typedChanged() }
        XCTAssertEqual(app.banner?.kind, .music)
        XCTAssertNil(p.typedResult)
    }

    func testHelperExitedFromDescribeSetsBannerAndLeavesResultNil() async throws {
        let (p, app, _) = try await make { s in
            s.describeResults["x"] = .failure(ClientError.helperExited(stderrTail: ["dead"]))
        }
        p.typed = "x"
        try await withTimeout { await p.typedChanged() }
        XCTAssertEqual(app.banner?.kind, .helperExited)
        XCTAssertNil(p.typedResult)
    }

    // 3. No set/delete while a run is active.
    func testActionsMakeNoCallsWhileRunIsActive() async throws {
        let (p, app, api) = try await make()
        let task = Task { await app.preview() }
        try await api.waitForSort()
        try await waitUntil("running") {
            if case .running = app.runState { return true }
            return false
        }
        let before = api.calls
        let m = MatchInfo(tuning: TuningInfo(name: "Drop D", playlistName: "p", notes: ""), source: "web",
                          url: "u", matchedArtist: "m", matchedTitle: "t", exact: true)
        p.typed = "Drop D"
        try await withTimeout { await p.save() }
        try await withTimeout { await p.use(m) }
        try await withTimeout { await p.clear() }
        XCTAssertEqual(api.calls, before, "no set/delete (or refresh) while a run is active")

        api.yield(.finished(Report(cancelled: false, createdPlaylists: [], added: [:], alreadyPresent: [:],
                                   review: [], lookupFailed: [], addErrors: [])))
        api.finishStream()
        try await withTimeout { await task.value }
    }

    // 4. save() invalidates a pending describe: its late reply must not change typedResult.
    func testSaveInvalidatesPendingDescribe() async throws {
        let (p, _, api) = try await make()
        let gate = Gate()
        api.configure { $0.describeGates["Dro"] = gate }
        p.typed = "Dro"
        let pending = Task { await p.typedChanged() }
        try await api.waitForCall("describe:bass:Dro")

        p.typed = "Drop D"
        try await withTimeout { await p.save() }
        XCTAssertNil(p.typedResult)

        gate.open()
        try await withTimeout { await pending.value }
        XCTAssertNil(p.typedResult, "reply for earlier text must not apply after save started")
    }
}
