import XCTest
@testable import TuneSortCore

@MainActor
final class AppModelTests: XCTestCase {
    private let dropD = TuningInfo(name: "Drop D", playlistName: "Bass – Drop D", notes: "D A D G")
    private let eStd = TuningInfo(name: "E Standard", playlistName: "Bass – E Standard", notes: "E A D G")

    private func track(_ a: String, _ t: String) -> Track { Track(artist: a, title: t, persistentId: "id-\(a)-\(t)") }
    private func ts(_ a: String, _ t: String, _ s: CacheState) -> TrackState { TrackState(track: track(a, t), state: s) }
    private func match(_ tuning: TuningInfo) -> MatchInfo {
        MatchInfo(tuning: tuning, source: "web", url: "u", matchedArtist: "m", matchedTitle: "t", exact: true)
    }
    private func report(cancelled: Bool = false, created: [String] = [], added: [String: [Track]] = [:],
                        review: [Track] = [], failed: [Track] = []) -> Report {
        Report(cancelled: cancelled, createdPlaylists: created, added: added, alreadyPresent: [:],
               review: review, lookupFailed: failed, addErrors: [])
    }

    private func makeModel(_ configure: (inout FakeHelperAPI.State) -> Void = { _ in })
        -> (AppModel, FakeHelperAPI) {
        let api = FakeHelperAPI()
        api.configure(configure)
        return (AppModel(api: api), api)
    }

    private func waitUntil(_ what: String, timeout: Double = 5, _ cond: () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while !cond() {
            if Date() > deadline { XCTFail("timed out waiting for \(what)"); throw TestTimeout() }
            try await Task.sleep(nanoseconds: 2_000_000)
        }
    }

    private func row(_ m: AppModel, _ a: String, _ t: String) -> SongRow? {
        m.rows.first { $0.artist == a && $0.title == t }
    }

    private func isIdle(_ m: AppModel) -> Bool { m.runState == .idle }

    /// Model with playlist "PL" holding two unknown tracks, selected.
    private func playlistModel(extra: (inout FakeHelperAPI.State) -> Void = { _ in }) async throws
        -> (AppModel, FakeHelperAPI) {
        let (m, api) = makeModel { s in
            s.playlists = .success(["PL", "Bass – Drop D"])
            s.tracks["PL"] = .success([self.ts("A", "One", .unknown), self.ts("B", "Two", .unknown)])
            extra(&s)
        }
        await m.load()
        await m.select(.playlist("PL"))
        return (m, api)
    }

    private func startPreview(_ m: AppModel, _ api: FakeHelperAPI) async throws -> Task<Void, Never> {
        let task = Task { await m.preview() }
        try await api.waitForSort()
        return task
    }

    // MARK: load

    func testLoadSplitsPlaylistsAndCountsReview() async throws {
        let (m, api) = makeModel { s in
            s.playlists = .success(["Road Trip", "Bass – Drop D", "Bass 5-String – B Standard", "Guitar – Drop D", "Mix"])
            s.reviewList[.bass] = .success([ReviewItem(artist: "A", title: "T", candidates: []),
                                            ReviewItem(artist: "B", title: "U", candidates: [])])
        }
        XCTAssertEqual(m.instrument, .bass)
        await m.load()
        XCTAssertEqual(m.playlists, ["Road Trip", "Guitar – Drop D", "Mix"])
        XCTAssertEqual(m.tuningPlaylists, ["Bass – Drop D", "Bass 5-String – B Standard"])
        XCTAssertEqual(m.reviewCount, 2)
        XCTAssertNil(m.banner)
        XCTAssertTrue(api.calls.contains("reviewList:bass"))
    }

    // MARK: select

