import Foundation

/// Errors from talking to the helper.
public enum ClientError: Error, Equatable, Sendable {
    /// The helper executable doesn't exist at `path`.
    case helperNotFound(path: String)
    /// The helper exited (or its output ended); its last stderr lines.
    case helperExited(stderrTail: [String])
    /// `hello` reported a protocol version other than the one this app speaks.
    case protocolMismatch(helper: Int, expected: Int)
    /// The helper's error reply: `{"error": {"kind", "message"}}`.
    case helper(kind: String, message: String)
}

/// A line-oriented connection to the helper.
public protocol Transport: Sendable {
    /// Writes one line; `line` has no trailing `\n` (the transport adds it).
    func write(_ line: Data) async throws
    /// The helper's output lines, without `\n`. Single consumer. Ends by throwing
    /// `ClientError.helperExited(stderrTail:)` when the helper exits.
    var lines: AsyncThrowingStream<Data, Error> { get }
}

/// Runs the helper as a child process and talks to it over stdin/stdout.
public final class ProcessTransport: Transport, @unchecked Sendable {
    /// Launches `executable` with `arguments`. Throws `ClientError.helperNotFound(path:)`
    /// when the file is missing.
    public init(executable: URL, arguments: [String]) throws {
        fatalError("unimplemented")
    }

    /// The helper's last 50 stderr lines, oldest first.
    public var stderrTail: [String] {
        fatalError("unimplemented")
    }

    public var lines: AsyncThrowingStream<Data, Error> {
        fatalError("unimplemented")
    }

    public func write(_ line: Data) async throws {
        fatalError("unimplemented")
    }

    /// Closes the helper's stdin, which cancels a running sort; the helper then exits.
    public func close() {
        fatalError("unimplemented")
    }
}
