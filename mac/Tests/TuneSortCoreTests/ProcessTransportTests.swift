import XCTest
@testable import TuneSortCore

final class ProcessTransportTests: XCTestCase {
    private func make(_ script: String) throws -> ProcessTransport {
        try ProcessTransport(executable: URL(fileURLWithPath: "/bin/sh"), arguments: ["-c", script])
    }

    /// Drains the transport's lines; returns the lines seen and the terminating error (nil if ended normally).
    private func drain(_ t: ProcessTransport) async throws -> (lines: [String], error: Error?) {
        let box = try await withTimeout { () -> DrainResult in
            var out: [String] = []
            do {
                for try await l in t.lines { out.append(String(decoding: l, as: UTF8.self)) }
                return DrainResult(lines: out, error: nil)
            } catch {
                return DrainResult(lines: out, error: error)
            }
        }
        return (box.lines, box.error)
    }

    private struct DrainResult: @unchecked Sendable {
        let lines: [String]
        let error: Error?
    }

    func testExitCarriesFinalStderrLines() async throws {
        for i in 0..<20 {
            let t = try make("echo one >&2; echo two >&2; exit 3")
            let r = try await drain(t)
            XCTAssertEqual(r.error as? ClientError, .helperExited(stderrTail: ["one", "two"]), "iteration \(i)")
            XCTAssertEqual(t.stderrTail, ["one", "two"], "iteration \(i)")
        }
    }

    func testStdoutLinesThenExit() async throws {
        let t = try make("printf 'a\\nb\\n'; exit 0")
        let r = try await drain(t)
        XCTAssertEqual(r.lines, ["a", "b"])
        guard case .helperExited? = r.error as? ClientError else {
            return XCTFail("expected helperExited, got \(String(describing: r.error))")
        }
    }

    func testWriteAfterExitThrowsHelperExited() async throws {
        let t = try make("exit 0")
        _ = try await drain(t)
        do {
            try await withTimeout { try await t.write(Data("hello".utf8)) }
            XCTFail("expected write to throw")
        } catch {
            guard case .helperExited? = error as? ClientError else {
                return XCTFail("expected helperExited, got \(error)")
            }
        }
    }

    func testCloseMakesHelperExit() async throws {
        let t = try make("cat")
        try await withTimeout { try await t.write(Data("hi".utf8)) }
        let first = try await withTimeout { () -> String? in
            var it = t.lines.makeAsyncIterator()
            let l = try await it.next()
            return l.map { String(decoding: $0, as: UTF8.self) }
        }
        XCTAssertEqual(first, "hi")
        t.close()
        // The first iterator above was a copy; the stream is single-consumer but buffered state continues.
        let r = try await drain(t)
        guard case .helperExited? = r.error as? ClientError else {
            return XCTFail("expected helperExited, got \(String(describing: r.error))")
        }
    }

    func testStderrTailKeepsLast50() async throws {
        let t = try make("i=1; while [ $i -le 60 ]; do echo $i >&2; i=$((i+1)); done; exit 1")
        let r = try await drain(t)
        let expected = (11...60).map(String.init)
        XCTAssertEqual(r.error as? ClientError, .helperExited(stderrTail: expected))
        XCTAssertEqual(t.stderrTail, expected)
    }

    func testStderrBurstAfterStdoutClosed() async throws {
        let expected = (250...299).map { "err \($0)" }
        for i in 0..<50 {
            let t = try make(#"exec 1>&-; i=0; while [ $i -lt 300 ]; do echo "err $i" >&2; i=$((i+1)); done; exit 2"#)
            let r = try await drain(t)
            XCTAssertEqual(r.error as? ClientError, .helperExited(stderrTail: expected), "iteration \(i)")
            XCTAssertEqual(t.stderrTail, expected, "iteration \(i)")
        }
    }
}