    func testSelectPlaylistMapsTrackStates() async throws {
        let (m, api) = makeModel { s in
            s.tracks["PL"] = .success([
                self.ts("A", "Cached", .cached(tuning: self.dropD, source: "web", confirmed: true)),
                self.ts("B", "Rev", .review(candidates: [self.match(self.eStd)])),
                self.ts("C", "Unk", .unknown),
            ])
        }
        await m.select(.playlist("PL"))
        XCTAssertEqual(m.selection, .playlist("PL"))
        XCTAssertTrue(api.calls.contains("tracks:bass:PL"))
        XCTAssertEqual(m.rows.count, 3)
        XCTAssertEqual(row(m, "A", "Cached")?.status, .cached(dropD, source: "web", confirmed: true))
        XCTAssertEqual(row(m, "A", "Cached")?.persistentID, "id-A-Cached")
        XCTAssertEqual(row(m, "B", "Rev")?.status, .review([match(eStd)]))
        XCTAssertEqual(row(m, "B", "Rev")?.persistentID, "id-B-Rev")
        XCTAssertEqual(row(m, "C", "Unk")?.status, .unknown)
        XCTAssertEqual(row(m, "C", "Unk")?.persistentID, "id-C-Unk")
    }

    func testSelectNeedsReviewLoadsReviewList() async throws {
        let (m, _) = makeModel { s in
            s.reviewList[.bass] = .success([ReviewItem(artist: "A", title: "T", candidates: [self.match(self.dropD)])])
        }
        await m.select(.needsReview)
        XCTAssertEqual(m.rows.count, 1)
        XCTAssertEqual(m.rows.first?.artist, "A")
        XCTAssertEqual(m.rows.first?.title, "T")
        XCTAssertEqual(m.rows.first?.status, .review([match(dropD)]))
        XCTAssertNil(m.rows.first?.persistentID)
    }

    func testSelectAllSongsLoadsEntries() async throws {
        let (m, api) = makeModel { s in
            s.entries[.bass] = .success([
                CachedSong(artist: "A", title: "T", tuning: self.dropD, source: "web", confirmed: false)])
        }
        await m.select(.allSongs)
        XCTAssertTrue(api.calls.contains("entries:bass"))
        XCTAssertEqual(m.rows.count, 1)
        XCTAssertEqual(m.rows.first?.status, .cached(dropD, source: "web", confirmed: false))
    }

    func testSearchFiltersAllSongsCaseInsensitively() async throws {
        let song = { (a: String, t: String) in
            CachedSong(artist: a, title: t, tuning: self.dropD, source: "web", confirmed: true)
        }
        let (m, _) = makeModel { s in
            s.entries[.bass] = .success([song("The Beatles", "Help"), song("Queen", "Bicycle Race"),
                                         song("Abba", "Beat It")])
        }
        await m.select(.allSongs)
        XCTAssertEqual(m.rows.count, 3)

        m.searchText = "BEAT"
        XCTAssertEqual(Set(m.rows.map(\.artist)), ["The Beatles", "Abba"])

        m.searchText = "race"
        XCTAssertEqual(m.rows.map(\.artist), ["Queen"])

        m.searchText = "zzz"
        XCTAssertEqual(m.rows, [])

        m.searchText = ""
        XCTAssertEqual(m.rows.count, 3)
    }

    func testEmptyPlaylistGivesNoRowsAndNoBanner() async throws {
        let (m, _) = makeModel { s in s.tracks["Empty"] = .success([]) }
        await m.select(.playlist("Empty"))
        XCTAssertEqual(m.rows, [])
        XCTAssertNil(m.banner)
    }

    // MARK: preview

