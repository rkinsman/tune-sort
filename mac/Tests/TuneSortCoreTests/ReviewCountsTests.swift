import XCTest
@testable import TuneSortCore

@MainActor
final class ReviewCountsTests: XCTestCase {
    private func ts(_ a: String, _ t: String) -> TrackState {
        TrackState(track: Track(artist: a, title: t, persistentId: "id-\(a)-\(t)"), state: .unknown)
    }
    private func report() -> Report {
        Report(cancelled: false, createdPlaylists: [], added: [:], alreadyPresent: [:],
               review: [], lookupFailed: [], addErrors: [])
    }
    private func calls(_ api: FakeHelperAPI, _ c: String) -> Int { api.calls.filter { $0 == c }.count }

    private func make(_ extra: (inout FakeHelperAPI.State) -> Void = { _ in }) -> (AppModel, FakeHelperAPI) {
        let api = FakeHelperAPI()
        api.configure { s in
            s.playlists = .success(["PL"])
            s.tracks["PL"] = .success([self.ts("A", "One"), self.ts("B", "Two")])
            extra(&s)
        }
        return (AppModel(api: api), api)
    }

    /// Awaits the latest background refresh, bounded.
    private func settle(_ m: AppModel) async throws {
        let t = m.reviewCountsTask
        try await withTimeout { await t?.value }
    }

    func testStartsEmpty() {
        let (m, _) = make()
        XCTAssertEqual(m.playlistReviewCounts, [:])
    }

    func testLoadFillsCounts() async throws {
        let (m, api) = make { $0.reviewCounts[.bass] = .success(["Drop D": 2, "Gym": 1]) }
        await m.load()
        try await settle(m)
        XCTAssertEqual(m.playlistReviewCounts, ["Drop D": 2, "Gym": 1])
        XCTAssertEqual(calls(api, "reviewCounts:bass"), 1)
        XCTAssertNil(m.banner)
    }

    func testLoadDoesNotWaitForReviewCounts() async throws {
        let gate = Gate()
        let (m, api) = make { s in
            s.reviewCounts[.bass] = .success(["Drop D": 2])
            s.reviewCountsGate = gate
        }
        let task = Task { await m.load() }
        try await withTimeout { await task.value }
        try await api.waitForCall("reviewCounts:bass")
        XCTAssertEqual(m.playlistReviewCounts, [:])
        gate.open()
        try await settle(m)
        XCTAssertEqual(m.playlistReviewCounts, ["Drop D": 2])
    }

    func testCountsRefreshAfterPreviewWithoutDelayingIdle() async throws {
        let (m, api) = make { $0.reviewCounts[.bass] = .success(["Drop D": 2]) }
        await m.load()
        await m.select(.playlist("PL"))
        try await settle(m)
        XCTAssertEqual(m.playlistReviewCounts, ["Drop D": 2])

        let gate = Gate()
        api.configure { $0.reviewCountsQueue = [(gate: gate, result: .success(["Drop D": 5, "Gym": 1]))] }
        let task = Task { await m.preview() }
        try await api.waitForSort()
        api.yield(.finished(report()))
        api.finishStream()
        try await withTimeout { await task.value }
        XCTAssertEqual(m.runState, .idle)
        try await api.waitForCall("reviewCounts:bass", count: 2)
        XCTAssertEqual(m.playlistReviewCounts, ["Drop D": 2], "old values stay until the refresh lands")
        gate.open()
        try await settle(m)
        XCTAssertEqual(m.playlistReviewCounts, ["Drop D": 5, "Gym": 1])
    }

    func testCountsRefreshAfterSortRun() async throws {
        let (m, api) = make()
        await m.load()
        await m.select(.playlist("PL"))
        try await settle(m)
        api.configure { $0.reviewCounts[.bass] = .success(["Gym": 4]) }
        let task = Task { await m.sort() }
        try await api.waitForSort()
        api.yield(.finished(report()))
        api.finishStream()
        try await withTimeout { await task.value }
        try await settle(m)
        XCTAssertEqual(calls(api, "reviewCounts:bass"), 2)
        XCTAssertEqual(m.playlistReviewCounts, ["Gym": 4])
    }

