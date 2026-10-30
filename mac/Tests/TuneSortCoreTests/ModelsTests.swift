import XCTest
@testable import TuneSortCore

final class ModelsTests: XCTestCase {
    private let dec = JSONDecoder()
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try dec.decode(type, from: Data(json.utf8))
    }

    private let tuningJSON = #"{"name":"Drop D","playlist_name":"Bass – Drop D","notes":"D A D G"}"#
    private let tuning = TuningInfo(name: "Drop D", playlistName: "Bass – Drop D", notes: "D A D G")

    func testTrack() throws {
        let t = try decode(Track.self, #"{"artist":"A","title":"T","persistent_id":"P1"}"#)
        XCTAssertEqual(t, Track(artist: "A", title: "T", persistentId: "P1"))
    }

    func testTuningInfo() throws {
        XCTAssertEqual(try decode(TuningInfo.self, tuningJSON), tuning)
    }

    func testMatchInfo() throws {
        let m = try decode(MatchInfo.self, """
        {"tuning":\(tuningJSON),"source":"web","url":"http://x","matched_artist":"MA","matched_title":"MT","exact":true}
        """)
        XCTAssertEqual(m, MatchInfo(tuning: tuning, source: "web", url: "http://x",
                                    matchedArtist: "MA", matchedTitle: "MT", exact: true))
    }

    func testCachedSong() throws {
        let c = try decode(CachedSong.self, """
        {"artist":"A","title":"T","tuning":\(tuningJSON),"source":"manual","confirmed":false}
        """)
        XCTAssertEqual(c, CachedSong(artist: "A", title: "T", tuning: tuning, source: "manual", confirmed: false))
    }

    func testTrackStateCached() throws {
        let s = try decode(TrackState.self, """
        {"artist":"A","title":"T","persistent_id":"P","state":"cached","tuning":\(tuningJSON),"source":"manual","confirmed":true}
        """)
        XCTAssertEqual(s.track, Track(artist: "A", title: "T", persistentId: "P"))
        XCTAssertEqual(s.state, .cached(tuning: tuning, source: "manual", confirmed: true))
    }

    func testTrackStateReview() throws {
        let m = MatchInfo(tuning: tuning, source: "web", url: "u", matchedArtist: "a", matchedTitle: "t", exact: false)
        let s = try decode(TrackState.self, """
        {"artist":"A","title":"T","persistent_id":"P","state":"review","candidates":[
        {"tuning":\(tuningJSON),"source":"web","url":"u","matched_artist":"a","matched_title":"t","exact":false}]}
        """)
        XCTAssertEqual(s.state, .review(candidates: [m]))
    }

    func testTrackStateUnknown() throws {
        let s = try decode(TrackState.self, #"{"artist":"A","title":"T","persistent_id":"P","state":"unknown"}"#)
        XCTAssertEqual(s.state, .unknown)
        XCTAssertEqual(s.track.persistentId, "P")
    }

    func testTrackStateBadStateFails() {
        XCTAssertThrowsError(try decode(TrackState.self,
            #"{"artist":"A","title":"T","persistent_id":"P","state":"bogus"}"#))
    }

    func testReviewItem() throws {
        let r = try decode(ReviewItem.self, #"{"artist":"A","title":"T","candidates":[]}"#)
        XCTAssertEqual(r, ReviewItem(artist: "A", title: "T", candidates: []))
    }

    func testAddError() throws {
        let e = try decode(AddError.self, """
        {"track":{"artist":"A","title":"T","persistent_id":"P"},"playlist":"PL","error":"nope"}
        """)
        XCTAssertEqual(e, AddError(track: Track(artist: "A", title: "T", persistentId: "P"), playlist: "PL", error: "nope"))
    }

    func testReport() throws {
        let t = #"{"artist":"A","title":"T","persistent_id":"P"}"#
        let track = Track(artist: "A", title: "T", persistentId: "P")
        let r = try decode(Report.self, """
        {"cancelled":true,"created_playlists":["X"],"added":{"X":[\(t)]},"already_present":{"Y":[\(t)]},
        "review":[\(t)],"lookup_failed":[\(t)],
        "add_errors":[{"track":\(t),"playlist":"X","error":"bad"}]}
        """)
        XCTAssertEqual(r, Report(cancelled: true, createdPlaylists: ["X"], added: ["X": [track]],
                                 alreadyPresent: ["Y": [track]], review: [track], lookupFailed: [track],
                                 addErrors: [AddError(track: track, playlist: "X", error: "bad")]))
    }

    func testSortStart() throws {
        let s = try decode(SortStart.self, #"{"i":2,"total":10,"artist":"A","title":"T"}"#)
        XCTAssertEqual(s, SortStart(i: 2, total: 10, artist: "A", title: "T"))
    }

    func testDoneStatusRawValues() {
        XCTAssertEqual(DoneStatus.added.rawValue, "added")
        XCTAssertEqual(DoneStatus.alreadyPresent.rawValue, "already_present")
        XCTAssertEqual(DoneStatus.review.rawValue, "review")
        XCTAssertEqual(DoneStatus.lookupFailed.rawValue, "lookup_failed")
        XCTAssertEqual(DoneStatus.addError.rawValue, "add_error")
    }

    func testSortDoneMinimalAndFull() throws {
        let a = try decode(SortDone.self, #"{"artist":"A","title":"T","status":"review"}"#)
        XCTAssertEqual(a, SortDone(artist: "A", title: "T", status: .review))
        let b = try decode(SortDone.self, """
        {"artist":"A","title":"T","status":"add_error","tuning":\(tuningJSON),"source":"web","playlist":"PL","failed":["x"],"error":"e"}
        """)
        XCTAssertEqual(b, SortDone(artist: "A", title: "T", status: .addError, tuning: tuning,
                                   source: "web", playlist: "PL", failed: ["x"], error: "e"))
    }

    func testSortEventStartAndDone() throws {
        let s = try decode(SortEvent.self, #"{"id":3,"event":"start","data":{"i":1,"total":2,"artist":"A","title":"T"}}"#)
        XCTAssertEqual(s, .start(SortStart(i: 1, total: 2, artist: "A", title: "T")))
        let d = try decode(SortEvent.self, #"{"id":3,"event":"done","data":{"artist":"A","title":"T","status":"added","playlist":"PL"}}"#)
        XCTAssertEqual(d, .done(SortDone(artist: "A", title: "T", status: .added, playlist: "PL")))
    }

    func testSortEventUnknownKindFails() {
        XCTAssertThrowsError(try decode(SortEvent.self, #"{"event":"weird","data":{}}"#))
    }

    func testConfigInfo() throws {
        let c = try decode(ConfigInfo.self, """
        {"path":"/p/c.toml","exists":true,"order":{"bass":["a","b"],"guitar":["c"]},"sources":{"bass":["s"],"guitar":[]}}
        """)
        XCTAssertEqual(c, ConfigInfo(path: "/p/c.toml", exists: true,
                                     order: [.bass: ["a", "b"], .guitar: ["c"]],
                                     sources: [.bass: ["s"], .guitar: []]))
    }

    func testSortRequestOmitsNilOptionals() throws {
        let data = try JSONEncoder().encode(SortRequest(instrument: .bass, playlist: "PL", dryRun: true))
        let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? NSDictionary)
        let expected: NSDictionary = ["instrument": "bass", "playlist": "PL", "dry_run": true, "recheck": false]
        XCTAssertEqual(obj, expected)
    }

    func testSortRequestIncludesOptionalsWhenSet() throws {
        let data = try JSONEncoder().encode(SortRequest(instrument: .guitar, playlist: "PL", dryRun: false,
                                                        order: ["a"], source: "web", recheck: true))
        let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? NSDictionary)
        let expected: NSDictionary = ["instrument": "guitar", "playlist": "PL", "dry_run": false,
                                      "recheck": true, "order": ["a"], "source": "web"]
        XCTAssertEqual(obj, expected)
    }

    func testSpecialCharacterNamesSurvive() throws {
        let a = try decode(Track.self, #"{"artist":"Sigur Rós","title":"Hoppípolla","persistent_id":"1"}"#)
        XCTAssertEqual(a.artist, "Sigur Rós")
        XCTAssertEqual(a.title, "Hoppípolla")
        let b = try decode(Track.self, #"{"artist":"AC/DC","title":"T.N.T.","persistent_id":"2"}"#)
        XCTAssertEqual(b.artist, "AC/DC")
    }
}
