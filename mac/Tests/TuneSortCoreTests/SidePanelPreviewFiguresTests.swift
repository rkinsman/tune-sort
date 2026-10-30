import XCTest
@testable import TuneSortCore

@MainActor
final class SidePanelPreviewFiguresTests: XCTestCase {
    private func ts(_ a: String, _ t: String) -> TrackState {
        TrackState(track: Track(artist: a, title: t, persistentId: "id-\(a)-\(t)"), state: .unknown)
    }

    private func previewed() async throws -> (SidePanelModel, AppModel, FakeHelperAPI) {
        let api = FakeHelperAPI()
        api.configure { $0.tracks["PL"] = .success([self.ts("A", "One"), self.ts("B", "Two")]) }
        let app = AppModel(api: api)
        await app.select(.playlist("PL"))
        app.selectedRowID = try XCTUnwrap(app.rows.first { $0.artist == "A" }).id
        let p = SidePanelModel(api: api, app: app)

        let task = Task { await app.preview() }
        try await api.waitForSort()
        let t = Track(artist: "A", title: "One", persistentId: "id-A-One")
        api.yield(.finished(Report(cancelled: false, createdPlaylists: [], added: ["Bass – Drop D": [t]],
                                   alreadyPresent: [:], review: [], lookupFailed: [], addErrors: [])))
        api.finishStream()
        try await withTimeout { await task.value }
        XCTAssertEqual(app.sortConfirmation(), "Add 1 song to 1 playlist?")
        return (p, app, api)
    }

    private let fallback = "Sort 'PL' into tuning playlists?"

    func testSaveClearsPreviewFigures() async throws {
        let (p, app, _) = try await previewed()
        p.typed = "Drop D"
        try await withTimeout { await p.save() }
        XCTAssertEqual(app.sortConfirmation(), fallback)
    }

    func testClearClearsPreviewFigures() async throws {
        let (p, app, _) = try await previewed()
        try await withTimeout { await p.clear() }
        XCTAssertEqual(app.sortConfirmation(), fallback)
    }

    func testUseClearsPreviewFigures() async throws {
        let (p, app, _) = try await previewed()
        let m = MatchInfo(tuning: TuningInfo(name: "Drop D", playlistName: "Bass – Drop D", notes: ""),
                          source: "web", url: "u", matchedArtist: "m", matchedTitle: "t", exact: true)
        try await withTimeout { await p.use(m) }
        XCTAssertEqual(app.sortConfirmation(), fallback)
    }
}
