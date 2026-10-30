import Foundation
@testable import TuneSortCore

struct FakeError: Error, Equatable { let tag: String }

/// Scripted, call-logging HelperAPI. Sort streams are driven by the test.
final class FakeHelperAPI: HelperAPI, @unchecked Sendable {
    struct State {
        var playlists: Result<[String], Error> = .success([])
        var tracks: [String: Result<[TrackState], Error>] = [:]
        var config: Result<ConfigInfo, Error> = .success(
            ConfigInfo(path: "/c", exists: false, order: [.bass: [], .guitar: []], sources: [.bass: [], .guitar: []]))
        var reviewList: [Instrument: Result<[ReviewItem], Error>] = [:]
        var entries: [Instrument: Result<[CachedSong], Error>] = [:]
        var sortError: Error?
        var calls: [String] = []
        var sortRequests: [SortRequest] = []
        var cancelledRunIDs: [Int] = []
        var continuations: [AsyncThrowingStream<SortUpdate, Error>.Continuation] = []
    }

    private let lock = NSLock()
    private var state = State()

    /// Mutate scripted results.
    func configure(_ f: (inout State) -> Void) { lock.withLock { f(&state) } }
    private func read<T>(_ f: (State) -> T) -> T { lock.withLock { f(state) } }
    private func log(_ s: String) { lock.withLock { state.calls.append(s) } }

    var calls: [String] { read { $0.calls } }
    var sortRequests: [SortRequest] { read { $0.sortRequests } }
    var cancelledRunIDs: [Int] { read { $0.cancelledRunIDs } }

    static let firstRunID = 7

    // MARK: HelperAPI

    func playlists() async throws -> [String] {
        log("playlists")
        return try read { $0.playlists }.get()
    }

    func tracks(_ i: Instrument, playlist: String) async throws -> [TrackState] {
        log("tracks:\(i.rawValue):\(playlist)")
        return try (read { $0.tracks[playlist] } ?? .success([])).get()
    }

    func config() async throws -> ConfigInfo {
        log("config")
        return try read { $0.config }.get()
    }

    func setOrder(_ i: Instrument, _ order: [String]?) async throws -> [String] {
        log("setOrder:\(i.rawValue)")
        return order ?? []
    }

    func reviewList(_ i: Instrument) async throws -> [ReviewItem] {
        log("reviewList:\(i.rawValue)")
        return try (read { $0.reviewList[i] } ?? .success([])).get()
    }

    func describe(_ i: Instrument, _ tuning: String) async throws -> TuningInfo {
        log("describe:\(i.rawValue):\(tuning)")
        return TuningInfo(name: tuning, playlistName: "\(i.rawValue) – \(tuning)", notes: "")
    }

    func set(_ i: Instrument, artist: String, title: String, tuning: String) async throws -> CachedSong {
        log("set:\(i.rawValue):\(artist):\(title):\(tuning)")
        return CachedSong(artist: artist, title: title,
                          tuning: TuningInfo(name: tuning, playlistName: "", notes: ""),
                          source: "manual", confirmed: true)
    }

    func entries(_ i: Instrument) async throws -> [CachedSong] {
        log("entries:\(i.rawValue)")
        return try (read { $0.entries[i] } ?? .success([])).get()
    }

    func delete(_ i: Instrument, artist: String, title: String) async throws {
        log("delete:\(i.rawValue):\(artist):\(title)")
    }

    func sort(_ request: SortRequest) async throws -> SortRun {
        log("sort")
        if let e = read({ $0.sortError }) {
            lock.withLock { state.sortRequests.append(request) }
            throw e
        }
        let (stream, cont) = AsyncThrowingStream<SortUpdate, Error>.makeStream()
        let id = lock.withLock { () -> Int in
            state.sortRequests.append(request)
            state.continuations.append(cont)
            return Self.firstRunID + state.continuations.count - 1
        }
        return SortRun(id: id, updates: stream)
    }

    func cancel(_ run: SortRun) async throws {
        log("cancel")
        lock.withLock { state.cancelledRunIDs.append(run.id) }
    }

    // MARK: stream driving

    private var latest: AsyncThrowingStream<SortUpdate, Error>.Continuation? {
        read { $0.continuations.last }
    }

    func yield(_ update: SortUpdate) { latest?.yield(update) }
    func finishStream() { latest?.finish() }
    func finishStream(throwing error: Error) { latest?.finish(throwing: error) }

    /// Waits (bounded) until `sort` has been called at least `count` times.
    func waitForSort(_ count: Int = 1, timeout: Double = 5) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while read({ $0.continuations.count }) < count {
            if Date() > deadline { throw TestTimeout() }
            try await Task.sleep(nanoseconds: 2_000_000)
        }
    }
}
