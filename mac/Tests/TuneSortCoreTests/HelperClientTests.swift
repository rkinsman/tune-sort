import XCTest
@testable import TuneSortCore

final class HelperClientTests: XCTestCase {
    private let tuningJSON = #"{"name":"Drop D","playlist_name":"Bass – Drop D","notes":"D A D G"}"#
    private let tuning = TuningInfo(name: "Drop D", playlistName: "Bass – Drop D", notes: "D A D G")
    private let emptyReport = #"{"cancelled":false,"created_playlists":[],"added":{},"already_present":{},"review":[],"lookup_failed":[],"add_errors":[]}"#

    private func expectRequest(_ t: FakeTransport, index: Int, id: Int, cmd: String, args: String,
                               file: StaticString = #filePath, line: UInt = #line) async throws {
        let lines = try await t.waitForWrites(index + 1)
        let r = try SentRequest(lines[index])
        XCTAssertEqual(r.id, id, file: file, line: line)
        XCTAssertEqual(r.cmd, cmd, file: file, line: line)
        XCTAssertEqual(r.keys, ["id", "cmd", "args"], file: file, line: line)
        XCTAssertTrue(try r.argsEqual(args), "args were \(r.args), expected \(args)", file: file, line: line)
    }

    /// Sends one call as request id 1, checks cmd/args, replies with `result`, returns the decoded value.
    private func roundTrip<T: Sendable>(
        cmd: String, args: String, result: String,
        file: StaticString = #filePath, line: UInt = #line,
        call: @escaping @Sendable (HelperClient) async throws -> T
    ) async throws -> T {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let task = Task { try await call(client) }
        try await expectRequest(t, index: 0, id: 1, cmd: cmd, args: args, file: file, line: line)
        t.push(#"{"id":1,"result":\#(result)}"#)
        return try await withTimeout { try await task.value }
    }

    private func collect(_ run: SortRun) async throws -> [SortUpdate] {
        try await withTimeout {
            var out: [SortUpdate] = []
            for try await u in run.updates { out.append(u) }
            return out
        }
    }

    // MARK: start

    func testStartSucceedsOnProtocol1() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let task = Task { try await client.start() }
        try await expectRequest(t, index: 0, id: 1, cmd: "hello", args: "{}")
        t.push(#"{"id":1,"result":{"protocol":1,"instruments":["bass","guitar"]}}"#)
        try await withTimeout { try await task.value }
    }

    func testStartThrowsProtocolMismatch() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let task = Task { try await client.start() }
        try await expectRequest(t, index: 0, id: 1, cmd: "hello", args: "{}")
        t.push(#"{"id":1,"result":{"protocol":2,"instruments":["bass"]}}"#)
        do {
            try await withTimeout { try await task.value }
            XCTFail("expected protocolMismatch")
        } catch {
            XCTAssertEqual(error as? ClientError, .protocolMismatch(helper: 2, expected: 1))
        }
    }

    func testProtocolVersionConstant() {
        XCTAssertEqual(HelperClient.protocolVersion, 1)
    }

    // MARK: methods

    func testPlaylists() async throws {
        let r = try await roundTrip(cmd: "playlists", args: "{}", result: #"["A","B"]"#) { try await $0.playlists() }
        XCTAssertEqual(r, ["A", "B"])
    }

    func testTracks() async throws {
        let r = try await roundTrip(cmd: "tracks", args: #"{"instrument":"bass","playlist":"PL"}"#, result:
            #"[{"artist":"A","title":"T","persistent_id":"P","state":"unknown"}]"#) {
            try await $0.tracks(.bass, playlist: "PL")
        }
        XCTAssertEqual(r, [TrackState(track: Track(artist: "A", title: "T", persistentId: "P"), state: .unknown)])
    }

    func testConfig() async throws {
        let r = try await roundTrip(cmd: "config", args: "{}", result:
            #"{"path":"/c","exists":false,"order":{"bass":["a"],"guitar":[]},"sources":{"bass":[],"guitar":["g"]}}"#) {
            try await $0.config()
        }
        XCTAssertEqual(r, ConfigInfo(path: "/c", exists: false, order: [.bass: ["a"], .guitar: []],
                                     sources: [.bass: [], .guitar: ["g"]]))
    }

    func testSetOrderWithValue() async throws {
        let r = try await roundTrip(cmd: "set_order", args: #"{"instrument":"guitar","order":["x","y"]}"#,
                                    result: #"["x","y"]"#) {
            try await $0.setOrder(.guitar, ["x", "y"])
        }
        XCTAssertEqual(r, ["x", "y"])
    }

    func testSetOrderNilSendsNull() async throws {
        let r = try await roundTrip(cmd: "set_order", args: #"{"instrument":"bass","order":null}"#,
                                    result: #"["default"]"#) {
            try await $0.setOrder(.bass, nil)
        }
        XCTAssertEqual(r, ["default"])
    }

    func testReviewList() async throws {
        let r = try await roundTrip(cmd: "review_list", args: #"{"instrument":"bass"}"#, result:
            #"[{"artist":"A","title":"T","candidates":[]}]"#) { try await $0.reviewList(.bass) }
        XCTAssertEqual(r, [ReviewItem(artist: "A", title: "T", candidates: [])])
    }

    func testDescribeUnwrapsTuning() async throws {
        let json = tuningJSON
        let r = try await roundTrip(cmd: "describe", args: #"{"instrument":"bass","tuning":"Drop D"}"#,
                                    result: #"{"tuning":\#(json)}"#) {
            try await $0.describe(.bass, "Drop D")
        }
        XCTAssertEqual(r, tuning)
    }

    func testSet() async throws {
        let json = tuningJSON
        let r = try await roundTrip(cmd: "set",
            args: #"{"instrument":"bass","artist":"A","title":"T","tuning":"Drop D"}"#,
            result: #"{"artist":"A","title":"T","tuning":\#(json),"source":"manual","confirmed":true}"#) {
            try await $0.set(.bass, artist: "A", title: "T", tuning: "Drop D")
        }
        XCTAssertEqual(r, CachedSong(artist: "A", title: "T", tuning: tuning, source: "manual", confirmed: true))
    }

    func testEntries() async throws {
        let json = tuningJSON
        let r = try await roundTrip(cmd: "entries", args: #"{"instrument":"guitar"}"#,
            result: #"[{"artist":"A","title":"T","tuning":\#(json),"source":"web","confirmed":false}]"#) {
            try await $0.entries(.guitar)
        }
        XCTAssertEqual(r, [CachedSong(artist: "A", title: "T", tuning: tuning, source: "web", confirmed: false)])
    }

    func testDelete() async throws {
        try await roundTrip(cmd: "delete", args: #"{"instrument":"bass","artist":"AC/DC","title":"T.N.T."}"#,
                            result: "{}") {
            try await $0.delete(.bass, artist: "AC/DC", title: "T.N.T.")
        }
    }

    // MARK: matching

    func testRequestIdsIncrementAndRepliesMatchOutOfOrder() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let first = Task { try await client.playlists() }
        try await expectRequest(t, index: 0, id: 1, cmd: "playlists", args: "{}")
        let second = Task { try await client.config() }
        try await expectRequest(t, index: 1, id: 2, cmd: "config", args: "{}")
        t.push(#"{"id":2,"result":{"path":"/c","exists":true,"order":{"bass":[],"guitar":[]},"sources":{"bass":[],"guitar":[]}}}"#)
        t.push(#"{"id":1,"result":["P"]}"#)
        let p = try await withTimeout { try await first.value }
        let c = try await withTimeout { try await second.value }
        XCTAssertEqual(p, ["P"])
        XCTAssertEqual(c.path, "/c")
    }

    func testIdCountsHelloAndLaterRequests() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let s = Task { try await client.start() }
        try await expectRequest(t, index: 0, id: 1, cmd: "hello", args: "{}")
        t.push(#"{"id":1,"result":{"protocol":1,"instruments":[]}}"#)
        try await withTimeout { try await s.value }
        let p = Task { try await client.playlists() }
        try await expectRequest(t, index: 1, id: 2, cmd: "playlists", args: "{}")
        t.push(#"{"id":2,"result":[]}"#)
        let r = try await withTimeout { try await p.value }
        XCTAssertEqual(r, [])
    }

    func testErrorReplyBecomesHelperError() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let task = Task { try await client.playlists() }
        try await expectRequest(t, index: 0, id: 1, cmd: "playlists", args: "{}")
        t.push(#"{"id":1,"error":{"kind":"music","message":"Music is closed"}}"#)
        do {
            _ = try await withTimeout { try await task.value }
            XCTFail("expected error")
        } catch {
            XCTAssertEqual(error as? ClientError, .helper(kind: "music", message: "Music is closed"))
        }
    }

    func testNonJSONAndUnknownIdLinesAreSkipped() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let task = Task { try await client.playlists() }
        try await expectRequest(t, index: 0, id: 1, cmd: "playlists", args: "{}")
        t.push("this is not json")
        t.push(#"{"id":null,"error":{"kind":"bad_request","message":"unparseable"}}"#)
        t.push(#"{"id":99,"result":["wrong"]}"#)
        t.push(#"{"id":1,"result":["right"]}"#)
        let r = try await withTimeout { try await task.value }
        XCTAssertEqual(r, ["right"])
    }

    // MARK: sort / cancel

    func testSortStreamsEventsThenFinished() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let req = SortRequest(instrument: .bass, playlist: "PL", dryRun: true, order: ["a"], source: nil, recheck: false)
        let sortTask = Task { try await client.sort(req) }
        try await expectRequest(t, index: 0, id: 1, cmd: "sort",
            args: #"{"instrument":"bass","playlist":"PL","dry_run":true,"recheck":false,"order":["a"]}"#)
        let run = try await withTimeout { try await sortTask.value }
        XCTAssertEqual(run.id, 1)

        t.push(#"{"id":1,"event":"start","data":{"i":1,"total":1,"artist":"A","title":"T"}}"#)
        t.push(#"{"id":1,"event":"done","data":{"artist":"A","title":"T","status":"review"}}"#)
        t.push(#"{"id":1,"result":\#(emptyReport)}"#)

        let updates = try await collect(run)
        XCTAssertEqual(updates, [
            .event(.start(SortStart(i: 1, total: 1, artist: "A", title: "T"))),
            .event(.done(SortDone(artist: "A", title: "T", status: .review))),
            .finished(Report(cancelled: false, createdPlaylists: [], added: [:], alreadyPresent: [:],
                             review: [], lookupFailed: [], addErrors: [])),
        ])
    }

    func testSortErrorReplyThrowsOnStream() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let sortTask = Task { try await client.sort(SortRequest(instrument: .bass, playlist: "PL", dryRun: false)) }
        _ = try await t.waitForWrites(1)
        let run = try await withTimeout { try await sortTask.value }
        t.push(#"{"id":1,"error":{"kind":"busy","message":"busy"}}"#)
        do {
            _ = try await collect(run)
            XCTFail("expected error")
        } catch {
            XCTAssertEqual(error as? ClientError, .helper(kind: "busy", message: "busy"))
        }
    }

    func testCancelWritesCancelRequest() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let sortTask = Task { try await client.sort(SortRequest(instrument: .bass, playlist: "PL", dryRun: false)) }
        _ = try await t.waitForWrites(1)
        let run = try await withTimeout { try await sortTask.value }
        let cancelTask = Task { try await client.cancel(run) }
        try await expectRequest(t, index: 1, id: 2, cmd: "cancel", args: #"{"id":1}"#)
        t.push(#"{"id":2,"result":{}}"#)
        try await withTimeout { try await cancelTask.value }
        t.push(#"{"id":1,"result":\#(emptyReport)}"#)
        let updates = try await collect(run)
        XCTAssertEqual(updates.count, 1)
    }

    func testCancelBadRequestThrownButSortContinues() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let sortTask = Task { try await client.sort(SortRequest(instrument: .bass, playlist: "PL", dryRun: false)) }
        _ = try await t.waitForWrites(1)
        let run = try await withTimeout { try await sortTask.value }

        t.push(#"{"id":1,"event":"start","data":{"i":1,"total":1,"artist":"A","title":"T"}}"#)
        let cancelTask = Task { try await client.cancel(run) }
        try await expectRequest(t, index: 1, id: 2, cmd: "cancel", args: #"{"id":1}"#)
        t.push(#"{"id":2,"error":{"kind":"bad_request","message":"no such run"}}"#)
        do {
            try await withTimeout { try await cancelTask.value }
            XCTFail("expected cancel to throw")
        } catch {
            XCTAssertEqual(error as? ClientError, .helper(kind: "bad_request", message: "no such run"))
        }
        t.push(#"{"id":1,"event":"done","data":{"artist":"A","title":"T","status":"added","playlist":"PL"}}"#)
        t.push(#"{"id":1,"result":\#(emptyReport)}"#)

        let updates = try await collect(run)
        XCTAssertEqual(updates.count, 3)
        guard case .finished(let report) = updates.last else {
            return XCTFail("last update should be .finished")
        }
        XCTAssertFalse(report.cancelled)
    }

    // MARK: transport end

    func testTransportErrorFailsEveryPendingRequest() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let a = Task { try await client.playlists() }
        try await expectRequest(t, index: 0, id: 1, cmd: "playlists", args: "{}")
        let b = Task { try await client.config() }
        try await expectRequest(t, index: 1, id: 2, cmd: "config", args: "{}")
        t.finish(throwing: ClientError.helperExited(stderrTail: ["boom"]))
        for task in [a.asVoid, b.asVoid] {
            do {
                try await withTimeout { try await task.value }
                XCTFail("expected helperExited")
            } catch {
                XCTAssertEqual(error as? ClientError, .helperExited(stderrTail: ["boom"]))
            }
        }
    }

    func testTransportEndingNormallyFailsPendingWithHelperExited() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let a = Task { try await client.playlists() }
        try await expectRequest(t, index: 0, id: 1, cmd: "playlists", args: "{}")
        t.finish()
        do {
            _ = try await withTimeout { try await a.value }
            XCTFail("expected helperExited")
        } catch {
            guard case .helperExited? = error as? ClientError else {
                return XCTFail("expected helperExited, got \(error)")
            }
        }
    }

    func testTransportEndFailsRunningSort() async throws {
        let t = FakeTransport()
        let client = HelperClient(transport: t)
        let sortTask = Task { try await client.sort(SortRequest(instrument: .bass, playlist: "PL", dryRun: false)) }
        _ = try await t.waitForWrites(1)
        let run = try await withTimeout { try await sortTask.value }
        t.finish(throwing: ClientError.helperExited(stderrTail: ["boom"]))
        do {
            _ = try await collect(run)
            XCTFail("expected helperExited")
        } catch {
            XCTAssertEqual(error as? ClientError, .helperExited(stderrTail: ["boom"]))
        }
    }

    // MARK: ProcessTransport

    func testProcessTransportMissingExecutable() {
        let path = "/nonexistent/dir/tunesort-helper"
        XCTAssertThrowsError(try ProcessTransport(executable: URL(fileURLWithPath: path), arguments: [])) { error in
            XCTAssertEqual(error as? ClientError, .helperNotFound(path: path))
        }
    }
}

private extension Task where Failure == Error {
    var asVoid: Task<Void, Error> {
        let t = self
        return Task<Void, Error> { _ = try await t.value }
    }
}
