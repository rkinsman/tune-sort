import XCTest
@testable import TuneSortCore

final class TuningPlaylistsTests: XCTestCase {
    func testBassNamesMatchBassOnly() {
        for name in ["Bass – Drop D", "Bass 5-String – B Standard", "Bass 6-String – Drop A"] {
            XCTAssertTrue(isTuningPlaylist(name, for: .bass), name)
            XCTAssertFalse(isTuningPlaylist(name, for: .guitar), name)
        }
    }

    func testGuitarNamesMatchGuitarOnly() {
        for name in ["Guitar – Drop D", "Guitar 7-String – B Standard"] {
            XCTAssertTrue(isTuningPlaylist(name, for: .guitar), name)
            XCTAssertFalse(isTuningPlaylist(name, for: .bass), name)
        }
    }

    func testHyphenInsteadOfEnDashDoesNotMatch() {
        XCTAssertFalse(isTuningPlaylist("Bass - Drop D", for: .bass))
        XCTAssertFalse(isTuningPlaylist("Guitar - Drop D", for: .guitar))
        XCTAssertFalse(isTuningPlaylist("Bass 5-String - B Standard", for: .bass))
    }

    func testOrdinaryPlaylistNamesDoNotMatch() {
        XCTAssertFalse(isTuningPlaylist("Bassline", for: .bass))
        XCTAssertFalse(isTuningPlaylist("Bass", for: .bass))
        XCTAssertFalse(isTuningPlaylist("Bass Favourites", for: .bass))
        XCTAssertFalse(isTuningPlaylist("Road Trip", for: .bass))
        XCTAssertFalse(isTuningPlaylist("", for: .bass))
        XCTAssertFalse(isTuningPlaylist("Bass5-String – X", for: .bass))
    }

    func testMissingSpacesAroundDashDoNotMatch() {
        XCTAssertFalse(isTuningPlaylist("Bass–Drop D", for: .bass))
        XCTAssertFalse(isTuningPlaylist("Bass –Drop D", for: .bass))
    }

    /// Decision: a name with nothing after the dash ("Bass – ") is not a tuning playlist.
    func testEmptyTuningPartDoesNotMatch() {
        XCTAssertFalse(isTuningPlaylist("Bass – ", for: .bass))
        XCTAssertFalse(isTuningPlaylist("Guitar – ", for: .guitar))
    }
}
