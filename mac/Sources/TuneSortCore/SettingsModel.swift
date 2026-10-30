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

    public func load() async {
        do {
            let info = try await api.config()
            var result: [Instrument: [SourceToggle]] = [:]
            for i in Instrument.allCases {
                let saved = info.order[i] ?? []
                let rest = (info.sources[i] ?? []).filter { !saved.contains($0) }
                result[i] = saved.map { SourceToggle(name: $0, enabled: true) }
                    + rest.map { SourceToggle(name: $0, enabled: false) }
            }
            orders = result
            error = nil
        } catch {
            fail(error)
        }
    }

    public func move(_ i: Instrument, from: IndexSet, to: Int) async {
        guard var list = orders[i] else { return }
        let moving = from.filter { list.indices.contains($0) }.sorted().map { list[$0] }
        let dest = to - from.filter { $0 < to }.count
        for idx in from.sorted(by: >) where list.indices.contains(idx) { list.remove(at: idx) }
        list.insert(contentsOf: moving, at: max(0, min(dest, list.count)))
        await push(i, list)
    }

    public func toggle(_ i: Instrument, _ name: String) async {
        guard var list = orders[i], let idx = list.firstIndex(where: { $0.name == name }) else { return }
        if list[idx].enabled && list.filter(\.enabled).count <= 1 { return }
        list[idx].enabled.toggle()
        await push(i, list)
    }

    public func reset(_ i: Instrument) async {
        await apply(i, nil)
    }

    private func push(_ i: Instrument, _ list: [SourceToggle]) async {
        await apply(i, list.filter(\.enabled).map(\.name), keeping: list)
    }

    /// Sends the order; on success rebuilds `orders[i]` from the returned order. `keeping` is
    /// the current list whose disabled entries stay where they are.
    private func apply(_ i: Instrument, _ names: [String]?, keeping: [SourceToggle]? = nil) async {
        do {
            let returned = try await api.setOrder(i, names)
            var list: [SourceToggle]
            if let keeping {
                // Enabled entries follow the returned order; disabled entries keep their slots.
                var queue = returned
                list = keeping.map { t in
                    t.enabled ? SourceToggle(name: queue.isEmpty ? t.name : queue.removeFirst(), enabled: true) : t
                }
            } else {
                let all = (orders[i] ?? []).map(\.name)
                let rest = all.filter { !returned.contains($0) }
                list = returned.map { SourceToggle(name: $0, enabled: true) }
                    + rest.map { SourceToggle(name: $0, enabled: false) }
            }
            orders[i] = list
            error = nil
        } catch {
            fail(error)
        }
    }

    private func fail(_ e: Error) {
        if e is CancellationError { return }
        if case let ClientError.helper(kind, message) = e, kind == "config" {
            error = message
        } else {
            error = String(describing: e)
        }
    }
}
