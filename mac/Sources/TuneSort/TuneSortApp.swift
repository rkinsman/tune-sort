import AppKit
import SwiftUI
import TuneSortCore

@main
enum Entry {
    /// `TuneSort --selftest <helper> [args...]` starts the helper, says hello, prints
    /// `playlists()` and exits. Anything else runs the app.
    static func main() {
        let args = CommandLine.arguments
        if let i = args.firstIndex(of: "--selftest") {
            SelfTest.run(Array(args[(i + 1)...]))
        } else {
            TuneSortApp.main()
        }
    }
}

struct TuneSortApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        Window("TuneSort", id: "main") {
            RootView(state: delegate.state)
        }
        .defaultSize(width: 1100, height: 680)
        Settings {
            SettingsView(state: delegate.state)
        }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let state = AppState()

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    /// Closes the helper's stdin: it cancels any running sort and exits.
    func applicationWillTerminate(_ notification: Notification) {
        state.shutdown()
    }
}

/// What the window shows: the helper's state, then the app once it has said hello.
enum Phase {
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
final class Session {
    let transport: ProcessTransport
    let client: HelperClient
    let app: AppModel
    let panel: SidePanelModel
    let settings: SettingsModel

    init(transport: ProcessTransport, client: HelperClient) {
        self.transport = transport
        self.client = client
        app = AppModel(api: client)
        panel = SidePanelModel(api: client, app: app)
        settings = SettingsModel(api: client, defaults: .standard)
    }
}

/// Owns the helper process: starts it, restarts it, and closes it on quit.
@MainActor @Observable
final class AppState {
    static let repoPathKey = "repoPath"

    var phase: Phase = .starting
    /// The repo path the setup screen edits; the same default `SettingsModel` uses.
    var repoPath: String {
        didSet { UserDefaults.standard.set(repoPath, forKey: Self.repoPathKey) }
    }

    @ObservationIgnored private var transport: ProcessTransport?
    @ObservationIgnored private var started = false

    init() {
        repoPath = Self.savedRepoPath()
    }

    var session: Session? {
        if case .ready(let s) = phase { return s }
        return nil
    }

    private static func savedRepoPath() -> String {
        UserDefaults.standard.string(forKey: repoPathKey)
            ?? NSString(string: "~/code/tune-sort").expandingTildeInPath
    }

    /// The helper's arguments: `serve`, or in debug builds `TUNESORT_HELPER_ARGS`
    /// (space-separated) when set, e.g. to point at a scratch cache.
    static func helperArguments() -> [String] {
        #if DEBUG
            if let raw = ProcessInfo.processInfo.environment["TUNESORT_HELPER_ARGS"] {
                let args = raw.split(separator: " ").map(String.init)
                if !args.isEmpty { return args }
            }
        #endif
        return ["serve"]
    }

    /// Starts the helper once; later calls do nothing.
    func startIfNeeded() async {
        guard !started else { return }
        started = true
        await start()
    }

    /// Closes the current helper and starts a new one, keeping the instrument.
    func restart() async {
        let instrument = session?.app.instrument
        shutdown()
        repoPath = Self.savedRepoPath()
        await start(instrument: instrument)
    }

    /// Closes the helper's stdin, which cancels a running sort; the helper then exits.
    func shutdown() {
        transport?.close()
        transport = nil
    }

    private func start(instrument: Instrument? = nil) async {
        phase = .starting
        let root = URL(fileURLWithPath: NSString(string: repoPath).expandingTildeInPath)
        let helper = root.appendingPathComponent(".venv/bin/tune-sort")
        let t: ProcessTransport
        do {
            t = try ProcessTransport(executable: helper, arguments: Self.helperArguments())
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
            t.close()
            transport = nil
            phase = .mismatch(
                "Helper speaks protocol \(helperVersion), the app expects \(expected). Pull and rebuild.")
            return
        } catch {
            var tail = t.stderrTail
            if case ClientError.helperExited(let errTail) = error, !errTail.isEmpty { tail = errTail }
            t.close()
            transport = nil
            phase = .failed("The helper at \(helper.path) didn't start.", stderrTail: tail)
            return
        }
        guard transport === t else { return }  // restarted meanwhile
        let session = Session(transport: t, client: client)
        phase = .ready(session)
        if let instrument, instrument != session.app.instrument {
            await session.app.setInstrument(instrument)
        } else {
            await session.app.load()
        }
        await session.settings.load()
    }
}

enum SelfTest {
    static func run(_ args: [String]) -> Never {
        guard let helper = args.first else {
            FileHandle.standardError.write(Data("usage: TuneSort --selftest <helper> [args...]\n".utf8))
            exit(2)
        }
        Task {
            var transport: ProcessTransport?
            do {
                let t = try ProcessTransport(
                    executable: URL(fileURLWithPath: helper), arguments: Array(args.dropFirst()))
                transport = t
                let client = HelperClient(transport: t)
                try await client.start()
                print("hello: protocol \(HelperClient.protocolVersion) ok")
                let playlists = try await client.playlists()
                print("playlists (\(playlists.count)):")
                for name in playlists { print("  \(name)") }
                t.close()
                exit(0)
            } catch {
                print("selftest failed: \(error)")
                for line in transport?.stderrTail ?? [] { print("  stderr: \(line)") }
                exit(1)
            }
        }
        dispatchMain()
    }
}
