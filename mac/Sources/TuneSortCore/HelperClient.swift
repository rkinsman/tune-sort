import Foundation
import os

/// What `SortRun.updates` yields: progress events, then exactly one `.finished`.
public enum SortUpdate: Sendable, Equatable {
    case event(SortEvent)
    case finished(Report)
}

/// A running sort. `updates` yields its events then `.finished(report)` and ends; it ends
/// by throwing if the sort fails (`ClientError.helper`) or the helper exits.
public struct SortRun: Sendable {
    public let id: Int
    public let updates: AsyncThrowingStream<SortUpdate, Error>

    public init(id: Int, updates: AsyncThrowingStream<SortUpdate, Error>) {
        self.id = id
        self.updates = updates
    }
}

/// The helper's commands. View models depend on this, not on `HelperClient`.
public protocol HelperAPI: Sendable {
    func playlists() async throws -> [String]
    func tracks(_ i: Instrument, playlist: String) async throws -> [TrackState]
    func config() async throws -> ConfigInfo
    /// `nil` restores the default order. Returns the new effective order.
    func setOrder(_ i: Instrument, _ order: [String]?) async throws -> [String]
    func reviewList(_ i: Instrument) async throws -> [ReviewItem]
    /// For each playlist with songs in the review queue, how many: `review_counts`.
    func reviewCounts(_ i: Instrument) async throws -> [String: Int]
    func describe(_ i: Instrument, _ tuning: String) async throws -> TuningInfo
    func set(_ i: Instrument, artist: String, title: String, tuning: String) async throws -> CachedSong
    func entries(_ i: Instrument) async throws -> [CachedSong]
    func delete(_ i: Instrument, artist: String, title: String) async throws
    /// Sends `sort` and returns once it is written; the run's `updates` carry the rest.
    func sort(_ request: SortRequest) async throws -> SortRun
    /// Sends `cancel` for the run; throws the helper's `bad_request` if it isn't running.
    func cancel(_ run: SortRun) async throws
}

