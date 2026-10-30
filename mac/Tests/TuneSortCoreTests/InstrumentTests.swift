import XCTest
@testable import TuneSortCore

final class InstrumentTests: XCTestCase {
    private struct Wrapper: Codable {
        let instrument: Instrument
    }

    func testRawValues() {
        XCTAssertEqual(Instrument.bass.rawValue, "bass")
        XCTAssertEqual(Instrument.guitar.rawValue, "guitar")
    }

    func testDecodesFromJSONString() throws {
        let decoder = JSONDecoder()

        let list = try decoder.decode([Instrument].self, from: Data(#"["guitar"]"#.utf8))
        XCTAssertEqual(list, [.guitar])

        let wrapped = try decoder.decode(Wrapper.self, from: Data(#"{"instrument":"bass"}"#.utf8))
        XCTAssertEqual(wrapped.instrument, .bass)

        XCTAssertThrowsError(try decoder.decode([Instrument].self, from: Data(#"["banjo"]"#.utf8)))
        XCTAssertThrowsError(try decoder.decode(Wrapper.self, from: Data(#"{"instrument":"banjo"}"#.utf8)))
    }

    func testAllCases() {
        XCTAssertEqual(Instrument.allCases, [.bass, .guitar])
    }
}