    func testPreviewSendsRequestAndUpdatesRows() async throws {
        let (m, api) = try await playlistModel()
        m.sourcesOverride = ["songsterr", "ug"]
        let task = try await startPreview(m, api)

        let req = try XCTUnwrap(api.sortRequests.first)
        XCTAssertEqual(req.instrument, .bass)
        XCTAssertEqual(req.playlist, "PL")
        XCTAssertTrue(req.dryRun)
        XCTAssertEqual(req.order, ["songsterr", "ug"])
        try await waitUntil("running") {
            if case .running(_, _, let dry) = m.runState { return dry }
            return false
        }

        api.yield(.event(.start(SortStart(i: 1, total: 2, artist: "A", title: "One"))))
        try await waitUntil("lookingUp") { self.row(m, "A", "One")?.status == .lookingUp }
        XCTAssertEqual(row(m, "B", "Two")?.status, .unknown)
        if case .running(_, let total, let dry) = m.runState {
            XCTAssertEqual(total, 2)
            XCTAssertTrue(dry)
        } else { XCTFail("expected running, got \(m.runState)") }

        api.yield(.event(.done(SortDone(artist: "A", title: "One", status: .added, tuning: dropD,
                                        source: "web", playlist: "Bass – Drop D"))))
        try await waitUntil("cached") {
            self.row(m, "A", "One")?.status == .cached(self.dropD, source: "web", confirmed: false)
        }

        api.yield(.event(.start(SortStart(i: 2, total: 2, artist: "B", title: "Two"))))
        try await waitUntil("lookingUp 2") { self.row(m, "B", "Two")?.status == .lookingUp }
        api.yield(.event(.done(SortDone(artist: "B", title: "Two", status: .review))))
        try await waitUntil("review") { self.row(m, "B", "Two")?.status == .review([]) }

        api.yield(.finished(report(added: ["Bass – Drop D": [track("A", "One")]], review: [track("B", "Two")])))
        api.finishStream()
        await task.value

        XCTAssertEqual(m.runState, .idle)
        XCTAssertEqual(m.lastSummary, "Preview: 1 would be added to 1 playlist · 1 needs review")
        XCTAssertNil(m.banner)
    }

    func testDoneStatusesMapToRowStatuses() async throws {
        let (m, api) = try await playlistModel { s in
            s.tracks["PL"] = .success([self.ts("A", "One", .unknown), self.ts("B", "Two", .unknown),
                                       self.ts("C", "Three", .unknown)])
        }
        let task = try await startPreview(m, api)
        api.yield(.event(.done(SortDone(artist: "A", title: "One", status: .alreadyPresent, tuning: dropD,
                                        source: nil, playlist: "Bass – Drop D"))))
        api.yield(.event(.done(SortDone(artist: "B", title: "Two", status: .lookupFailed, failed: ["ug", "web"]))))
        api.yield(.event(.done(SortDone(artist: "C", title: "Three", status: .addError, error: "boom"))))
        try await waitUntil("statuses") { self.row(m, "C", "Three")?.status == .addError("boom") }
        XCTAssertEqual(row(m, "A", "One")?.status, .cached(dropD, source: "", confirmed: false))
        XCTAssertEqual(row(m, "B", "Two")?.status, .failed(sources: ["ug", "web"]))
        api.yield(.finished(report(failed: [track("B", "Two")])))
        api.finishStream()
        await task.value
        XCTAssertEqual(m.lastSummary, "Preview: 0 would be added to 0 playlists · 1 failed")
    }

    func testPreviewDoesNothingWhenSelectionIsNotAPlaylist() async throws {
        let (m, api) = makeModel()
        await m.preview()
        await m.sort()
        XCTAssertTrue(api.sortRequests.isEmpty)
        XCTAssertEqual(m.runState, .idle)

        await m.select(.allSongs)
        await m.preview()
        await m.sort()
        XCTAssertTrue(api.sortRequests.isEmpty)
        XCTAssertEqual(m.runState, .idle)
        XCTAssertNil(m.lastSummary)
    }

    // MARK: sort summary / confirmation

