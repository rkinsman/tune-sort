import XCTest
@testable import TuneSortCore

final class HelperClientReviewCountsTests: XCTestCase {
    func testReviewCountsSendsCommandAndDecodesObject() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let task = Task { try await client.reviewCounts(.bass) }
        let lines = try await t.waitForWrites(1)
        let r = try SentRequest(lines[0])
        XCTAssertEqual(r.id, 1)
        XCTAssertEqual(r.cmd, "review_counts")
        XCTAssertEqual(r.keys, ["id", "cmd", "args"])
        XCTAssertTrue(try r.argsEqual(#"{"instrument":"bass"}"#), "args were \(r.args)")
        t.push(#"{"id":1,"result":{"Drop D":2,"Gym":1}}"#)
        let counts = try await withTimeout { try await task.value }
        XCTAssertEqual(counts, ["Drop D": 2, "Gym": 1])
    }

    func testReviewCountsUsesGuitarInstrumentAndDecodesEmpty() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let task = Task { try await client.reviewCounts(.guitar) }
        let lines = try await t.waitForWrites(1)
        let r = try SentRequest(lines[0])
        XCTAssertEqual(r.cmd, "review_counts")
        XCTAssertTrue(try r.argsEqual(#"{"instrument":"guitar"}"#), "args were \(r.args)")
        t.push(#"{"id":1,"result":{}}"#)
        let counts = try await withTimeout { try await task.value }
        XCTAssertEqual(counts, [:])
    }

    func testReviewCountsErrorReplyThrowsHelperError() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let task = Task { try await client.reviewCounts(.bass) }
        _ = try await t.waitForWrites(1)
        t.push(#"{"id":1,"error":{"kind":"music","message":"Music is closed"}}"#)
        do {
            _ = try await withTimeout { try await task.value }
            XCTFail("expected error")
        } catch {
            XCTAssertEqual(error as? ClientError, .helper(kind: "music", message: "Music is closed"))
        }
    }
}
