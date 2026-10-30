import Foundation
@testable import TuneSortCore

struct FakeError: Error, Equatable { let tag: String }

/// A bounded, test-controlled gate. Calls that wait on it return once it is opened
/// (or after `timeout` seconds, so a broken test never hangs the suite).
final class Gate: @unchecked Sendable {
    private let lock = NSLock()
    private var opened = false
    func open() { lock.withLock { opened = true } }
    var isOpen: Bool { lock.withLock { opened } }
    func wait(timeout: Double = 10) async {
        let deadline = Date().addingTimeInterval(timeout)
        while !isOpen && Date() < deadline {
            try? await Task.sleep(nanoseconds: 2_000_000)
        }
    }
}

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
        /// When set, the call blocks (after being logged) until the gate opens.
        var playlistsGate: Gate?
        var tracksGate: [String: Gate] = [:]
        var entriesGate: Gate?
        var reviewListGate: Gate?
        var sortGate: Gate?
        var calls: [String] = []
        var sortRequests: [SortRequest] = []
        var cancelledRunIDs: [Int] = []
        var continuations: [AsyncThrowingStream<SortUpdate, Error>.Continuation] = []
        /// Scripted describe replies by tuning text (default: success echoing the text).
        var describeResults: [String: Result<TuningInfo, Error>] = [:]
        /// describe blocks (after being logged) until the gate for its text opens.
        var describeGates: [String: Gate] = [:]
        var setError: Error?
        var deleteError: Error?
        /// When set, setOrder returns/throws this instead of echoing its argument.
        var setOrderReply: Result<[String], Error>?
        var setOrderArgs: [(Instrument, [String]?)] = []
        /// setOrder blocks (after being logged) until this gate opens.
        var setOrderGate: Gate?
    }

    private let lock = NSLock()
    private var state = State()

    /// Mutate scripted results.
    func configure(_ f: (inout State) -> Void) { lock.withLock { f(&state) } }
    private func read<T>(_ f: (State) -> T) -> T { lock.withLock { f(state) } }
    private func log(_ s: String) { lock.withLock { state.calls.append(s) } }

    var calls: [String] { read { $0.calls } }
    var setOrderArgs: [(Instrument, [String]?)] { read { $0.setOrderArgs } }
    var sortRequests: [SortRequest] { read { $0.sortRequests } }
    var cancelledRunIDs: [Int] { read { $0.cancelledRunIDs } }

    static let firstRunID = 7

    // MARK: HelperAPI

    func playlists() async throws -> [String] {
        log("playlists")
        await read({ $0.playlistsGate })?.wait()
        return try read { $0.playlists }.get()
    }

    func tracks(_ i: Instrument, playlist: String) async throws -> [TrackState] {
        log("tracks:\(i.rawValue):\(playlist)")
        await read({ $0.tracksGate[playlist] })?.wait()
        return try (read { $0.tracks[playlist] } ?? .success([])).get()
    }

    func config() async throws -> ConfigInfo {
        log("config")
        return try read { $0.config }.get()
    }

    func setOrder(_ i: Instrument, _ order: [String]?) async throws -> [String] {
        log("setOrder:\(i.rawValue)")
        lock.withLock { state.setOrderArgs.append((i, order)) }
        await read({ $0.setOrderGate })?.wait()
        if let reply = read({ $0.setOrderReply }) { return try reply.get() }
        return order ?? []
    }

    func reviewList(_ i: Instrument) async throws -> [ReviewItem] {
        log("reviewList:\(i.rawValue)")
        await read({ $0.reviewListGate })?.wait()
        return try (read { $0.reviewList[i] } ?? .success([])).get()
    }

    func describe(_ i: Instrument, _ tuning: String) async throws -> TuningInfo {
        log("describe:\(i.rawValue):\(tuning)")
        await read({ $0.describeGates[tuning] })?.wait()
        if let r = read({ $0.describeResults[tuning] }) { return try r.get() }
        return TuningInfo(name: tuning, playlistName: "\(i.rawValue) – \(tuning)", notes: "")
    }

    func set(_ i: Instrument, artist: String, title: String, tuning: String) async throws -> CachedSong {
        log("set:\(i.rawValue):\(artist):\(title):\(tuning)")
        if let e = read({ $0.setError }) { throw e }
        return CachedSong(artist: artist, title: title,
                          tuning: TuningInfo(name: tuning, playlistName: "", notes: ""),
                          source: "manual", confirmed: true)
    }

    func entries(_ i: Instrument) async throws -> [CachedSong] {
        log("entries:\(i.rawValue)")
        await read({ $0.entriesGate })?.wait()
        return try (read { $0.entries[i] } ?? .success([])).get()
    }

    func delete(_ i: Instrument, artist: String, title: String) async throws {
        log("delete:\(i.rawValue):\(artist):\(title)")
        if let e = read({ $0.deleteError }) { throw e }
    }

    func sort(_ request: SortRequest) async throws -> SortRun {
        log("sort")
        lock.withLock { state.sortRequests.append(request) }
        await read({ $0.sortGate })?.wait()
        if let e = read({ $0.sortError }) { throw e }
        let (stream, cont) = AsyncThrowingStream<SortUpdate, Error>.makeStream()
        let id = lock.withLock { () -> Int in
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

    /// Waits (bounded) until `sort` has returned a run at least `count` times.
    func waitForSort(_ count: Int = 1, timeout: Double = 5) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while read({ $0.continuations.count }) < count {
            if Date() > deadline { throw TestTimeout() }
            try await Task.sleep(nanoseconds: 2_000_000)
        }
    }

    /// Waits (bounded) until the call log holds `count` entries equal to `call`.
    func waitForCall(_ call: String, count: Int = 1, timeout: Double = 5) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while read({ $0.calls.filter { $0 == call }.count }) < count {
            if Date() > deadline { throw TestTimeout() }
            try await Task.sleep(nanoseconds: 2_000_000)
        }
    }
}
