import XCTest
@testable import TuneSortCore

@MainActor
final class PostRunRefreshTests: XCTestCase {
    private let dropD = TuningInfo(name: "Drop D", playlistName: "Bass – Drop D", notes: "D A D G")
    private let eStd = TuningInfo(name: "E Standard", playlistName: "Bass – E Standard", notes: "E A D G")

    private func match(_ t: TuningInfo) -> MatchInfo {
        MatchInfo(tuning: t, source: "web", url: "u", matchedArtist: "m", matchedTitle: "t", exact: true)
    }
    private func ts(_ a: String, _ t: String, _ s: CacheState) -> TrackState {
        TrackState(track: Track(artist: a, title: t, persistentId: "id-\(a)-\(t)"), state: s)
    }
    private func report(cancelled: Bool = false) -> Report {
        Report(cancelled: cancelled, createdPlaylists: [], added: [:], alreadyPresent: [:],
               review: [], lookupFailed: [], addErrors: [])
    }
    private func row(_ m: AppModel, _ a: String, _ t: String) -> SongRow? {
        m.rows.first { $0.artist == a && $0.title == t }
    }
    private func count(_ api: FakeHelperAPI, _ prefix: String) -> Int {
        api.calls.filter { $0.hasPrefix(prefix) }.count
    }

    private func make(_ extra: (inout FakeHelperAPI.State) -> Void = { _ in }) async -> (AppModel, FakeHelperAPI) {
        let api = FakeHelperAPI()
        api.configure { s in
            s.playlists = .success(["PL"])
            s.tracks["PL"] = .success([self.ts("A", "One", .unknown), self.ts("B", "Two", .unknown),
                                       self.ts("C", "Three", .review(candidates: [self.match(self.eStd)]))])
            extra(&s)
        }
        let m = AppModel(api: api)
        await m.load()
        await m.select(.playlist("PL"))
        return (m, api)
    }

    func testReviewRowGetsCandidatesFromReviewListAfterPreview() async throws {
        let (m, api) = await make()
        XCTAssertEqual(m.reviewCount, 0)
        let task = Task { await m.preview() }
        try await api.waitForSort()
        api.configure { s in
            s.reviewList[.bass] = .success([
                ReviewItem(artist: "A", title: "One", candidates: [self.match(self.dropD)]),
                ReviewItem(artist: "Z", title: "Other", candidates: []),
            ])
        }
        api.yield(.event(.done(SortDone(artist: "A", title: "One", status: .review))))
        api.yield(.finished(report()))
        api.finishStream()
        try await withTimeout { await task.value }

        XCTAssertEqual(row(m, "A", "One")?.status, .review([match(dropD)]))
        XCTAssertEqual(m.reviewCount, 2)
        // Rows not in the review list are unchanged.
        XCTAssertEqual(row(m, "B", "Two")?.status, .unknown)
        XCTAssertEqual(row(m, "C", "Three")?.status, .review([match(eStd)]))
        XCTAssertEqual(m.runState, .idle)
    }

    func testNewTuningPlaylistAppearsAfterSort() async throws {
        let (m, api) = await make()
        XCTAssertEqual(m.tuningPlaylists, [])
        let task = Task { await m.sort() }
        try await api.waitForSort()
        api.configure { $0.playlists = .success(["PL", "Bass – Drop D"]) }
        api.yield(.finished(report()))
        api.finishStream()
        try await withTimeout { await task.value }
        XCTAssertEqual(m.tuningPlaylists, ["Bass – Drop D"])
        XCTAssertEqual(m.playlists, ["PL"])
    }