/// Speaks protocol version 1 to the helper over a `Transport`. Request ids start at 1.
///
/// One reader task (started on the first request) reads `transport.lines` and routes each
/// reply by `id`: plain requests resume their waiting caller, sorts feed their stream. Lines
/// that aren't JSON, or carry a null or unknown `id`, are logged and skipped. When the
/// transport ends, every pending request and running sort fails with its error
/// (`ClientError.helperExited` for a normal end), as do later requests.
public actor HelperClient: HelperAPI {
    public static let protocolVersion = 1

    private let transport: Transport
    private var nextId = 1
    private var reader: Task<Void, Never>?
    /// Set once the transport has ended.
    private var failure: Error?
    /// Plain requests sent (or being sent) and not yet answered.
    private var inFlight: Set<Int> = []
    /// Callers waiting for their reply.
    private var waiting: [Int: CheckedContinuation<Data, Error>] = [:]
    /// Replies that arrived before their caller started waiting.
    private var early: [Int: Result<Data, Error>] = [:]
    /// Running sorts.
    private var sorts: [Int: AsyncThrowingStream<SortUpdate, Error>.Continuation] = [:]

    private static let log = Logger(subsystem: "TuneSort", category: "helper")

    public init(transport: Transport) {
        self.transport = transport
    }

    /// Sends `hello`; throws `ClientError.protocolMismatch` unless the helper speaks version 1.
    public func start() async throws {
        let hello = try await call("hello", NoArgs(), as: Hello.self)
        guard hello.version == Self.protocolVersion else {
            throw ClientError.protocolMismatch(helper: hello.version, expected: Self.protocolVersion)
        }
    }

    public func playlists() async throws -> [String] {
        try await call("playlists", NoArgs(), as: [String].self)
    }

    public func tracks(_ i: Instrument, playlist: String) async throws -> [TrackState] {
        try await call("tracks", ["instrument": i.rawValue, "playlist": playlist], as: [TrackState].self)
    }

    public func config() async throws -> ConfigInfo {
        try await call("config", NoArgs(), as: ConfigInfo.self)
    }

    public func setOrder(_ i: Instrument, _ order: [String]?) async throws -> [String] {
        try await call("set_order", SetOrderArgs(instrument: i, order: order), as: [String].self)
    }

    public func reviewList(_ i: Instrument) async throws -> [ReviewItem] {
        try await call("review_list", ["instrument": i.rawValue], as: [ReviewItem].self)
    }

    public func describe(_ i: Instrument, _ tuning: String) async throws -> TuningInfo {
        try await call("describe", ["instrument": i.rawValue, "tuning": tuning], as: Described.self).tuning
    }

    public func set(_ i: Instrument, artist: String, title: String, tuning: String) async throws
        -> CachedSong
    {
        let args = ["instrument": i.rawValue, "artist": artist, "title": title, "tuning": tuning]
        return try await call("set", args, as: CachedSong.self)
    }

    public func reviewCounts(_ i: Instrument) async throws -> [String: Int] {
        try await call("review_counts", ["instrument": i.rawValue], as: [String: Int].self)
    }

    public func entries(_ i: Instrument) async throws -> [CachedSong] {
        try await call("entries", ["instrument": i.rawValue], as: [CachedSong].self)
    }

    public func delete(_ i: Instrument, artist: String, title: String) async throws {
        let args = ["instrument": i.rawValue, "artist": artist, "title": title]
        _ = try await send("delete", args)
    }

    public func sort(_ request: SortRequest) async throws -> SortRun {
        startReader()
        if let failure { throw failure }
        let id = takeId()
        let line = try Self.encode(id: id, cmd: "sort", args: request)
        let (updates, continuation) = AsyncThrowingStream<SortUpdate, Error>.makeStream()
        // Registered before writing, so no reply can arrive unrouted.
        sorts[id] = continuation
        do {
            try await transport.write(line)
        } catch {
            sorts.removeValue(forKey: id)?.finish(throwing: error)
            throw error
        }
        return SortRun(id: id, updates: updates)
    }

    public func cancel(_ run: SortRun) async throws {
        _ = try await send("cancel", ["id": run.id])
    }

    // MARK: - Requests

    private func call<A: Encodable & Sendable, R: Decodable>(
        _ cmd: String, _ args: A, as type: R.Type
    ) async throws -> R {
        let line = try await send(cmd, args)
        return try JSONDecoder().decode(ResultReply<R>.self, from: line).result
    }

    /// Sends one request and returns its success reply line; an error reply is thrown.
    private func send<A: Encodable & Sendable>(_ cmd: String, _ args: A) async throws -> Data {
        startReader()
        if let failure { throw failure }
        let id = takeId()
        let line = try Self.encode(id: id, cmd: cmd, args: args)
        inFlight.insert(id)
        do {
            try await transport.write(line)
        } catch {
            inFlight.remove(id)
            early.removeValue(forKey: id)
            throw error
        }
        // The reply (or the transport's end) may already have come in during the write.
        if let reply = early.removeValue(forKey: id) {
            return try reply.get()
        }
        if let failure {
            inFlight.remove(id)
            throw failure
        }
        return try await withCheckedThrowingContinuation { continuation in
            waiting[id] = continuation
        }
    }

    private func takeId() -> Int {
        defer { nextId += 1 }
        return nextId
    }

    private static func encode<A: Encodable>(id: Int, cmd: String, args: A) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.withoutEscapingSlashes, .sortedKeys]
        return try encoder.encode(Request(id: id, cmd: cmd, args: args))
    }

    // MARK: - Reading

    private func startReader() {
        guard reader == nil else { return }
        let lines = transport.lines
        reader = Task { [weak self] in
            do {
                for try await line in lines {
                    guard let self else { return }
                    await self.route(line)
                }
                await self?.end(ClientError.helperExited(stderrTail: []))
            } catch {
                await self?.end(error)
            }
        }
    }

    private func route(_ line: Data) {
        let header: Header
        do {
            header = try JSONDecoder().decode(Header.self, from: line)
        } catch {
            Self.log.warning("skipping unreadable line: \(String(decoding: line, as: UTF8.self), privacy: .public)")
            return
        }
        guard let id = header.id else {
            Self.log.warning("skipping reply without id: \(String(decoding: line, as: UTF8.self), privacy: .public)")
            return
        }
        if let sort = sorts[id] {
            routeSort(id: id, sort, header, line)
        } else if inFlight.contains(id), header.event == nil {
            inFlight.remove(id)
            let reply: Result<Data, Error> =
                if let error = header.error {
                    .failure(ClientError.helper(kind: error.kind, message: error.message))
                } else {
                    .success(line)
                }
            if let continuation = waiting.removeValue(forKey: id) {
                continuation.resume(with: reply)
            } else {
                early[id] = reply
            }
        } else {
            Self.log.warning("skipping reply for unknown id \(id): \(String(decoding: line, as: UTF8.self), privacy: .public)")
        }
    }

    private func routeSort(
        id: Int, _ sort: AsyncThrowingStream<SortUpdate, Error>.Continuation, _ header: Header,
        _ line: Data
    ) {
        if header.event != nil {
            do {
                sort.yield(.event(try JSONDecoder().decode(SortEvent.self, from: line)))
            } catch {
                Self.log.warning("skipping unreadable event: \(String(decoding: line, as: UTF8.self), privacy: .public)")
            }
            return
        }
        sorts.removeValue(forKey: id)
        if let error = header.error {
            sort.finish(throwing: ClientError.helper(kind: error.kind, message: error.message))
            return
        }
        do {
            sort.yield(.finished(try JSONDecoder().decode(ResultReply<Report>.self, from: line).result))
            sort.finish()
        } catch {
            sort.finish(throwing: error)
        }
    }

    /// The transport ended: fail everything pending, and every later request.
    private func end(_ error: Error) {
        failure = error
        for (_, continuation) in waiting { continuation.resume(throwing: error) }
        waiting = [:]
        for id in inFlight where early[id] == nil { early[id] = .failure(error) }
        inFlight = []
        for (_, sort) in sorts { sort.finish(throwing: error) }
        sorts = [:]
    }
}

// MARK: - Wire envelopes

private struct NoArgs: Encodable, Sendable {}

private struct Request<A: Encodable>: Encodable {
    let id: Int
    let cmd: String
    let args: A
}

private struct SetOrderArgs: Encodable, Sendable {
    let instrument: Instrument
    let order: [String]?

    enum CodingKeys: String, CodingKey { case instrument, order }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(instrument, forKey: .instrument)
        try c.encode(order, forKey: .order)  // nil is sent as null: the default order
    }
}

/// What every reply line carries, read before routing.
private struct Header: Decodable {
    let id: Int?
    let event: String?
    let error: ErrorBody?

    struct ErrorBody: Decodable {
        let kind: String
        let message: String
    }
}

private struct ResultReply<R: Decodable>: Decodable {
    let result: R
}

private struct Hello: Decodable {
    let version: Int
    enum CodingKeys: String, CodingKey { case version = "protocol" }
}

private struct Described: Decodable {
    let tuning: TuningInfo
}
