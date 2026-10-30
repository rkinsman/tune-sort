import XCTest
@testable import TuneSortCore

final class LineSplitterTests: XCTestCase {
    private func d(_ s: String) -> Data { Data(s.utf8) }

    func testOneLineInOneChunk() {
        var s = LineSplitter()
        XCTAssertEqual(s.feed(d("hello\n")), [d("hello")])
    }

    func testNoNewlineYieldsNothing() {
        var s = LineSplitter()
        XCTAssertEqual(s.feed(d("hello")), [])
    }

    func testOneLineSplitAcrossThreeChunks() {
        var s = LineSplitter()
        XCTAssertEqual(s.feed(d("he")), [])
        XCTAssertEqual(s.feed(d("llo")), [])
        XCTAssertEqual(s.feed(d("!\n")), [d("hello!")])
    }

    func testThreeLinesInOneChunk() {
        var s = LineSplitter()
        XCTAssertEqual(s.feed(d("a\nbb\nccc\n")), [d("a"), d("bb"), d("ccc")])
    }

    func testTrailingPartialKeptForNextFeed() {
        var s = LineSplitter()
        XCTAssertEqual(s.feed(d("one\ntw")), [d("one")])
        XCTAssertEqual(s.feed(d("o\nthree")), [d("two")])
        XCTAssertEqual(s.feed(d("\n")), [d("three")])
    }

    func testMultiByteCharSplitAcrossChunks() throws {
        var s = LineSplitter()
        let bytes = Array("Sigur Rós\n".utf8)
        // "ó" is 0xC3 0xB3; split between its two bytes.
        let idx = try XCTUnwrap(bytes.firstIndex(of: 0xC3))
        XCTAssertEqual(s.feed(Data(bytes[...idx])), [])
        let out = s.feed(Data(bytes[(idx + 1)...]))
        XCTAssertEqual(out.count, 1)
        XCTAssertEqual(String(data: out[0], encoding: .utf8), "Sigur Rós")
    }
}
