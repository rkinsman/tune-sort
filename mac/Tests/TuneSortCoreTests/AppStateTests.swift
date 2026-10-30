import XCTest
@testable import TuneSortCore

/// A HelperProcess that answers requests by command, recording close().
final class ScriptedProcess: HelperProcess, @unchecked Sendable {
    enum Hello {
        case ok(protocolVersion: Int)
        case exits(tail: [String])
    }

    private let inner = FakeTransport()
    private let lock = NSLock()
    private var closeCount = 0
    private let hello: Hello
    private let helloGate: Gate?
    let stderrTail: [String]

    init(hello: Hello = .ok(protocolVersion: 1), helloGate: Gate? = nil, stderrTail: [String] = []) {
        self.hello = hello
        self.helloGate = helloGate
        self.stderrTail = stderrTail
    }

    var lines: AsyncThrowingStream<Data, Error> { inner.lines }

    func close() { lock.withLock { closeCount += 1 } }
    var closes: Int { lock.withLock { closeCount } }

    var requests: [SentRequest] { inner.writtenLines.compactMap { try? SentRequest($0) } }
    func waitForRequest(_ cmd: String, timeout: Double = 5) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while !requests.contains(where: { $0.cmd == cmd }) {
            if Date() > deadline { throw TestTimeout() }
            try await Task.sleep(nanoseconds: 2_000_000)
        }
    }

    func write(_ line: Data) async throws {
        try await inner.write(line)
        guard let req = try? SentRequest(line) else { return }
        let id = req.id
        if req.cmd == "hello" {
            let hello = self.hello
            let gate = helloGate
            Task {
                if let gate { await gate.wait() }
                switch hello {
                case .ok(let v):
                    self.inner.push(#"{"id":\#(id),"result":{"protocol":\#(v),"instruments":["bass","guitar"]}}"#)
                case .exits(let tail):
                    self.inner.finish(throwing: ClientError.helperExited(stderrTail: tail))
                }
            }
        } else if req.cmd == "config" {
            inner.push(#"{"id":\#(id),"result":{"path":"/c","exists":false,"order":{"bass":[],"guitar":[]},"sources":{"bass":[],"guitar":[]}}}"#)
        } else {
            inner.push(#"{"id":\#(id),"result":[]}"#)
        }
    }
}

/// Factory recording calls and handing out scripted processes in order.
@MainActor
final class ProcessFactory {
    var urls: [URL] = []
    var args: [[String]] = []
    var processes: [ScriptedProcess] = []
    var make: (Int) throws -> ScriptedProcess
    init(_ make: @escaping (Int) throws -> ScriptedProcess = { _ in ScriptedProcess() }) { self.make = make }

    func transport(_ url: URL, _ a: [String]) throws -> Transport {
        urls.append(url)
        args.append(a)
        let p = try make(urls.count - 1)
        processes.append(p)
        return p
    }

    func waitForFactory(_ n: Int, timeout: Double = 5) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while processes.count < n {
            if Date() > deadline { throw TestTimeout() }
            try await Task.sleep(nanoseconds: 2_000_000)
        }
    }
}

@MainActor
final class AppStateTests: XCTestCase {
    private var defaults: UserDefaults!
    private var suite = ""

    override func setUp() async throws {
        suite = "AppStateTests-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suite)
        defaults.set("/tmp/ts-repo-a", forKey: AppState.repoPathKey)
    }

    override func tearDown() async throws {
        defaults.removePersistentDomain(forName: suite)
    }

    private func state(_ f: ProcessFactory) -> AppState {
        AppState(defaults: defaults, makeTransport: { try f.transport($0, $1) })
    }

    private let helperA = "/tmp/ts-repo-a/.venv/bin/tune-sort"

    func testHelperURL() {
        XCTAssertEqual(AppState.helperURL(repoPath: "/x/y").path, "/x/y/.venv/bin/tune-sort")
        let home = NSHomeDirectory()
        XCTAssertEqual(AppState.helperURL(repoPath: "~/code/tune-sort").path, home + "/code/tune-sort/.venv/bin/tune-sort")
    }

    func testRepoPathDefaultsAndWritesDefaults() {
        let fresh = UserDefaults(suiteName: suite + "-fresh")!
        defer { fresh.removePersistentDomain(forName: suite + "-fresh") }
        let s = AppState(defaults: fresh, makeTransport: { _, _ in ScriptedProcess() })
        XCTAssertEqual(s.repoPath, NSHomeDirectory() + "/code/tune-sort")
        s.repoPath = "/somewhere"
        XCTAssertEqual(fresh.string(forKey: AppState.repoPathKey), "/somewhere")
    }

    func testFactoryReceivesHelperURLAndArguments() async {
        let f = ProcessFactory()
        let s = state(f)
        await s.startIfNeeded()
        XCTAssertEqual(f.urls.map(\.path), [helperA])
        XCTAssertEqual(f.args, [["serve"]])
    }

    func testHelperNotFoundGivesSetupPhase() async {
        let s = AppState(defaults: defaults, makeTransport: { _, _ in throw ClientError.helperNotFound(path: "/nope") })
        await s.startIfNeeded()
        XCTAssertEqual(s.phase, .setup(path: "/nope"))
    }

    func testOtherFactoryErrorGivesFailed() async {
        struct Boom: LocalizedError { var errorDescription: String? { "kaboom" } }
        let s = AppState(defaults: defaults, makeTransport: { _, _ in throw Boom() })
        await s.startIfNeeded()
        XCTAssertEqual(s.phase, .failed("Couldn't start the helper at \(helperA): kaboom", stderrTail: []))
    }

    func testProtocolMismatchClosesAndReportsMismatch() async {
        let f = ProcessFactory { _ in ScriptedProcess(hello: .ok(protocolVersion: 2)) }
        let s = state(f)
        await s.startIfNeeded()
        XCTAssertEqual(s.phase, .mismatch("Helper speaks protocol 2, the app expects 1. Pull and rebuild."))
        XCTAssertEqual(f.processes.first?.closes, 1)
    }

    func testHelloFailureUsesErrorTail() async {
        let f = ProcessFactory { _ in ScriptedProcess(hello: .exits(tail: ["boom"]), stderrTail: ["other"]) }
        let s = state(f)
        await s.startIfNeeded()
        XCTAssertEqual(s.phase, .failed("The helper at \(helperA) didn't start.", stderrTail: ["boom"]))
        XCTAssertEqual(f.processes.first?.closes, 1)
    }

    func testHelloFailureFallsBackToTransportTail() async {
        let f = ProcessFactory { _ in ScriptedProcess(hello: .exits(tail: []), stderrTail: ["from transport"]) }
        let s = state(f)
        await s.startIfNeeded()
        XCTAssertEqual(s.phase, .failed("The helper at \(helperA) didn't start.", stderrTail: ["from transport"]))
    }

    func testSuccessIsReadyAndLoadsAreSent() async throws {
        let f = ProcessFactory()
        let s = state(f)
        await s.startIfNeeded()
        guard case .ready(let session) = s.phase else { return XCTFail("expected ready, got \(s.phase)") }
        XCTAssertTrue(s.session === session)
        XCTAssertFalse(s.isStarting)
        let cmds = f.processes[0].requests.map(\.cmd)
        XCTAssertEqual(cmds.first, "hello")
        XCTAssertTrue(cmds.contains("playlists"), "\(cmds)")
        XCTAssertTrue(cmds.contains("review_list"), "\(cmds)")
        XCTAssertTrue(cmds.contains("config"), "\(cmds)")
        XCTAssertEqual(f.processes[0].closes, 0)
        let hello = try XCTUnwrap(f.processes[0].requests.first)
        XCTAssertEqual(hello.id, 1)
        XCTAssertTrue(try hello.argsEqual("{}"))
    }

    func testStartIfNeededTwiceStartsOnce() async {
        let f = ProcessFactory()
        let s = state(f)
        await s.startIfNeeded()
        await s.startIfNeeded()
        XCTAssertEqual(f.urls.count, 1)
    }

    func testRestartClosesOldAndStartsNew() async {
        let f = ProcessFactory()
        let s = state(f)
        await s.startIfNeeded()
        await s.restart()
        XCTAssertEqual(f.urls.count, 2)
        XCTAssertEqual(f.processes[0].closes, 1)
        XCTAssertEqual(f.processes[1].closes, 0)
        guard case .ready(let session) = s.phase else { return XCTFail("expected ready") }
        XCTAssertTrue((session.transport as AnyObject) === f.processes[1])
    }

    func testRestartWhileStartingIsNoOp() async throws {
        let gate = Gate()
        let f = ProcessFactory { _ in ScriptedProcess(helloGate: gate) }
        let s = state(f)
        let first = Task { await s.startIfNeeded() }
        try await f.waitForFactory(1)
        XCTAssertTrue(s.isStarting)
        XCTAssertEqual(s.phase, .starting)
        await s.restart()
        XCTAssertEqual(f.urls.count, 1)
        gate.open()
        await first.value
        XCTAssertEqual(f.urls.count, 1)
        XCTAssertEqual(f.processes[0].closes, 0)
        if case .ready = s.phase {} else { XCTFail("expected ready, got \(s.phase)") }
    }

    func testRestartPicksUpChangedRepoPath() async {
        let f = ProcessFactory()
        let s = state(f)
        await s.startIfNeeded()
        defaults.set("/tmp/ts-repo-b", forKey: AppState.repoPathKey)
        await s.restart()
        XCTAssertEqual(f.urls.map(\.path), [helperA, "/tmp/ts-repo-b/.venv/bin/tune-sort"])
    }

    func testRestartRestoresInstrument() async throws {
        let f = ProcessFactory()
        let s = state(f)
        await s.startIfNeeded()
        let session = try XCTUnwrap(s.session)
        await session.app.setInstrument(.guitar)
        await s.restart()
        let newSession = try XCTUnwrap(s.session)
        XCTAssertFalse(newSession === session)
        XCTAssertEqual(newSession.app.instrument, .guitar)
        let reqs = f.processes[1].requests
        XCTAssertTrue(reqs.contains { ($0.args["instrument"] as? String) == "guitar" },
                      "new helper should be asked about guitar: \(reqs.map(\.cmd))")
    }

    func testShutdownClosesTransport() async {
        let f = ProcessFactory()
        let s = state(f)
        await s.startIfNeeded()
        s.shutdown()
        XCTAssertEqual(f.processes[0].closes, 1)
        s.shutdown()
        XCTAssertEqual(f.processes[0].closes, 1, "transport is forgotten after shutdown")
    }

    func testShutdownDuringPendingHelloDiscardsLateSuccess() async throws {
        let gate = Gate()
        let f = ProcessFactory { _ in ScriptedProcess(helloGate: gate) }
        let s = state(f)
        let first = Task { await s.startIfNeeded() }
        try await f.waitForFactory(1)
        try await f.processes[0].waitForRequest("hello")
        s.shutdown()
        XCTAssertEqual(f.processes[0].closes, 1)
        gate.open()
        await first.value
        if case .ready = s.phase { XCTFail("superseded start must not become ready") }
        XCTAssertNil(s.session)
        XCTAssertGreaterThanOrEqual(f.processes[0].closes, 1)
    }
}
