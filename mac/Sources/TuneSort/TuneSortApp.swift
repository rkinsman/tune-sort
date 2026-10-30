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
    var body: some Scene {
        WindowGroup {}
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
