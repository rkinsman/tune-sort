import Foundation

// The helper protocol's data shapes (spec "Protocol (version 1)"; Python: tune_sort/wire.py).
// JSON keys are snake_case; Swift names are camelCase.

/// Instruments are JSON object keys in `config` (`{"bass": [...], "guitar": [...]}`).
extension Instrument: CodingKeyRepresentable {}

/// A Music track: `{"artist", "title", "persistent_id"}`.
public struct Track: Codable, Sendable, Equatable, Hashable {
    public let artist: String
    public let title: String
    public let persistentId: String

    public init(artist: String, title: String, persistentId: String) {
        self.artist = artist
        self.title = title
        self.persistentId = persistentId
    }

    enum CodingKeys: String, CodingKey {
        case artist, title
        case persistentId = "persistent_id"
    }
}

/// A tuning: `{"name", "playlist_name", "notes"}`; `notes` lists the open strings, lowest first.
public struct TuningInfo: Codable, Sendable, Equatable, Hashable {
    public let name: String
    public let playlistName: String
    public let notes: String

    public init(name: String, playlistName: String, notes: String) {
        self.name = name
        self.playlistName = playlistName
        self.notes = notes
    }

    enum CodingKeys: String, CodingKey {
        case name, notes
        case playlistName = "playlist_name"
    }
}

/// A source's candidate: `{"tuning", "source", "url", "matched_artist", "matched_title", "exact"}`.
public struct MatchInfo: Codable, Sendable, Equatable {
    public let tuning: TuningInfo
    public let source: String
    public let url: String
    public let matchedArtist: String
    public let matchedTitle: String
    public let exact: Bool

    public init(
        tuning: TuningInfo, source: String, url: String,
        matchedArtist: String, matchedTitle: String, exact: Bool
    ) {
        self.tuning = tuning
        self.source = source
        self.url = url
        self.matchedArtist = matchedArtist
        self.matchedTitle = matchedTitle
        self.exact = exact
    }

    enum CodingKeys: String, CodingKey {
        case tuning, source, url, exact
        case matchedArtist = "matched_artist"
        case matchedTitle = "matched_title"
    }
}

/// A cached entry: `{"artist", "title", "tuning", "source", "confirmed"}`.
public struct CachedSong: Codable, Sendable, Equatable {
    public let artist: String
    public let title: String
    public let tuning: TuningInfo
    public let source: String
    public let confirmed: Bool

    public init(artist: String, title: String, tuning: TuningInfo, source: String, confirmed: Bool) {
        self.artist = artist
        self.title = title
        self.tuning = tuning
        self.source = source
        self.confirmed = confirmed
    }
}

/// A `tracks` item's cache state.
public enum CacheState: Sendable, Equatable {
    /// `"state": "cached"`, with `tuning`, `source` and `confirmed`.
    case cached(tuning: TuningInfo, source: String, confirmed: Bool)
    /// `"state": "review"`, with `candidates`.
    case review(candidates: [MatchInfo])
    /// `"state": "unknown"`.
    case unknown
}

/// A `tracks` item: the track's keys plus `"state"` and that state's keys, all in one object.
public struct TrackState: Codable, Sendable, Equatable {
    public let track: Track
    public let state: CacheState

    public init(track: Track, state: CacheState) {
        self.track = track
        self.state = state
    }

    enum CodingKeys: String, CodingKey {
        case state, tuning, source, confirmed, candidates
    }

    public init(from decoder: Decoder) throws {
        track = try Track(from: decoder)
        let c = try decoder.container(keyedBy: CodingKeys.self)
        switch try c.decode(String.self, forKey: .state) {
        case "cached":
            state = .cached(
                tuning: try c.decode(TuningInfo.self, forKey: .tuning),
                source: try c.decode(String.self, forKey: .source),
                confirmed: try c.decode(Bool.self, forKey: .confirmed))
        case "review":
            state = .review(candidates: try c.decode([MatchInfo].self, forKey: .candidates))
        case "unknown":
            state = .unknown
        case let other:
            throw DecodingError.dataCorruptedError(
                forKey: .state, in: c, debugDescription: "unknown track state: \(other)")
        }
    }

    public func encode(to encoder: Encoder) throws {
        try track.encode(to: encoder)
        var c = encoder.container(keyedBy: CodingKeys.self)
        switch state {
        case let .cached(tuning, source, confirmed):
            try c.encode("cached", forKey: .state)
            try c.encode(tuning, forKey: .tuning)
            try c.encode(source, forKey: .source)
            try c.encode(confirmed, forKey: .confirmed)
        case let .review(candidates):
            try c.encode("review", forKey: .state)
            try c.encode(candidates, forKey: .candidates)
        case .unknown:
            try c.encode("unknown", forKey: .state)
        }
    }
}

/// A `review_list` item: `{"artist", "title", "candidates": [match]}`.
public struct ReviewItem: Codable, Sendable, Equatable {
    public let artist: String
    public let title: String
    public let candidates: [MatchInfo]

    public init(artist: String, title: String, candidates: [MatchInfo]) {
        self.artist = artist
        self.title = title
        self.candidates = candidates
    }
}

