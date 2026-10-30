import XCTest
@testable import TuneSortCore

@MainActor
final class CanRunTests: XCTestCase {
    private func ts(_ a: String, _ t: String) -> TrackState {
        TrackState(track: Track(artist: a, title: t, persistentId: "id-\(a)-\(t)"), state: .unknown)
    }

    private func make(_ configure: (inout FakeHelperAPI.State) -> Void = { _ in }) -> (AppModel, FakeHelperAPI) {
        let api = FakeHelperAPI()
        api.configure { s in
            s.playlists = .success(["PL", "Bass – Drop D"])
            s.tracks["PL"] = .success([self.ts("A", "One"), self.ts("B", "Two")])
            configure(&s)
        }
        return (AppModel(api: api), api)
    }

    func testFalseWithNoSelection() {
        let (m, _) = make()
        XCTAssertNil(m.selection)
        XCTAssertFalse(m.canRun)
    }

    func testFalseForNonPlaylistSelections() async {
        let (m, _) = make()
        await m.load()
        await m.select(.needsReview)
        XCTAssertFalse(m.canRun)
        await m.select(.allSongs)
        XCTAssertFalse(m.canRun)
        await m.select(.tuningPlaylist("Bass – Drop D"))
        XCTAssertFalse(m.canRun)
    }

    func testTrueForLoadedPlaylist() async {
        let (m, _) = make()
        await m.load()
        await m.select(.playlist("PL"))
        XCTAssertFalse(m.loadingRows)
        XCTAssertTrue(m.canRun)
    }

    func testFalseWhileRowsLoadThenTrue() async throws {
        let (m, api) = make()
        let gate = Gate()
        api.configure { $0.tracksGate["PL"] = gate }
        let task = Task { await m.select(.playlist("PL")) }
        try await api.waitForCall("tracks:bass:PL")
        XCTAssertTrue(m.loadingRows)
        XCTAssertFalse(m.canRun)
        gate.open()
        await task.value
        XCTAssertFalse(m.loadingRows)
        XCTAssertTrue(m.canRun)
    }

    func testLoadingEndsWhenRowsFail() async {
        let (m, _) = make { $0.tracks["PL"] = .failure(ClientError.helper(kind: "music", message: "no")) }
        await m.select(.playlist("PL"))
        XCTAssertFalse(m.loadingRows)
    }

    func testSetInstrumentResetsLoadingRows() async throws {
        let (m, api) = make()
        let gate = Gate()
        api.configure { $0.tracksGate["PL"] = gate }
        let task = Task { await m.select(.playlist("PL")) }
        try await api.waitForCall("tracks:bass:PL")
        XCTAssertTrue(m.loadingRows)
        await m.setInstrument(.guitar)
        XCTAssertFalse(m.loadingRows)
        gate.open()
        await task.value
    }

    func testFalseDuringRun() async throws {
        let (m, api) = make()
        await m.load()
        await m.select(.playlist("PL"))
        let task = Task { await m.preview() }
        try await api.waitForSort()
        XCTAssertNotEqual(m.runState, .idle)
        XCTAssertFalse(m.canRun)
        api.yield(.finished(Report(cancelled: false, createdPlaylists: [], added: [:], alreadyPresent: [:],
                                   review: [], lookupFailed: [], addErrors: [])))
        api.finishStream()
        await task.value
        XCTAssertEqual(m.runState, .idle)
        XCTAssertTrue(m.canRun)
    }

    func testFalseWithConfigBanner() async {
        let (m, _) = make { $0.sortError = ClientError.helper(kind: "config", message: "bad order") }
        await m.load()
        await m.select(.playlist("PL"))
        XCTAssertTrue(m.canRun)
        await m.sort()
        XCTAssertEqual(m.banner?.kind, .config)
        XCTAssertFalse(m.canRun)
    }

    func testTrueWithNonConfigBanner() async {
        let (m, _) = make { $0.sortError = ClientError.helper(kind: "music", message: "down") }
        await m.load()
        await m.select(.playlist("PL"))
        await m.sort()
        XCTAssertEqual(m.banner?.kind, .music)
        XCTAssertTrue(m.canRun)
    }
}