    func testRealSortSummary() async throws {
        let (m, api) = try await playlistModel()
        let task = Task { await m.sort() }
        try await api.waitForSort()
        XCTAssertFalse(try XCTUnwrap(api.sortRequests.first).dryRun)
        try await waitUntil("running") {
            if case .running(_, _, let dry) = m.runState { return !dry }
            return false
        }
        let t = [track("A", "One"), track("B", "Two")]
        api.yield(.finished(report(added: ["Bass – Drop D": t, "Bass – E Standard": [track("C", "X")]],
                                   review: [track("D", "Y"), track("E", "Z")], failed: [track("F", "W")])))
        api.finishStream()
        await task.value
        XCTAssertEqual(m.lastSummary, "Added 3 to 2 playlists · 2 need review · 1 failed")
    }

    func testSummaryStoppedSuffix() async throws {
        let (m, api) = try await playlistModel()
        let task = Task { await m.sort() }
        try await api.waitForSort()
        api.yield(.finished(report(cancelled: true, added: ["Bass – Drop D": [track("A", "One")]])))
        api.finishStream()
        await task.value
        XCTAssertEqual(m.lastSummary, "Added 1 to 1 playlist · stopped")
    }

    func testPreviewSummaryFullExample() async throws {
        let (m, api) = try await playlistModel()
        let task = try await startPreview(m, api)
        api.yield(.finished(report(added: ["Bass – Drop D": [track("A", "1"), track("B", "2"), track("C", "3")]],
                                   review: [track("D", "4")], failed: [track("E", "5")])))
        api.finishStream()
        await task.value
        XCTAssertEqual(m.lastSummary, "Preview: 3 would be added to 1 playlist · 1 needs review · 1 failed")
    }

    func testConfirmationFallbackWithoutPreview() async throws {
        let (m, _) = try await playlistModel()
        XCTAssertEqual(m.sortConfirmation(), "Sort 'PL' into tuning playlists?")
    }

    private func finishedPreview(_ m: AppModel, _ api: FakeHelperAPI, _ r: Report) async throws {
        let task = try await startPreview(m, api)
        api.yield(.finished(r))
        api.finishStream()
        await task.value
    }

    func testConfirmationUsesPreviewFiguresPlural() async throws {
        let (m, api) = try await playlistModel()
        try await finishedPreview(m, api, report(
            created: ["Bass – Drop D"],
            added: ["Bass – Drop D": [track("A", "1"), track("B", "2")], "Bass – E Standard": [track("C", "3")]]))
        XCTAssertEqual(m.sortConfirmation(), "Add 3 songs to 2 playlists, creating 1?")
    }

    func testConfirmationSingularAndNoCreating() async throws {
        let (m, api) = try await playlistModel()
        try await finishedPreview(m, api, report(added: ["Bass – Drop D": [track("A", "1")]]))
        XCTAssertEqual(m.sortConfirmation(), "Add 1 song to 1 playlist?")
    }

    func testConfirmationFallsBackWhenSourcesOverrideChanged() async throws {
        let (m, api) = try await playlistModel()
        try await finishedPreview(m, api, report(added: ["Bass – Drop D": [track("A", "1")]]))
        XCTAssertEqual(m.sortConfirmation(), "Add 1 song to 1 playlist?")
        m.sourcesOverride = ["ug"]
        XCTAssertEqual(m.sortConfirmation(), "Sort 'PL' into tuning playlists?")
    }

    func testConfirmationFallsBackWhenPlaylistChanged() async throws {
        let (m, api) = try await playlistModel { s in s.tracks["Other"] = .success([]) }
        try await finishedPreview(m, api, report(added: ["Bass – Drop D": [track("A", "1")]]))
        await m.select(.playlist("Other"))
        XCTAssertEqual(m.sortConfirmation(), "Sort 'Other' into tuning playlists?")
    }

    func testConfirmationFallsBackAfterRealRun() async throws {
        let (m, api) = try await playlistModel()
        try await finishedPreview(m, api, report(added: ["Bass – Drop D": [track("A", "1")]]))
        let task = Task { await m.sort() }
        try await api.waitForSort(2)
        api.yield(.finished(report(added: ["Bass – Drop D": [track("A", "1")]])))
        api.finishStream()
        await task.value
        XCTAssertEqual(m.sortConfirmation(), "Sort 'PL' into tuning playlists?")
    }