/// One `add_errors` item in a report: `{"track", "playlist", "error"}`.
public struct AddError: Codable, Sendable, Equatable {
    public let track: Track
    public let playlist: String
    public let error: String

    public init(track: Track, playlist: String, error: String) {
        self.track = track
        self.playlist = playlist
        self.error = error
    }
}

/// A sort's result. In a dry run `added` means "would add". Playlist name -> tracks.
public struct Report: Codable, Sendable, Equatable {
    public let cancelled: Bool
    public let createdPlaylists: [String]
    public let added: [String: [Track]]
    public let alreadyPresent: [String: [Track]]
    public let review: [Track]
    public let lookupFailed: [Track]
    public let addErrors: [AddError]

    public init(
        cancelled: Bool, createdPlaylists: [String], added: [String: [Track]],
        alreadyPresent: [String: [Track]], review: [Track], lookupFailed: [Track],
        addErrors: [AddError]
    ) {
        self.cancelled = cancelled
        self.createdPlaylists = createdPlaylists
        self.added = added
        self.alreadyPresent = alreadyPresent
        self.review = review
        self.lookupFailed = lookupFailed
        self.addErrors = addErrors
    }

    enum CodingKeys: String, CodingKey {
        case cancelled, added, review
        case createdPlaylists = "created_playlists"
        case alreadyPresent = "already_present"
        case lookupFailed = "lookup_failed"
        case addErrors = "add_errors"
    }
}

/// `start` event data: `{"i", "total", "artist", "title"}`, sent just before a track is resolved.
public struct SortStart: Codable, Sendable, Equatable {
    public let i: Int
    public let total: Int
    public let artist: String
    public let title: String

    public init(i: Int, total: Int, artist: String, title: String) {
        self.i = i
        self.total = total
        self.artist = artist
        self.title = title
    }
}

/// `done` event `status` values.
public enum DoneStatus: String, Codable, Sendable, Equatable {
    case added
    case alreadyPresent = "already_present"
    case review
    case lookupFailed = "lookup_failed"
    case addError = "add_error"
}

/// `done` event data: `{"artist", "title", "status", "tuning"?, "source"?, "playlist"?,
/// "failed"?, "error"?}`, sent after a track is handled. `failed` lists source names.
public struct SortDone: Codable, Sendable, Equatable {
    public let artist: String
    public let title: String
    public let status: DoneStatus
    public let tuning: TuningInfo?
    public let source: String?
    public let playlist: String?
    public let failed: [String]?
    public let error: String?

    public init(
        artist: String, title: String, status: DoneStatus, tuning: TuningInfo? = nil,
        source: String? = nil, playlist: String? = nil, failed: [String]? = nil,
        error: String? = nil
    ) {
        self.artist = artist
        self.title = title
        self.status = status
        self.tuning = tuning
        self.source = source
        self.playlist = playlist
        self.failed = failed
        self.error = error
    }
}

/// A sort progress event. Coded as `{"event": "start" | "done", "data": {...}}`, the shape of
/// an event reply line without its `id` (an `id` key, if present, is ignored).
public enum SortEvent: Codable, Sendable, Equatable {
    case start(SortStart)
    case done(SortDone)

    enum CodingKeys: String, CodingKey {
        case event, data
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        switch try c.decode(String.self, forKey: .event) {
        case "start": self = .start(try c.decode(SortStart.self, forKey: .data))
        case "done": self = .done(try c.decode(SortDone.self, forKey: .data))
        case let other:
            throw DecodingError.dataCorruptedError(
                forKey: .event, in: c, debugDescription: "unknown event: \(other)")
        }
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        switch self {
        case let .start(data):
            try c.encode("start", forKey: .event)
            try c.encode(data, forKey: .data)
        case let .done(data):
            try c.encode("done", forKey: .event)
            try c.encode(data, forKey: .data)
        }
    }
}

/// The `config` result: `{"path", "exists", "order": {instrument: [name]},
/// "sources": {instrument: [name]}}`. `sources` lists every allowed source name.
public struct ConfigInfo: Codable, Sendable, Equatable {
    public let path: String
    public let exists: Bool
    public let order: [Instrument: [String]]
    public let sources: [Instrument: [String]]

    public init(
        path: String, exists: Bool, order: [Instrument: [String]], sources: [Instrument: [String]]
    ) {
        self.path = path
        self.exists = exists
        self.order = order
        self.sources = sources
    }
}

/// The `sort` command's args: `{"instrument", "playlist", "dry_run", "order"?, "source"?,
/// "recheck"}`. `order` and `source` are left out when nil (the saved order; `both`).
/// `source` is `both`, `ug` or `songsterr`.
public struct SortRequest: Codable, Sendable, Equatable {
    public var instrument: Instrument
    public var playlist: String
    public var dryRun: Bool
    public var order: [String]?
    public var source: String?
    public var recheck: Bool

    public init(
        instrument: Instrument, playlist: String, dryRun: Bool, order: [String]? = nil,
        source: String? = nil, recheck: Bool = false
    ) {
        self.instrument = instrument
        self.playlist = playlist
        self.dryRun = dryRun
        self.order = order
        self.source = source
        self.recheck = recheck
    }

    enum CodingKeys: String, CodingKey {
        case instrument, playlist, order, source, recheck
        case dryRun = "dry_run"
    }
}