    func testRefreshCallsOnceEachInOrderAndNoTracksRefetch() async throws {
        let (m, api) = await make()
        let tracksBefore = count(api, "tracks:")
        let reviewBefore = count(api, "reviewList:")
        let playlistsBefore = count(api, "playlists")
        let task = Task { await m.preview() }
        try await api.waitForSort()
        api.yield(.finished(report()))
        api.finishStream()
        try await withTimeout { await task.value }
        XCTAssertEqual(count(api, "tracks:"), tracksBefore)
        XCTAssertEqual(count(api, "reviewList:"), reviewBefore + 1)
        XCTAssertEqual(count(api, "playlists"), playlistsBefore + 1)
        let calls = api.calls
        let r = try XCTUnwrap(calls.lastIndex(of: "reviewList:bass"))
        let p = try XCTUnwrap(calls.lastIndex(of: "playlists"))
        XCTAssertLessThan(r, p)
        XCTAssertGreaterThan(r, try XCTUnwrap(calls.lastIndex(of: "sort")))
    }

    func testRunStaysNotIdleUntilRefreshCompletes() async throws {
        let (m, api) = await make()
        let gate = Gate()
        api.configure { $0.reviewListGate = gate }
        let task = Task { await m.preview() }
        try await api.waitForSort()
        api.yield(.finished(report()))
        api.finishStream()
        try await api.waitForCall("reviewList:bass", count: 2)
        XCTAssertNotEqual(m.runState, .idle)
        gate.open()
        try await withTimeout { await task.value }
        XCTAssertEqual(m.runState, .idle)
    }

    func testCancelledRunStillRefreshes() async throws {
        let (m, api) = await make()
        let task = Task { await m.preview() }
        try await api.waitForSort()
        api.configure { $0.reviewList[.bass] = .success([ReviewItem(artist: "B", title: "Two", candidates: [])]) }
        api.yield(.finished(report(cancelled: true)))
        api.finishStream()
        try await withTimeout { await task.value }
        XCTAssertEqual(m.reviewCount, 1)
        XCTAssertEqual(count(api, "reviewList:"), 2)
        XCTAssertEqual(count(api, "playlists"), 2)
    }

    func testFailedStreamKeepsHelperExitedBannerWhileRefreshing() async throws {
        let (m, api) = await make()
        let task = Task { await m.preview() }
        try await api.waitForSort()
        api.finishStream(throwing: ClientError.helperExited(stderrTail: ["boom"]))
        try await withTimeout { await task.value }
        XCTAssertEqual(m.banner?.kind, .helperExited)
        XCTAssertEqual(m.banner?.stderrTail, ["boom"])
        XCTAssertEqual(count(api, "reviewList:"), 2)
        XCTAssertEqual(count(api, "playlists"), 2)
        XCTAssertEqual(m.runState, .idle)
    }

    func testRefreshFailureIsIgnored() async throws {
        let (m, api) = await make { s in
            s.reviewList[.bass] = .success([ReviewItem(artist: "A", title: "T", candidates: [])])
        }
        await m.load()
        XCTAssertEqual(m.reviewCount, 1)
        let task = Task { await m.sort() }
        try await api.waitForSort()
        api.configure { s in
            s.reviewList[.bass] = .failure(ClientError.helper(kind: "internal", message: "oops"))
            s.playlists = .failure(ClientError.helper(kind: "music", message: "down"))
        }
        api.yield(.finished(report()))
        api.finishStream()
        try await withTimeout { await task.value }
        XCTAssertNil(m.banner)
        XCTAssertEqual(m.reviewCount, 1)
        XCTAssertEqual(m.playlists, ["PL"])
        XCTAssertEqual(m.runState, .idle)
    }

    func testRefreshFailureDoesNotReplaceRunBanner() async throws {
        let (m, api) = await make()
        let task = Task { await m.preview() }
        try await api.waitForSort()
        api.configure { $0.reviewList[.bass] = .failure(ClientError.helper(kind: "internal", message: "oops")) }
        api.finishStream(throwing: ClientError.helperExited(stderrTail: ["x"]))
        try await withTimeout { await task.value }
        XCTAssertEqual(m.banner?.kind, .helperExited)
    }
}