    // MARK: stop / errors

    func testStopCallsCancelAndCancelledReportRestoresRows() async throws {
        let (m, api) = try await playlistModel()
        let task = try await startPreview(m, api)
        api.yield(.event(.start(SortStart(i: 1, total: 2, artist: "A", title: "One"))))
        try await waitUntil("lookingUp") { self.row(m, "A", "One")?.status == .lookingUp }

        await m.stop()
        XCTAssertEqual(api.cancelledRunIDs, [FakeHelperAPI.firstRunID])

        api.yield(.finished(report(cancelled: true)))
        api.finishStream()
        await task.value
        XCTAssertEqual(m.runState, .idle)
        XCTAssertEqual(row(m, "A", "One")?.status, .unknown)
        XCTAssertEqual(m.lastSummary, "Preview: 0 would be added to 0 playlists · stopped")
    }

    func testHelperExitedDuringSortShowsBannerAndRestoresRows() async throws {
        let (m, api) = try await playlistModel()
        let task = try await startPreview(m, api)
        api.yield(.event(.start(SortStart(i: 1, total: 2, artist: "A", title: "One"))))
        try await waitUntil("lookingUp") { self.row(m, "A", "One")?.status == .lookingUp }

        api.finishStream(throwing: ClientError.helperExited(stderrTail: ["line1", "boom"]))
        await task.value

        XCTAssertEqual(m.banner?.kind, .helperExited)
        XCTAssertEqual(m.banner?.stderrTail, ["line1", "boom"])
        XCTAssertEqual(m.runState, .idle)
        XCTAssertEqual(row(m, "A", "One")?.status, .unknown)
    }

    func testHelperExitedFromLoadShowsBanner() async throws {
        let (m, _) = makeModel { s in s.playlists = .failure(ClientError.helperExited(stderrTail: ["dead"])) }
        await m.load()
        XCTAssertEqual(m.banner?.kind, .helperExited)
        XCTAssertEqual(m.banner?.stderrTail, ["dead"])
    }

    func testMusicErrorShowsMusicBanner() async throws {
        let (m, _) = makeModel { s in
            s.playlists = .failure(ClientError.helper(kind: "music", message: "Music is not running"))
        }
        await m.load()
        XCTAssertEqual(m.banner?.kind, .music)
        XCTAssertTrue(m.banner?.message.contains("Music is not running") ?? false)
    }

    func testMusicErrorOnSelectShowsMusicBanner() async throws {
        let (m, _) = makeModel { s in
            s.tracks["PL"] = .failure(ClientError.helper(kind: "music", message: "no playlist"))
        }
        await m.select(.playlist("PL"))
        XCTAssertEqual(m.banner?.kind, .music)
    }

    func testConfigErrorOnSortShowsConfigBanner() async throws {
        let (m, api) = try await playlistModel { s in
            s.sortError = ClientError.helper(kind: "config", message: "bad order")
        }
        await m.sort()
        XCTAssertEqual(api.sortRequests.count, 1)
        XCTAssertEqual(m.banner?.kind, .config)
        XCTAssertEqual(m.runState, .idle)
    }

    func testOtherErrorShowsOtherBanner() async throws {
        let (m, _) = makeModel { s in
            s.playlists = .failure(ClientError.helper(kind: "internal", message: "oops"))
        }
        await m.load()
        XCTAssertEqual(m.banner?.kind, .other)

        let (m2, _) = makeModel { s in s.playlists = .failure(FakeError(tag: "x")) }
        await m2.load()
        XCTAssertEqual(m2.banner?.kind, .other)
    }

    // MARK: instrument

