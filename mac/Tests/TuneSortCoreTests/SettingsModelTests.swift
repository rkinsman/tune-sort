import XCTest
@testable import TuneSortCore

@MainActor
final class SettingsModelTests: XCTestCase {
    private func config(bass: [String] = ["songsterr"], guitar: [String] = []) -> ConfigInfo {
        ConfigInfo(path: "/c", exists: true, order: [.bass: bass, .guitar: guitar],
                   sources: [.bass: ["songsterr", "ug", "web"], .guitar: ["songsterr", "ug"]])
    }

    private func defaults() -> UserDefaults { UserDefaults(suiteName: UUID().uuidString)! }

    private func make(_ cfg: ConfigInfo? = nil) async throws -> (SettingsModel, FakeHelperAPI) {
        let api = FakeHelperAPI()
        let c = cfg ?? config(bass: ["ug", "songsterr"], guitar: ["songsterr"])
        api.configure { $0.config = .success(c) }
        let m = SettingsModel(api: api, defaults: defaults())
        try await withTimeout { await m.load() }
        return (m, api)
    }

    private func t(_ n: String, _ e: Bool) -> SourceToggle { SourceToggle(name: n, enabled: e) }

    func testLoadLayout() async throws {
        let (m, _) = try await make()
        XCTAssertEqual(m.orders[.bass], [t("ug", true), t("songsterr", true), t("web", false)])
        XCTAssertEqual(m.orders[.guitar], [t("songsterr", true), t("ug", false)])
        XCTAssertNil(m.error)
    }

    func testMoveCallsSetOrderWithEnabledNamesInOrder() async throws {
        let (m, api) = try await make()
        // bass: ug, songsterr, web(off). Move ug after songsterr.
        try await withTimeout { await m.move(.bass, from: IndexSet(integer: 0), to: 2) }
        let call = try XCTUnwrap(api.setOrderArgs.last)
        XCTAssertEqual(call.0, .bass)
        XCTAssertEqual(call.1, ["songsterr", "ug"])
        XCTAssertEqual(m.orders[.bass], [t("songsterr", true), t("ug", true), t("web", false)])
    }

    func testToggleOnEnablesSourceInPosition() async throws {
        let (m, api) = try await make()
        try await withTimeout { await m.toggle(.bass, "web") }
        XCTAssertEqual(api.setOrderArgs.last?.1, ["ug", "songsterr", "web"])
        XCTAssertEqual(m.orders[.bass], [t("ug", true), t("songsterr", true), t("web", true)])
    }

    func testToggleOffDisablesSource() async throws {
        let (m, api) = try await make()
        try await withTimeout { await m.toggle(.bass, "ug") }
        XCTAssertEqual(api.setOrderArgs.last?.1, ["songsterr"])
        XCTAssertEqual(m.orders[.bass]?.first { $0.name == "ug" }?.enabled, false)
        XCTAssertEqual(m.orders[.bass]?.first { $0.name == "songsterr" }?.enabled, true)
    }

    func testLastEnabledSourceCannotBeTurnedOff() async throws {
        let (m, api) = try await make()
        let before = m.orders
        try await withTimeout { await m.toggle(.guitar, "songsterr") }
        XCTAssertTrue(api.setOrderArgs.isEmpty)
        XCTAssertEqual(m.orders, before)
    }

    func testResetSendsNilAndShowsReturnedOrder() async throws {
        let (m, api) = try await make()
        api.configure { $0.setOrderReply = .success(["web", "songsterr"]) }
        try await withTimeout { await m.reset(.bass) }
        let call = try XCTUnwrap(api.setOrderArgs.last)
        XCTAssertEqual(call.0, .bass)
        XCTAssertNil(call.1)
        XCTAssertEqual(m.orders[.bass], [t("web", true), t("songsterr", true), t("ug", false)])
    }

    func testConfigErrorSetsErrorAndKeepsState() async throws {
        let (m, api) = try await make()
        let before = m.orders
        api.configure { $0.config = .failure(ClientError.helper(kind: "config", message: "bad toml")) }
        try await withTimeout { await m.load() }
        XCTAssertEqual(m.error, "bad toml")
        XCTAssertEqual(m.orders, before)

        api.configure { $0.setOrderReply = .failure(ClientError.helper(kind: "config", message: "bad order")) }
        try await withTimeout { await m.toggle(.bass, "web") }
        XCTAssertEqual(m.error, "bad order")
        XCTAssertEqual(m.orders, before)
    }

    func testErrorClearedAfterSuccess() async throws {
        let (m, api) = try await make()
        api.configure { $0.config = .failure(ClientError.helper(kind: "config", message: "bad toml")) }
        try await withTimeout { await m.load() }
        XCTAssertNotNil(m.error)
        api.configure { $0.config = .success(self.config(bass: ["ug"], guitar: ["ug"])) }
        try await withTimeout { await m.load() }
        XCTAssertNil(m.error)
        XCTAssertEqual(m.orders[.bass], [t("ug", true), t("songsterr", false), t("web", false)])
    }

    func testRepoPathDefaultAndPersistence() async throws {
        let d = defaults()
        let api = FakeHelperAPI()
        let m = SettingsModel(api: api, defaults: d)
        XCTAssertEqual(m.repoPath, ("~/code/tune-sort" as NSString).expandingTildeInPath)
        m.repoPath = "/somewhere/else"
        XCTAssertEqual(d.string(forKey: "repoPath"), "/somewhere/else")
        XCTAssertEqual(SettingsModel(api: api, defaults: d).repoPath, "/somewhere/else")
    }
}
