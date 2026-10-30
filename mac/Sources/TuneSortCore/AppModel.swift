import Foundation
import Observation

public enum SidebarItem: Hashable, Sendable {
    case needsReview, allSongs, playlist(String), tuningPlaylist(String)
}

public enum RowStatus: Equatable, Sendable {
    case cached(TuningInfo, source: String, confirmed: Bool)
    case review([MatchInfo])
    case unknown
    case lookingUp
    case failed(sources: [String])
    case addError(String)
}

public struct SongRow: Identifiable, Equatable, Sendable {
    public var artist: String
    public var title: String
    public var persistentID: String?
    public var status: RowStatus

    /// `persistentID` when present, else `"\(artist)\u{1F}\(title)"`.
    public var id: String { persistentID ?? "\(artist)\u{1F}\(title)" }

    public init(artist: String, title: String, persistentID: String? = nil, status: RowStatus) {
        self.artist = artist
        self.title = title
        self.persistentID = persistentID
        self.status = status
    }
}

public enum RunState: Equatable, Sendable {
    case idle
    case running(done: Int, total: Int, dryRun: Bool)
}

public enum BannerKind: Equatable, Sendable {
    case helperExited, music, config, other
}

public struct Banner: Equatable, Sendable {
    public var message: String
    public var kind: BannerKind
    public var stderrTail: [String]

    public init(message: String, kind: BannerKind, stderrTail: [String] = []) {
        self.message = message
        self.kind = kind
        self.stderrTail = stderrTail
    }
}

@MainActor @Observable
public final class AppModel {
    @ObservationIgnored let api: HelperAPI

    public var instrument: Instrument = .bass
    public var reviewCount: Int = 0
    public var playlists: [String] = []
    public var tuningPlaylists: [String] = []
    public var selection: SidebarItem?
    public var selectedRowID: SongRow.ID?
    public var searchText: String = ""
    public var sourcesOverride: [String]?
    public var runState: RunState = .idle
    public var lastSummary: String?
    public var banner: Banner?

    private var allRows: [SongRow] = []

    /// The selection's rows; for `.allSongs`, filtered by `searchText` (case-insensitive
    /// substring of artist or title).
    public var rows: [SongRow] {
        get {
            guard selection == .allSongs else { return allRows }
            let q = searchText.trimmingCharacters(in: .whitespaces)
            if q.isEmpty { return allRows }
            return allRows.filter {
                $0.artist.localizedCaseInsensitiveContains(q)
                    || $0.title.localizedCaseInsensitiveContains(q)
            }
        }
    }

    /// Figures from the last finished preview, valid only while nothing relevant changed.
    private struct PreviewFigures {
        var playlist: String
        var instrument: Instrument
        var sources: [String]?
        var songs: Int
        var playlists: Int
        var created: Int
    }
    private var lastPreview: PreviewFigures?
    private var currentRun: SortRun?
    /// `stop()` was called before `api.sort` returned a run.
    private var stopRequested = false
    /// A playlist's rows are being fetched; runs wait for them.
    private var loadingRows = false

    private var isRunning: Bool { runState != .idle }

    public init(api: HelperAPI) {
        self.api = api
    }

    // MARK: loading

    public func load() async {
        guard !isRunning else { return }
        banner = nil
        let i = instrument
        do {
            let all = try await api.playlists()
            let review = try await api.reviewList(i)
            guard i == instrument else { return }
            tuningPlaylists = all.filter { isTuningPlaylist($0, for: i) }
            playlists = all.filter { !isTuningPlaylist($0, for: i) }
            reviewCount = review.count
        } catch {
            show(error)
        }
    }

    public func select(_ item: SidebarItem) async {
        guard !isRunning else { return }
        banner = nil
        selection = item
        selectedRowID = nil
        allRows = []
        loadingRows = true
        let i = instrument
        do {
            let loaded = try await fetchRows(item, i)
            guard selection == item, i == instrument else { return }
            allRows = loaded
            loadingRows = false
        } catch {
            guard selection == item else { return }
            allRows = []
            loadingRows = false
            show(error)
        }
    }

    public func setInstrument(_ i: Instrument) async {
        guard !isRunning else { return }
        loadingRows = false
        instrument = i
        selection = nil
        selectedRowID = nil
        allRows = []
        playlists = []
        tuningPlaylists = []
        reviewCount = 0
        lastSummary = nil
        lastPreview = nil
        await load()
    }

    public func refreshRow(artist: String, title: String) async {
        let i = instrument
        guard let item = selection else { return }
        do {
            if let review = try? await api.reviewList(i), i == instrument { reviewCount = review.count }
            guard !isRunning else { return }
            let loaded = try await fetchRows(item, i)
            guard !isRunning, !loadingRows, selection == item, i == instrument else { return }
            if case .playlist = item {
                if let fresh = loaded.first(where: { $0.artist == artist && $0.title == title }),
                   let idx = allRows.firstIndex(where: { $0.artist == artist && $0.title == title }) {
                    allRows[idx] = fresh
                }
            } else {
                allRows = loaded
            }
        } catch {
            show(error)
        }
    }

    private func fetchRows(_ item: SidebarItem, _ i: Instrument) async throws -> [SongRow] {
        switch item {
        case .playlist(let name), .tuningPlaylist(let name):
            return try await api.tracks(i, playlist: name).map { t in
                let status: RowStatus
                switch t.state {
                case let .cached(tuning, source, confirmed):
                    status = .cached(tuning, source: source, confirmed: confirmed)
                case let .review(candidates): status = .review(candidates)
                case .unknown: status = .unknown
                }
                return SongRow(artist: t.track.artist, title: t.track.title,
                               persistentID: t.track.persistentId, status: status)
            }
        case .needsReview:
            return try await api.reviewList(i).map {
                SongRow(artist: $0.artist, title: $0.title, status: .review($0.candidates))
            }
        case .allSongs:
            return try await api.entries(i).map {
                SongRow(artist: $0.artist, title: $0.title,
                        status: .cached($0.tuning, source: $0.source, confirmed: $0.confirmed))
            }
        }
    }