    func testSetInstrumentReloadsSidebarAndClearsSelection() async throws {
        let (m, api) = makeModel { s in
            s.playlists = .success(["Mix", "Bass – Drop D", "Guitar – Drop D", "Guitar 7-String – B Standard"])
            s.tracks["Mix"] = .success([self.ts("A", "One", .unknown)])
            s.reviewList[.guitar] = .success([ReviewItem(artist: "G", title: "T", candidates: [])])
        }
        await m.load()
        await m.select(.playlist("Mix"))
        XCTAssertEqual(m.rows.count, 1)
        XCTAssertEqual(m.reviewCount, 0)

        await m.setInstrument(.guitar)
        XCTAssertEqual(m.instrument, .guitar)
        XCTAssertNil(m.selection)
        XCTAssertEqual(m.rows, [])
        XCTAssertEqual(m.tuningPlaylists, ["Guitar – Drop D", "Guitar 7-String – B Standard"])
        XCTAssertEqual(m.playlists, ["Mix", "Bass – Drop D"])
        XCTAssertEqual(m.reviewCount, 1)
        XCTAssertTrue(api.calls.contains("reviewList:guitar"))
    }

    // MARK: reentrancy (review follow-ups)

    private func m_isRunning(_ m: AppModel) -> Bool {
        if case .running = m.runState { return true }
        return false
    }

    /// 1. While a run is active, select / setInstrument / load do nothing.
    func testSelectionChangesAreIgnoredWhileRunIsActive() async throws {
        let (m, api) = try await playlistModel { s in s.tracks["Other"] = .success([self.ts("X", "Y", .unknown)]) }
        let task = try await startPreview(m, api)
        try await waitUntil("running") { self.m_isRunning(m) }
        let before = api.calls

        await m.select(.playlist("Other"))
        await m.select(.allSongs)
        await m.setInstrument(.guitar)
        await m.load()

        XCTAssertEqual(api.calls, before, "no API calls may be made while a run is active")
        XCTAssertEqual(m.selection, .playlist("PL"))
        XCTAssertEqual(m.instrument, .bass)
        XCTAssertEqual(m.playlists, ["PL"])
        XCTAssertEqual(m.rows.map(\.artist), ["A", "B"])

        // The run's events still apply to its own rows.
        api.yield(.event(.start(SortStart(i: 1, total: 2, artist: "A", title: "One"))))
        try await waitUntil("lookingUp") { self.row(m, "A", "One")?.status == .lookingUp }
        api.yield(.event(.done(SortDone(artist: "A", title: "One", status: .added, tuning: dropD,
                                        source: "web", playlist: "Bass – Drop D"))))
        api.yield(.finished(report(added: ["Bass – Drop D": [track("A", "One")]])))
        api.finishStream()
        await task.value

        XCTAssertEqual(m.rows.map(\.artist), ["A", "B"])
        XCTAssertEqual(row(m, "A", "One")?.status, .cached(dropD, source: "web", confirmed: false))
        XCTAssertEqual(m.lastSummary, "Preview: 1 would be added to 1 playlist")
        XCTAssertEqual(m.selection, .playlist("PL"))
        XCTAssertEqual(m.instrument, .bass)
    }

    /// 2. select(.playlist) clears rows at once; preview/sort do nothing while rows are loading.
    /// The runs are fired in tasks (not awaited) so a misbehaving model cannot hang the suite.
    func testSelectClearsRowsImmediatelyAndRunsAreBlockedWhileLoading() async throws {
        let (m, api) = makeModel { s in
            s.tracks["Mix"] = .success([self.ts("M", "One", .unknown)])
            s.tracks["PL"] = .success([self.ts("A", "One", .unknown), self.ts("B", "Two", .unknown)])
        }
        await m.select(.playlist("Mix"))
        XCTAssertEqual(m.rows.count, 1)

        let gate = Gate()
        api.configure { $0.tracksGate["PL"] = gate }
        let selectTask = Task { await m.select(.playlist("PL")) }
        try await api.waitForCall("tracks:bass:PL")
        XCTAssertEqual(m.rows, [], "rows must be cleared before the fetch returns")

        let previewTask = Task { await m.preview() }
        let sortTask = Task { await m.sort() }
        try await Task.sleep(nanoseconds: 200_000_000)
        let requests = api.sortRequests.count
        // Unblock anything that wrongly started, so nothing is left hanging.
        api.finishStream()
        api.finishStream()
        XCTAssertEqual(requests, 0, "no sort while the playlist is still loading")
        XCTAssertEqual(m.runState, .idle)

        gate.open()
        await selectTask.value
        XCTAssertEqual(m.rows.count, 2)
        _ = previewTask
        _ = sortTask
    }

