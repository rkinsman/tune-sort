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
    /// How long `lines` waits for stderr's EOF once the helper has exited and stdout has
    /// ended. Normally EOF comes within milliseconds; this only bounds the case where a
    /// grandchild process inherited stderr and keeps it open.
    private static let stderrGrace: DispatchTimeInterval = .seconds(2)

    private let process = Process()
    private let stdin = Pipe()
    private let stdout = Pipe()
    private let stderr = Pipe()
    private let continuation: AsyncThrowingStream<Data, Error>.Continuation
    public let lines: AsyncThrowingStream<Data, Error>

    /// Serializes writes to stdin. Separate from `lock`, so a blocking write (full pipe)
    /// never stalls the read handlers.
    private let writeLock = NSLock()
    // Guarded by `lock`.
    private let lock = NSLock()
    private var tail: [String] = []
    private var stdinClosed = false
    private var stdoutDone = false
    private var stderrDone = false
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
        stdout.fileHandleForReading.readabilityHandler = nil
        stderr.fileHandleForReading.readabilityHandler = nil
        process.terminationHandler = nil
        close()
    }

    /// The helper's last 50 stderr lines, oldest first.
    public var stderrTail: [String] {
        lock.withLock { tail }
    }

    public func write(_ line: Data) async throws {
        var bytes = line
        bytes.append(UInt8(ascii: "\n"))
        try writeLock.withLock {
            // `stdinClosed` only changes under `writeLock` too, so stdin can't be closed
            // mid-write.
            let gone = lock.withLock { stdinClosed || exited }
            guard !gone else { throw ClientError.helperExited(stderrTail: stderrTail) }
            do {
                try stdin.fileHandleForWriting.write(contentsOf: bytes)
            } catch {
                throw ClientError.helperExited(stderrTail: stderrTail)
            }
        }
    }

    /// Closes the helper's stdin, which cancels a running sort; the helper then exits.
    /// Waits for a write in progress to finish.
    public func close() {
        writeLock.withLock {
            let alreadyClosed = lock.withLock {
                defer { stdinClosed = true }
                return stdinClosed
            }
            if !alreadyClosed { try? stdin.fileHandleForWriting.close() }
        }
    }

    // MARK: - Pipe handlers (Foundation's background queues)

    private func readStdout(_ data: Data, from handle: FileHandle) {
        if data.isEmpty {
            handle.readabilityHandler = nil
            // Yield the leftover partial line before marking stdout done, so no finish
            // can come between.
            if let rest = lock.withLock({ outSplitter.flush() }) { continuation.yield(rest) }
            lock.withLock { stdoutDone = true }
            finishIfDone()
        } else {
            for line in lock.withLock({ outSplitter.feed(data) }) { continuation.yield(line) }
        }
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
            if data.isEmpty { stderrDone = true }
        }
        if data.isEmpty { finishIfDone() }
    }

    private func markExited() {
        lock.withLock { exited = true }
        finishIfDone()
    }

    /// Ends `lines` once the helper has exited and all of its stdout and stderr has been
    /// read, so the error carries the complete stderr tail. If stderr stays open (a
    /// grandchild holds it), finishes anyway after `stderrGrace`.
    private func finishIfDone(force: Bool = false) {
        enum Step { case none, finish([String]), wait }
        let step: Step = lock.withLock {
            guard exited, stdoutDone, !finished else { return .none }
            guard stderrDone || force else { return .wait }
            finished = true
            return .finish(tail)
        }
        switch step {
        case .none:
            break
        case let .finish(tailNow):
            continuation.finish(throwing: ClientError.helperExited(stderrTail: tailNow))
        case .wait:
            DispatchQueue.global().asyncAfter(deadline: .now() + Self.stderrGrace) { [weak self] in
                self?.finishIfDone(force: true)
            }
        }
    }
}
