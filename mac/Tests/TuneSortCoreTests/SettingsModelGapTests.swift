import XCTest
@testable import TuneSortCore

@MainActor
final class SettingsModelGapTests: XCTestCase {
    private func t(_ n: String, _ e: Bool) -> SourceToggle { SourceToggle(name: n, enabled: e) }

    private func make(bass: [String], sources: [String]) async throws -> (SettingsModel, FakeHelperAPI) {
        let api = FakeHelperAPI()
        api.configure {
            $0.config = .success(ConfigInfo(path: "/c", exists: true, order: [.bass: bass, .guitar: ["songsterr"]],
                                            sources: [.bass: sources, .guitar: ["songsterr", "ug"]]))
        }
        let m = SettingsModel(api: api, defaults: UserDefaults(suiteName: UUID().uuidString)!)
        try await withTimeout { await m.load() }
        return (m, api)
    }

    // 2. Reentrancy while setOrder is in flight.
    func testChangesIgnoredWhileSetOrderInFlight() async throws {
        let (m, api) = try await make(bass: ["ug", "songsterr"], sources: ["songsterr", "ug", "web"])
        let gate = Gate()
        api.configure { $0.setOrderGate = gate }

        let first = Task { await m.toggle(.bass, "web") }
        try await api.waitForCall("setOrder:bass")

        try await withTimeout { await m.toggle(.bass, "ug") }
        try await withTimeout { await m.move(.bass, from: IndexSet(integer: 0), to: 2) }
        try await withTimeout { await m.reset(.bass) }
        try await withTimeout { await m.toggle(.guitar, "ug") }
        XCTAssertEqual(api.setOrderArgs.count, 1, "no further setOrder while one is in flight")

        gate.open()
        try await withTimeout { await first.value }
        XCTAssertEqual(m.orders[.bass], [t("ug", true), t("songsterr", true), t("web", true)])

        try await withTimeout { await m.toggle(.bass, "ug") }
        XCTAssertEqual(api.setOrderArgs.count, 2)
        XCTAssertEqual(api.setOrderArgs.last?.1, ["songsterr", "web"])
        XCTAssertEqual(m.orders[.bass], [t("ug", false), t("songsterr", true), t("web", true)])
    }

    // 5. Readable error text for non-config errors.
    func testNonConfigHelperErrorShowsMessageText() async throws {
        let (m, api) = try await make(bass: ["ug", "songsterr"], sources: ["songsterr", "ug", "web"])
        api.configure { $0.setOrderReply = .failure(ClientError.helper(kind: "internal", message: "boom")) }
        try await withTimeout { await m.toggle(.bass, "web") }
        XCTAssertEqual(m.error, "boom")
    }

    // 6. Move semantics (Array.move(fromOffsets:toOffset:)), all four sources enabled.
    private func moved(from: IndexSet, to: Int) async throws -> ([String]?, [SourceToggle]?) {
        let (m, api) = try await make(bass: ["a", "b", "c", "d"], sources: ["a", "b", "c", "d"])
        try await withTimeout { await m.move(.bass, from: from, to: to) }
        return (api.setOrderArgs.last?.1, m.orders[.bass])
    }

    private func allOn(_ names: [String]) -> [SourceToggle] { names.map { t($0, true) } }

    func testMoveLastToFront() async throws {
        let (args, orders) = try await moved(from: IndexSet(integer: 2), to: 0)
        XCTAssertEqual(args, ["c", "a", "b", "d"])
        XCTAssertEqual(orders, allOn(["c", "a", "b", "d"]))
    }

    func testMoveFirstToEnd() async throws {
        let (args, orders) = try await moved(from: IndexSet(integer: 0), to: 4)
        XCTAssertEqual(args, ["b", "c", "d", "a"])
        XCTAssertEqual(orders, allOn(["b", "c", "d", "a"]))
    }

    func testMoveTwoOffsetsToEnd() async throws {
        let (args, orders) = try await moved(from: IndexSet([0, 2]), to: 4)
        XCTAssertEqual(args, ["b", "d", "a", "c"])
        XCTAssertEqual(orders, allOn(["b", "d", "a", "c"]))
    }
}