    // MARK: runs

    public func preview() async { await run(dryRun: true) }
    public func sort() async { await run(dryRun: false) }

    public func sortConfirmation() -> String {
        guard case .playlist(let name)? = selection else { return "Sort '' into tuning playlists?" }
        if let p = lastPreview, p.playlist == name, p.instrument == instrument,
           p.sources == sourcesOverride {
            var s = "Add \(p.songs) \(p.songs == 1 ? "song" : "songs") to \(p.playlists) "
                + (p.playlists == 1 ? "playlist" : "playlists")
            if p.created > 0 { s += ", creating \(p.created)" }
            return s + "?"
        }
        return "Sort '\(name)' into tuning playlists?"
    }

    public func stop() async {
        if let run = currentRun {
            do { try await api.cancel(run) } catch { show(error) }
        } else if isRunning {
            stopRequested = true
        }
    }

    private func run(dryRun: Bool) async {
        guard case .playlist(let name)? = selection, runState == .idle, !loadingRows else { return }
        banner = nil
        lastSummary = nil
        stopRequested = false
        let i = instrument
        let sources = sourcesOverride
        if !dryRun { lastPreview = nil }
        runState = .running(done: 0, total: allRows.count, dryRun: dryRun)
        var priors: [String: RowStatus] = [:]
        func key(_ a: String, _ t: String) -> String { "\(a)\u{1F}\(t)" }
        func restore() {
            for idx in allRows.indices where allRows[idx].status == .lookingUp {
                if let old = priors[key(allRows[idx].artist, allRows[idx].title)] {
                    allRows[idx].status = old
                }
            }
        }
        defer { currentRun = nil; stopRequested = false }
        do {
            let run = try await api.sort(
                SortRequest(instrument: i, playlist: name, dryRun: dryRun, order: sources))
            currentRun = run
            if stopRequested { try? await api.cancel(run) }
            var done = 0
            var total = allRows.count
            for try await update in run.updates {
                switch update {
                case .event(.start(let s)):
                    total = s.total
                    if let idx = index(s.artist, s.title) {
                        if allRows[idx].status != .lookingUp {
                            priors[key(s.artist, s.title)] = allRows[idx].status
                        }
                        allRows[idx].status = .lookingUp
                    }
                    runState = .running(done: done, total: total, dryRun: dryRun)
                case .event(.done(let d)):
                    done += 1
                    if let idx = index(d.artist, d.title) {
                        let prior = priors[key(d.artist, d.title)] ?? allRows[idx].status
                        allRows[idx].status = Self.status(for: d, prior: prior)
                        priors[key(d.artist, d.title)] = nil
                    }
                    runState = .running(done: done, total: total, dryRun: dryRun)
                case .finished(let report):
                    restore()
                    lastSummary = Self.summary(report, dryRun: dryRun)
                    if dryRun, !report.cancelled {
                        lastPreview = PreviewFigures(
                            playlist: name, instrument: i, sources: sources,
                            songs: report.added.values.reduce(0) { $0 + $1.count },
                            playlists: report.added.count, created: report.createdPlaylists.count)
                    }
                }
            }
            restore()
        } catch {
            restore()
            show(error)
        }
        runState = .idle
    }

    private func index(_ artist: String, _ title: String) -> Int? {
        allRows.firstIndex { $0.artist == artist && $0.title == title }
    }

    private static func status(for d: SortDone, prior: RowStatus) -> RowStatus {
        switch d.status {
        case .added, .alreadyPresent:
            guard let tuning = d.tuning else { return prior }
            var confirmed = false
            if case .cached(_, _, let c) = prior { confirmed = c }
            return .cached(tuning, source: d.source ?? "", confirmed: confirmed)
        case .review: return .review([])
        case .lookupFailed: return .failed(sources: d.failed ?? [])
        case .addError: return .addError(d.error ?? "")
        }
    }

    private static func summary(_ r: Report, dryRun: Bool) -> String {
        let songs = r.added.values.reduce(0) { $0 + $1.count }
        let p = r.added.count
        let pl = "\(p) playlist" + (p == 1 ? "" : "s")
        var parts = [dryRun ? "Preview: \(songs) would be added to \(pl)" : "Added \(songs) to \(pl)"]
        if !r.review.isEmpty {
            parts.append(r.review.count == 1 ? "1 needs review" : "\(r.review.count) need review")
        }
        let failed = r.lookupFailed.count + r.addErrors.count
        if failed > 0 { parts.append("\(failed) failed") }
        if r.cancelled { parts.append("stopped") }
        return parts.joined(separator: " · ")
    }

    func show(_ error: Error) {
        if error is CancellationError { return }
        if let e = error as? ClientError {
            switch e {
            case .helperExited(let tail):
                banner = Banner(message: "The TuneSort helper stopped unexpectedly.",
                                kind: .helperExited, stderrTail: tail)
            case .helper(let kind, let message):
                switch kind {
                case "music": banner = Banner(message: message, kind: .music)
                case "config": banner = Banner(message: message, kind: .config)
                default: banner = Banner(message: message, kind: .other)
                }
            case .helperNotFound(let path):
                banner = Banner(message: "Helper not found at \(path).", kind: .other)
            case .protocolMismatch(let helper, let expected):
                banner = Banner(message: "Helper speaks protocol \(helper); expected \(expected).",
                                kind: .other)
            }
        } else {
            banner = Banner(message: String(describing: error), kind: .other)
        }
    }
}
