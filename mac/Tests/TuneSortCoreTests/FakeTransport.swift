import Foundation
@testable import TuneSortCore

struct TestTimeout: Error {}

private final class Once<T: Sendable>: @unchecked Sendable {
    private let lock = NSLock()
    private var cont: CheckedContinuation<T, Error>?
    init(_ cont: CheckedContinuation<T, Error>) { self.cont = cont }
    func resume(_ result: Result<T, Error>) {
        let c: CheckedContinuation<T, Error>? = lock.withLock {
            let c = cont
            cont = nil
            return c
        }
        c?.resume(with: result)
    }
}

/// Runs `op`, failing with TestTimeout if it does not finish in time (never hangs the suite).
func withTimeout<T: Sendable>(
    _ seconds: Double = 5,
    _ op: @escaping @Sendable () async throws -> T
) async throws -> T {
    try await withCheckedThrowingContinuation { (cont: CheckedContinuation<T, Error>) in
        let once = Once(cont)
        Task {
            do { once.resume(.success(try await op())) } catch { once.resume(.failure(error)) }
        }
        Task {
            try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            once.resume(.failure(TestTimeout()))
        }
    }
}

final class FakeTransport: Transport, @unchecked Sendable {
    private let lock = NSLock()
    private var written: [Data] = []
    private let continuation: AsyncThrowingStream<Data, Error>.Continuation
    let lines: AsyncThrowingStream<Data, Error>

    init() {
        let (stream, cont) = AsyncThrowingStream<Data, Error>.makeStream()
        lines = stream
        continuation = cont
    }

    func write(_ line: Data) async throws {
        lock.withLock { written.append(line) }
    }

    var writtenLines: [Data] { lock.withLock { written } }

    /// Waits (bounded) until at least `count` lines have been written; returns all written lines.
    func waitForWrites(_ count: Int, timeout: Double = 5) async throws -> [Data] {
        let deadline = Date().addingTimeInterval(timeout)
        while true {
            let current = writtenLines
            if current.count >= count { return current }
            if Date() > deadline { throw TestTimeout() }
            try await Task.sleep(nanoseconds: 2_000_000)
        }
    }

    func push(_ line: String) { continuation.yield(Data(line.utf8)) }
    func finish() { continuation.finish() }
    func finish(throwing error: Error) { continuation.finish(throwing: error) }
}

/// Decoded view of a written request line.
struct SentRequest {
    let id: Int
    let cmd: String
    let args: NSDictionary
    let keys: Set<String>

    init(_ data: Data) throws {
        let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
        id = obj["id"] as? Int ?? -1
        cmd = obj["cmd"] as? String ?? ""
        args = obj["args"] as? NSDictionary ?? NSDictionary()
        keys = Set(obj.keys)
    }

    func argsEqual(_ json: String) throws -> Bool {
        let exp = try JSONSerialization.jsonObject(with: Data(json.utf8)) as? NSDictionary
        return exp == args
    }
}
