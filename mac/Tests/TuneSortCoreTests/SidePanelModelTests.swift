import XCTest
@testable import TuneSortCore

@MainActor
final class SidePanelModelTests: XCTestCase {
    private let dropD = TuningInfo(name: "Drop D", playlistName: "Bass – Drop D", notes: "D A D G")
    private let eStd = TuningInfo(name: "E Standard", playlistName: "Bass – E Standard", notes: "E A D G")

    private func match(_ t: TuningInfo) -> MatchInfo {
        MatchInfo(tuning: t, source: "web", url: "u", matchedArtist: "m", matchedTitle: "t", exact: true)
    }
    private func ts(_ a: String, _ t: String, _ s: CacheState) -> TrackState {
        TrackState(track: Track(artist: a, title: t, persistentId: "id-\(a)-\(t)"), state: s)
    }

    private func waitUntil(_ what: String, timeout: Double = 5, _ cond: () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while !cond() {
            if Date() > deadline { XCTFail("timed out waiting for \(what)"); throw TestTimeout() }
            try await Task.sleep(nanoseconds: 2_000_000)
        }
    }

    /// Playlist "PL" with A/One (state given) and B/Two unknown; A/One selected.
    private func make(_ state: CacheState = .unknown,
                      extra: (inout FakeHelperAPI.State) -> Void = { _ in }) async throws
        -> (SidePanelModel, AppModel, FakeHelperAPI) {
        let api = FakeHelperAPI()
        api.configure { s in
            s.tracks["PL"] = .success([self.ts("A", "One", state), self.ts("B", "Two", .unknown)])
            extra(&s)
        }
        let app = AppModel(api: api)
        await app.select(.playlist("PL"))
        let id = try XCTUnwrap(app.rows.first { $0.artist == "A" }).id
        app.selectedRowID = id
        return (SidePanelModel(api: api, app: app), app, api)
    }

    private func indexOf(_ api: FakeHelperAPI, _ prefix: String, after: Int = -1) -> Int? {
        api.calls.indices.first { $0 > after && api.calls[$0].hasPrefix(prefix) }
    }

    // MARK: typed tuning

    func testValidTypedTuningShowsPlaylistName() async throws {
        let (p, _, api) = try await make()
        p.typed = "Drop D"
        try await withTimeout { await p.typedChanged() }
        XCTAssertTrue(api.calls.contains("describe:bass:Drop D"))
        guard case .success(let info)? = p.typedResult else {
            return XCTFail("expected success, got \(String(describing: p.typedResult))")
        }
        XCTAssertEqual(info.playlistName, "bass – Drop D")
    }

    func testInvalidTypedTuningShowsBadTuningMessage() async throws {
        let (p, _, _) = try await make { s in
            s.describeResults["zzz"] = .failure(ClientError.helper(kind: "bad_tuning", message: "Can't parse 'zzz'"))
        }
        p.typed = "zzz"
        try await withTimeout { await p.typedChanged() }
        guard case .failure(.helper(let kind, let message))? = p.typedResult else {
            return XCTFail("expected bad_tuning failure, got \(String(describing: p.typedResult))")
        }
        XCTAssertEqual(kind, "bad_tuning")
        XCTAssertEqual(message, "Can't parse 'zzz'")
    }

    func testStaleDescribeReplyIsIgnored() async throws {
        let (p, _, api) = try await make()
        let gate = Gate()
        api.configure { $0.describeGates["Dro"] = gate }

        p.typed = "Dro"
        let old = Task { await p.typedChanged() }
        try await api.waitForCall("describe:bass:Dro")

        p.typed = "Drop D"
        try await withTimeout { await p.typedChanged() }
        guard case .success(let fresh)? = p.typedResult else { return XCTFail("no result for newer text") }
        XCTAssertEqual(fresh.name, "Drop D")

        gate.open()
        try await withTimeout { await old.value }
        guard case .success(let after)? = p.typedResult else { return XCTFail("result lost") }
        XCTAssertEqual(after.name, "Drop D", "late reply for older text must be ignored")
    }

    func testBlankTypedClearsResultWithoutCallingDescribe() async throws {
        let (p, _, api) = try await make()
        p.typed = "Drop D"
        try await withTimeout { await p.typedChanged() }
        XCTAssertNotNil(p.typedResult)
        let before = api.calls.filter { $0.hasPrefix("describe") }.count

        p.typed = "   "
        try await withTimeout { await p.typedChanged() }
        XCTAssertNil(p.typedResult)
        p.typed = ""
        try await withTimeout { await p.typedChanged() }
        XCTAssertNil(p.typedResult)
        XCTAssertEqual(api.calls.filter { $0.hasPrefix("describe") }.count, before)
    }

    // MARK: actions

    func testUseMatchSetsMatchTuningThenRefreshesRow() async throws {
        let (p, _, api) = try await make(.review(candidates: [match(eStd)]))
        let m = match(eStd)
        try await withTimeout { await p.use(m) }
        let s = try XCTUnwrap(indexOf(api, "set:bass:A:One:E Standard"))
        XCTAssertNotNil(indexOf(api, "tracks:bass:PL", after: s), "refreshRow must follow set")
    }

