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
    let state = AppState(defaults: .standard, helperArguments: helperArguments()) { url, args in
        try ProcessTransport(executable: url, arguments: args)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    /// Closes the helper's stdin: it cancels any running sort and exits.
    func applicationWillTerminate(_ notification: Notification) {
        state.shutdown()
    }
}

/// The helper's arguments: `serve`, or in debug builds `TUNESORT_HELPER_ARGS`
/// (space-separated) when set, e.g. to point at a scratch cache.
func helperArguments() -> [String] {
    #if DEBUG
        if let raw = ProcessInfo.processInfo.environment["TUNESORT_HELPER_ARGS"] {
            let args = raw.split(separator: " ").map(String.init)
            if !args.isEmpty { return args }
        }
    #endif
    return ["serve"]
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
