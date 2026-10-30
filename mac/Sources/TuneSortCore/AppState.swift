import Foundation
import Observation

/// A transport the app can close and read stderr from. `ProcessTransport` is one; a
/// transport that isn't is never closed by `AppState` and has an empty stderr tail.
public protocol HelperProcess: Transport {
    /// Closes the helper's stdin, which cancels a running sort; the helper then exits.
    func close()
    /// The helper's last stderr lines, oldest first.
    var stderrTail: [String] { get }
}

extension ProcessTransport: HelperProcess {}

/// What the window shows: the helper's state, then the app once it has said hello.
public enum Phase: Equatable {
    case starting
    case ready(Session)
    /// The helper executable wasn't found at `path`.
    case setup(path: String)
    /// `hello` reported another protocol version. Nothing else runs.
    case mismatch(String)
    /// The helper failed to start for another reason.
    case failed(String, stderrTail: [String])
}

/// One running helper and the view models that talk to it.
@MainActor
public final class Session: Equatable {
    public let transport: Transport
    public let client: HelperClient
    public let app: AppModel
    public let panel: SidePanelModel
    public let settings: SettingsModel

    public init(transport: Transport, client: HelperClient, defaults: UserDefaults) {
        self.transport = transport
        self.client = client
        app = AppModel(api: client)
        panel = SidePanelModel(api: client, app: app)
        settings = SettingsModel(api: client, defaults: defaults)
    }

    /// The helper's stderr tail, or `[]` when the transport isn't a `HelperProcess`.
    public var stderrTail: [String] { (transport as? HelperProcess)?.stderrTail ?? [] }

    public nonisolated static func == (a: Session, b: Session) -> Bool { a === b }
}

/// Owns the helper: starts it, restarts it, and closes it on quit.
@MainActor @Observable
public final class AppState {
    /// Makes the transport for `<repo>/.venv/bin/tune-sort` and the helper arguments. Throws
    /// `ClientError.helperNotFound(path:)` when the executable is missing.
    public typealias TransportFactory = (URL, [String]) throws -> Transport

    public static let repoPathKey = "repoPath"

    public private(set) var phase: Phase = .starting
    /// The repo path; stored in `defaults` under `repoPath`, the key `SettingsModel` uses.
    public var repoPath: String {
        didSet { defaults.set(repoPath, forKey: Self.repoPathKey) }
    }

    @ObservationIgnored private let defaults: UserDefaults
    @ObservationIgnored private let helperArguments: [String]
    @ObservationIgnored private let makeTransport: TransportFactory
    @ObservationIgnored private var transport: Transport?
    @ObservationIgnored private var started = false
    /// Bumped by every start and shutdown; a start whose number is stale was superseded.
    @ObservationIgnored private var generation = 0

    public init(
        defaults: UserDefaults, helperArguments: [String] = ["serve"],
        makeTransport: @escaping TransportFactory
    ) {
        self.defaults = defaults
        self.helperArguments = helperArguments
        self.makeTransport = makeTransport
        repoPath = Self.savedRepoPath(defaults)
    }

    /// The helper executable for a repo path: `<repo>/.venv/bin/tune-sort` (`~` expanded).
    public static func helperURL(repoPath: String) -> URL {
        URL(fileURLWithPath: NSString(string: repoPath).expandingTildeInPath)
            .appendingPathComponent(".venv/bin/tune-sort")
    }

    /// A start is in progress; `restart()` does nothing meanwhile.
    public var isStarting: Bool {
        if case .starting = phase { return true }
        return false
    }

    public var session: Session? {
        if case .ready(let s) = phase { return s }
        return nil
    }

    private static func savedRepoPath(_ defaults: UserDefaults) -> String {
        defaults.string(forKey: repoPathKey)
            ?? NSString(string: "~/code/tune-sort").expandingTildeInPath
    }

    /// Starts the helper once; later calls do nothing.
    public func startIfNeeded() async {
        guard !started else { return }
        started = true
        await start()
    }

    /// Closes the current helper and starts a new one, keeping the instrument. Re-reads the
    /// repo path from `defaults`. Does nothing while a start is in progress.
    public func restart() async {
        guard !isStarting else { return }
        started = true
        let instrument = session?.app.instrument
        shutdown()
        repoPath = Self.savedRepoPath(defaults)
        await start(instrument: instrument)
    }

    /// Closes the helper's stdin, which cancels a running sort; the helper then exits.
    public func shutdown() {
        generation += 1
        (transport as? HelperProcess)?.close()
        transport = nil
    }

    private func start(instrument: Instrument? = nil) async {
        generation += 1
        let gen = generation
        phase = .starting
        let helper = Self.helperURL(repoPath: repoPath)
        let t: Transport
        do {
            t = try makeTransport(helper, helperArguments)
        } catch ClientError.helperNotFound(let path) {
            phase = .setup(path: path)
            return
        } catch {
            phase = .failed("Couldn't start the helper at \(helper.path): \(error.localizedDescription)",
                            stderrTail: [])
            return
        }
        transport = t
        let client = HelperClient(transport: t)
        do {
            try await client.start()
        } catch ClientError.protocolMismatch(let helperVersion, let expected) {
            (t as? HelperProcess)?.close()
            // A restart while hello was pending owns `transport` and `phase` now.
            guard gen == generation else { return }
            transport = nil
            phase = .mismatch(
                "Helper speaks protocol \(helperVersion), the app expects \(expected). Pull and rebuild.")
            return
        } catch {
            var tail = (t as? HelperProcess)?.stderrTail ?? []
            if case ClientError.helperExited(let errTail) = error, !errTail.isEmpty { tail = errTail }
            (t as? HelperProcess)?.close()
            guard gen == generation else { return }  // restarted meanwhile
            transport = nil
            phase = .failed("The helper at \(helper.path) didn't start.", stderrTail: tail)
            return
        }
        guard gen == generation else {  // restarted meanwhile
            (t as? HelperProcess)?.close()
            return
        }
        let session = Session(transport: t, client: client, defaults: defaults)
        phase = .ready(session)
        if let instrument, instrument != session.app.instrument {
            await session.app.setInstrument(instrument)
        } else {
            await session.app.load()
        }
        await session.settings.load()
    }
}

/// One choice in the toolbar's Sources menu: `order` nil is the saved order.
public struct SourceChoice: Equatable, Hashable, Sendable {
    public let order: [String]?
    public let label: String

    public init(order: [String]?, label: String) {
        self.order = order
        self.label = label
    }
}

/// The Sources menu's choices for the instrument's enabled sources, in their saved order:
/// "Saved order" (order nil) first; then, for 2 or 3 sources, every ordering (label the
/// names joined by " → "); then, for 2 or more sources, each source alone ("<name> only").
public func sourceChoices(enabled: [String]) -> [SourceChoice] {
    var result = [SourceChoice(order: nil, label: "Saved order")]
    if (2...3).contains(enabled.count) {
        result += permutations(enabled).map { SourceChoice(order: $0, label: $0.joined(separator: " \u{2192} ")) }
    }
    if enabled.count >= 2 {
        result += enabled.map { SourceChoice(order: [$0], label: "\($0) only") }
    }
    return result
}

/// Every ordering of `items`: each item in turn first, then the orderings of the rest.
private func permutations(_ items: [String]) -> [[String]] {
    guard items.count > 1 else { return [items] }
    var out: [[String]] = []
    for (i, first) in items.enumerated() {
        var rest = items
        rest.remove(at: i)
        for p in permutations(rest) { out.append([first] + p) }
    }
    return out
}
