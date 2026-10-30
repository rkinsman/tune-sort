import Foundation

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
public actor HelperClient: HelperAPI {
    public static let protocolVersion = 1

    public init(transport: Transport) {
        fatalError("unimplemented")
    }

    /// Sends `hello`; throws `ClientError.protocolMismatch` unless the helper speaks version 1.
    public func start() async throws {
        fatalError("unimplemented")
    }

    public func playlists() async throws -> [String] { fatalError("unimplemented") }
    public func tracks(_ i: Instrument, playlist: String) async throws -> [TrackState] {
        fatalError("unimplemented")
    }
    public func config() async throws -> ConfigInfo { fatalError("unimplemented") }
    public func setOrder(_ i: Instrument, _ order: [String]?) async throws -> [String] {
        fatalError("unimplemented")
    }
    public func reviewList(_ i: Instrument) async throws -> [ReviewItem] {
        fatalError("unimplemented")
    }
    public func describe(_ i: Instrument, _ tuning: String) async throws -> TuningInfo {
        fatalError("unimplemented")
    }
    public func set(_ i: Instrument, artist: String, title: String, tuning: String) async throws
        -> CachedSong
    {
        fatalError("unimplemented")
    }
    public func entries(_ i: Instrument) async throws -> [CachedSong] {
        fatalError("unimplemented")
    }
    public func delete(_ i: Instrument, artist: String, title: String) async throws {
        fatalError("unimplemented")
    }
    public func sort(_ request: SortRequest) async throws -> SortRun { fatalError("unimplemented") }
    public func cancel(_ run: SortRun) async throws { fatalError("unimplemented") }
}
