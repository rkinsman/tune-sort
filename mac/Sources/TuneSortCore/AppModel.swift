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
    public var rows: [SongRow] = []
    public var selectedRowID: SongRow.ID?
    public var searchText: String = ""
    public var sourcesOverride: [String]?
    public var runState: RunState = .idle
    public var lastSummary: String?
    public var banner: Banner?

    public init(api: HelperAPI) {
        self.api = api
    }

    public func load() async { fatalError("unimplemented") }
    public func select(_ item: SidebarItem) async { fatalError("unimplemented") }
    public func setInstrument(_ i: Instrument) async { fatalError("unimplemented") }
    public func preview() async { fatalError("unimplemented") }
    public func sortConfirmation() -> String { fatalError("unimplemented") }
    public func sort() async { fatalError("unimplemented") }
    public func stop() async { fatalError("unimplemented") }
    public func refreshRow(artist: String, title: String) async { fatalError("unimplemented") }
}
