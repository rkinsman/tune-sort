import Foundation
import Observation

/// One source in an instrument's lookup order.
public struct SourceToggle: Equatable, Sendable {
    public var name: String
    public var enabled: Bool

    public init(name: String, enabled: Bool) {
        self.name = name
        self.enabled = enabled
    }
}

/// State for the Settings window: per-instrument source order and the repo path.
@MainActor @Observable
public final class SettingsModel {
    @ObservationIgnored let api: HelperAPI
    @ObservationIgnored let defaults: UserDefaults

    public var orders: [Instrument: [SourceToggle]] = [:]
    public var error: String?
    public var repoPath: String {
        didSet { defaults.set(repoPath, forKey: "repoPath") }
    }

    public init(api: HelperAPI, defaults: UserDefaults) {
        self.api = api
        self.defaults = defaults
        self.repoPath = defaults.string(forKey: "repoPath")
            ?? NSString(string: "~/code/tune-sort").expandingTildeInPath
    }

    public func load() async { fatalError("unimplemented") }
    public func move(_ i: Instrument, from: IndexSet, to: Int) async { fatalError("unimplemented") }
    public func toggle(_ i: Instrument, _ name: String) async { fatalError("unimplemented") }
    public func reset(_ i: Instrument) async { fatalError("unimplemented") }
}