    func testRefreshRowTriggersRefresh() async throws {
        let (m, api) = make { $0.reviewCounts[.bass] = .success(["Drop D": 2]) }
        await m.load()
        await m.select(.playlist("PL"))
        try await settle(m)
        XCTAssertEqual(calls(api, "reviewCounts:bass"), 1)

        api.configure { $0.reviewCounts[.bass] = .success(["Drop D": 1]) }
        await m.refreshRow(artist: "A", title: "One")
        try await settle(m)
        XCTAssertEqual(calls(api, "reviewCounts:bass"), 2)
        XCTAssertEqual(m.playlistReviewCounts, ["Drop D": 1])
    }

    func testRefreshReviewCountsDirectCall() async throws {
        let (m, api) = make { $0.reviewCounts[.bass] = .success(["Drop D": 2]) }
        m.refreshReviewCounts()
        try await settle(m)
        XCTAssertEqual(calls(api, "reviewCounts:bass"), 1)
        XCTAssertEqual(m.playlistReviewCounts, ["Drop D": 2])
    }

    func testSetInstrumentClearsCountsAndAsksForNewInstrument() async throws {
        let gate = Gate()
        let (m, api) = make { s in
            s.reviewCounts[.bass] = .success(["Drop D": 2])
            s.reviewCounts[.guitar] = .success(["Open G": 3])
        }
        await m.load()
        try await settle(m)
        XCTAssertEqual(m.playlistReviewCounts, ["Drop D": 2])

        api.configure { $0.reviewCountsGate = gate }
        await m.setInstrument(.guitar)
        XCTAssertEqual(m.playlistReviewCounts, [:])
        try await api.waitForCall("reviewCounts:guitar")
        XCTAssertEqual(m.playlistReviewCounts, [:])
        gate.open()
        try await settle(m)
        XCTAssertEqual(m.playlistReviewCounts, ["Open G": 3])
        XCTAssertEqual(calls(api, "reviewCounts:bass"), 1)
    }

    func testErrorLeavesCountsUnchangedAndSetsNoBanner() async throws {
        let (m, api) = make { $0.reviewCounts[.bass] = .success(["Drop D": 2]) }
        await m.load()
        try await settle(m)
        api.configure { $0.reviewCounts[.bass] = .failure(ClientError.helper(kind: "internal", message: "oops")) }
        m.refreshReviewCounts()
        try await settle(m)
        XCTAssertEqual(calls(api, "reviewCounts:bass"), 2)
        XCTAssertEqual(m.playlistReviewCounts, ["Drop D": 2])
        XCTAssertNil(m.banner)
    }

    func testResultArrivingAfterInstrumentChangeIsDropped() async throws {
        let (m, api) = make { $0.reviewCounts[.bass] = .success(["Drop D": 2]) }
        await m.load()
        try await settle(m)

        let gate = Gate()
        api.configure { s in
            // 1st: the stale bass refresh (gated); 2nd: guitar's refresh fails so nothing else sets counts.
            s.reviewCountsQueue = [(gate: gate, result: .success(["Stale": 9])),
                                   (gate: nil, result: .failure(FakeError(tag: "guitar")))]
        }
        m.refreshReviewCounts()
        let old = m.reviewCountsTask
        try await api.waitForCall("reviewCounts:bass", count: 2)
        await m.setInstrument(.guitar)
        XCTAssertEqual(m.instrument, .guitar)
        gate.open()
        try await withTimeout { await old?.value }
        try await settle(m)
        XCTAssertEqual(m.playlistReviewCounts, [:])
    }

    func testSupersededRefreshDoesNotOverwriteNewerResult() async throws {
        let (m, api) = make()
        await m.load()
        try await settle(m)

        let gate = Gate()
        api.configure { s in
            s.reviewCountsQueue = [(gate: gate, result: .success(["Old": 1])),
                                   (gate: nil, result: .success(["New": 2]))]
        }
        m.refreshReviewCounts()
        let first = m.reviewCountsTask
        try await api.waitForCall("reviewCounts:bass", count: 2)
        m.refreshReviewCounts()
        try await settle(m)
        XCTAssertEqual(m.playlistReviewCounts, ["New": 2])

        gate.open()
        try await withTimeout { await first?.value }
        XCTAssertEqual(m.playlistReviewCounts, ["New": 2])
    }
}