    func testSaveSetsTypedTuningThenRefreshesRow() async throws {
        let (p, app, api) = try await make()
        p.typed = "Drop D"
        try await withTimeout { await p.save() }
        let s = try XCTUnwrap(indexOf(api, "set:bass:A:One:Drop D"))
        XCTAssertNotNil(indexOf(api, "tracks:bass:PL", after: s))
        XCTAssertNil(app.banner)
    }

    func testClearDeletesThenRefreshesRowToUnknown() async throws {
        let cached = CacheState.cached(tuning: dropD, source: "web", confirmed: true)
        let (p, _, api) = try await make(cached)
        XCTAssertEqual(p.row?.status, .cached(dropD, source: "web", confirmed: true))
        api.configure { $0.tracks["PL"] = .success([self.ts("A", "One", .unknown), self.ts("B", "Two", .unknown)]) }
        try await withTimeout { await p.clear() }
        let d = try XCTUnwrap(indexOf(api, "delete:bass:A:One"))
        XCTAssertNotNil(indexOf(api, "tracks:bass:PL", after: d))
        XCTAssertEqual(p.row?.status, .unknown)
    }

    func testBadTuningOnSaveGoesToTypedResultNotBanner() async throws {
        let (p, app, _) = try await make { s in
            s.setError = ClientError.helper(kind: "bad_tuning", message: "nope")
        }
        p.typed = "zzz"
        try await withTimeout { await p.save() }
        guard case .failure(.helper(let kind, let message))? = p.typedResult else {
            return XCTFail("expected bad_tuning failure, got \(String(describing: p.typedResult))")
        }
        XCTAssertEqual(kind, "bad_tuning")
        XCTAssertEqual(message, "nope")
        XCTAssertNil(app.banner)
    }

    func testOtherErrorOnSaveSetsBanner() async throws {
        let (p, app, _) = try await make { s in
            s.setError = ClientError.helper(kind: "music", message: "Music is not running")
        }
        p.typed = "Drop D"
        try await withTimeout { await p.save() }
        XCTAssertEqual(app.banner?.kind, .music)

        let (p2, app2, _) = try await make { s in s.setError = ClientError.helperExited(stderrTail: ["x"]) }
        p2.typed = "Drop D"
        try await withTimeout { await p2.save() }
        XCTAssertEqual(app2.banner?.kind, .helperExited)

        let (p3, app3, _) = try await make { s in s.setError = FakeError(tag: "t") }
        p3.typed = "Drop D"
        try await withTimeout { await p3.save() }
        XCTAssertEqual(app3.banner?.kind, .other)
    }

    func testCancellationErrorOnSaveSetsNoBanner() async throws {
        let (p, app, _) = try await make { s in s.setError = CancellationError() }
        p.typed = "Drop D"
        try await withTimeout { await p.save() }
        XCTAssertNil(app.banner)
    }

    func testErrorOnClearSetsBanner() async throws {
        let (p, app, _) = try await make { s in
            s.deleteError = ClientError.helper(kind: "internal", message: "oops")
        }
        try await withTimeout { await p.clear() }
        XCTAssertEqual(app.banner?.kind, .other)
    }

    // MARK: row

    func testRowFollowsSelectionAndStatus() async throws {
        let (p, app, _) = try await make(.review(candidates: [match(eStd)]))
        XCTAssertEqual(p.row?.artist, "A")
        XCTAssertEqual(p.row?.status, .review([match(eStd)]))

        let b = try XCTUnwrap(app.rows.first { $0.artist == "B" })
        app.selectedRowID = b.id
        XCTAssertEqual(p.row?.artist, "B")
        XCTAssertEqual(p.row?.status, .unknown)

        app.selectedRowID = nil
        XCTAssertNil(p.row)
    }

    func testRowShowsCached() async throws {
        let (p, _, _) = try await make(.cached(tuning: dropD, source: "ug", confirmed: false))
        XCTAssertEqual(p.row?.status, .cached(dropD, source: "ug", confirmed: false))
    }

    func testRowShowsFailedAfterRun() async throws {
        let (p, app, api) = try await make()
        let task = Task { await app.preview() }
        try await api.waitForSort()
        api.yield(.event(.done(SortDone(artist: "A", title: "One", status: .lookupFailed, failed: ["ug", "web"]))))
        try await waitUntil("failed") { p.row?.status == .failed(sources: ["ug", "web"]) }
        api.yield(.finished(Report(cancelled: false, createdPlaylists: [], added: [:], alreadyPresent: [:],
                                   review: [], lookupFailed: [], addErrors: [])))
        api.finishStream()
        try await withTimeout { await task.value }
    }

    func testNoSelectedRowMakesNoCalls() async throws {
        let (p, app, api) = try await make()
        app.selectedRowID = nil
        let before = api.calls
        p.typed = "Drop D"
        let m = match(eStd)
        try await withTimeout { await p.use(m) }
        try await withTimeout { await p.save() }
        try await withTimeout { await p.clear() }
        XCTAssertEqual(api.calls, before)
        XCTAssertNil(app.banner)
    }
}