    /// 3. A refreshRow fetch that completes after a run started must not overwrite the run's rows.
    func testRefreshRowFinishingAfterRunStartedDoesNotOverwriteRows() async throws {
        let (m, api) = try await playlistModel()
        let gate = Gate()
        api.configure { $0.tracksGate["PL"] = gate }
        let refresh = Task { await m.refreshRow(artist: "A", title: "One") }
        try await api.waitForCall("tracks:bass:PL", count: 2)

        // What the refresh will return if it is (wrongly) applied.
        api.configure { s in
            s.tracks["PL"] = .success([self.ts("A", "One", .cached(tuning: self.dropD, source: "manual", confirmed: true)),
                                       self.ts("B", "Two", .unknown)])
        }
        let task = try await startPreview(m, api)
        api.yield(.event(.start(SortStart(i: 1, total: 2, artist: "A", title: "One"))))
        try await waitUntil("lookingUp") { self.row(m, "A", "One")?.status == .lookingUp }

        gate.open()
        await refresh.value
        XCTAssertEqual(row(m, "A", "One")?.status, .lookingUp)

        api.yield(.finished(report()))
        api.finishStream()
        await task.value
        XCTAssertEqual(row(m, "A", "One")?.status, .unknown)
    }

    /// 5. CancellationError from the API sets no banner.
    func testCancellationErrorSetsNoBanner() async throws {
        let (m, _) = makeModel { s in
            s.playlists = .failure(CancellationError())
            s.tracks["PL"] = .failure(CancellationError())
        }
        await m.load()
        XCTAssertNil(m.banner)
        await m.select(.playlist("PL"))
        XCTAssertNil(m.banner)
    }

    /// 6. stop() before api.sort returns still cancels once the run exists.
    func testStopBeforeSortReturnsStillCancelsRun() async throws {
        let (m, api) = try await playlistModel()
        let gate = Gate()
        api.configure { $0.sortGate = gate }
        let task = Task { await m.preview() }
        try await api.waitForCall("sort")

        let stopTask = Task { await m.stop() }
        try await Task.sleep(nanoseconds: 50_000_000)
        gate.open()

        try await waitUntil("cancel call") { !api.cancelledRunIDs.isEmpty }
        XCTAssertEqual(api.cancelledRunIDs, [FakeHelperAPI.firstRunID])

        api.yield(.finished(report(cancelled: true)))
        api.finishStream()
        await task.value
        await stopTask.value
        XCTAssertEqual(m.runState, .idle)
    }

    /// 7. lastSummary is cleared when a new run starts.
    func testLastSummaryClearedWhenNewRunStarts() async throws {
        let (m, api) = try await playlistModel()
        try await finishedPreview(m, api, report(added: ["Bass – Drop D": [track("A", "1")]]))
        XCTAssertNotNil(m.lastSummary)

        let task = Task { await m.sort() }
        try await api.waitForSort(2)
        try await waitUntil("running") { self.m_isRunning(m) }
        XCTAssertNil(m.lastSummary)

        api.yield(.finished(report()))
        api.finishStream()
        await task.value
        XCTAssertEqual(m.lastSummary, "Added 0 to 0 playlists")
    }
}
