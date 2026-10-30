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

/// Runs the helper as a child process and talks to it over stdin/stdout. Its stderr is
/// kept (last 50 lines) for the Settings log.
public final class ProcessTransport: Transport, @unchecked Sendable {
    private static let tailLimit = 50

    private let process = Process()
    private let stdin = Pipe()
    private let stdout = Pipe()
    private let stderr = Pipe()
    private let continuation: AsyncThrowingStream<Data, Error>.Continuation
    public let lines: AsyncThrowingStream<Data, Error>

    // Guarded by `lock`.
    private let lock = NSLock()
    private var tail: [String] = []
    private var stdinClosed = false
    private var stdoutDone = false
    private var exited = false
    private var finished = false
    private var outSplitter = LineSplitter()
    private var errSplitter = LineSplitter()

    /// Launches `executable` with `arguments`. Throws `ClientError.helperNotFound(path:)`
    /// when the file is missing.
    public init(executable: URL, arguments: [String]) throws {
        guard FileManager.default.fileExists(atPath: executable.path) else {
            throw ClientError.helperNotFound(path: executable.path)
        }
        // A write to a helper that has exited must fail, not kill the app.
        signal(SIGPIPE, SIG_IGN)
        (lines, continuation) = AsyncThrowingStream<Data, Error>.makeStream()
        process.executableURL = executable
        process.arguments = arguments
        process.standardInput = stdin
        process.standardOutput = stdout
        process.standardError = stderr

        stdout.fileHandleForReading.readabilityHandler = { [weak self] handle in
            self?.readStdout(handle.availableData, from: handle)
        }
        stderr.fileHandleForReading.readabilityHandler = { [weak self] handle in
            self?.readStderr(handle.availableData, from: handle)
        }
        process.terminationHandler = { [weak self] _ in
            self?.markExited()
        }
        do {
            try process.run()
        } catch {
            stdout.fileHandleForReading.readabilityHandler = nil
            stderr.fileHandleForReading.readabilityHandler = nil
            throw error
        }
    }

    deinit {
        close()
    }

    /// The helper's last 50 stderr lines, oldest first.
    public var stderrTail: [String] {
        lock.withLock { tail }
    }

    public func write(_ line: Data) async throws {
        try lock.withLock {
            guard !stdinClosed, !exited else {
                throw ClientError.helperExited(stderrTail: tail)
            }
            var bytes = line
            bytes.append(UInt8(ascii: "\n"))
            do {
                try stdin.fileHandleForWriting.write(contentsOf: bytes)
            } catch {
                throw ClientError.helperExited(stderrTail: tail)
            }
        }
    }

    /// Closes the helper's stdin, which cancels a running sort; the helper then exits.
    public func close() {
        lock.withLock {
            guard !stdinClosed else { return }
            stdinClosed = true
            try? stdin.fileHandleForWriting.close()
        }
    }

    // MARK: - Pipe handlers (Foundation's background queues)

    private func readStdout(_ data: Data, from handle: FileHandle) {
        var out: [Data] = []
        lock.withLock {
            if data.isEmpty {
                handle.readabilityHandler = nil
                if let rest = outSplitter.flush() { out.append(rest) }
                stdoutDone = true
            } else {
                out = outSplitter.feed(data)
            }
        }
        for line in out { continuation.yield(line) }
        finishIfDone()
    }

    private func readStderr(_ data: Data, from handle: FileHandle) {
        lock.withLock {
            var new: [Data]
            if data.isEmpty {
                handle.readabilityHandler = nil
                new = errSplitter.flush().map { [$0] } ?? []
            } else {
                new = errSplitter.feed(data)
            }
            tail.append(contentsOf: new.map { String(decoding: $0, as: UTF8.self) })
            if tail.count > Self.tailLimit {
                tail.removeFirst(tail.count - Self.tailLimit)
            }
        }
    }

    private func markExited() {
        lock.withLock { exited = true }
        finishIfDone()
    }

    /// Ends `lines` once the helper has exited and all its stdout has been read.
    private func finishIfDone() {
        let tailNow: [String]? = lock.withLock {
            guard exited, stdoutDone, !finished else { return nil }
            finished = true
            return tail
        }
        if let tailNow {
            continuation.finish(throwing: ClientError.helperExited(stderrTail: tailNow))
        }
    }
}
