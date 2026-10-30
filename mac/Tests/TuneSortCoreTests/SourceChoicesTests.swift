import XCTest
@testable import TuneSortCore

final class SourceChoicesTests: XCTestCase {
    private let saved = SourceChoice(order: nil, label: "Saved order")

    func testNoSourcesGivesOnlySavedOrder() {
        XCTAssertEqual(sourceChoices(enabled: []), [saved])
    }

    func testOneSourceGivesOnlySavedOrder() {
        XCTAssertEqual(sourceChoices(enabled: ["a"]), [saved])
    }

    func testTwoSources() {
        XCTAssertEqual(sourceChoices(enabled: ["a", "b"]), [
            saved,
            SourceChoice(order: ["a", "b"], label: "a → b"),
            SourceChoice(order: ["b", "a"], label: "b → a"),
            SourceChoice(order: ["a"], label: "a only"),
            SourceChoice(order: ["b"], label: "b only"),
        ])
    }

    func testThreeSources() {
        XCTAssertEqual(sourceChoices(enabled: ["a", "b", "c"]), [
            saved,
            SourceChoice(order: ["a", "b", "c"], label: "a → b → c"),
            SourceChoice(order: ["a", "c", "b"], label: "a → c → b"),
            SourceChoice(order: ["b", "a", "c"], label: "b → a → c"),
            SourceChoice(order: ["b", "c", "a"], label: "b → c → a"),
            SourceChoice(order: ["c", "a", "b"], label: "c → a → b"),
            SourceChoice(order: ["c", "b", "a"], label: "c → b → a"),
            SourceChoice(order: ["a"], label: "a only"),
            SourceChoice(order: ["b"], label: "b only"),
            SourceChoice(order: ["c"], label: "c only"),
        ])
    }

    func testFourSourcesGiveNoPermutations() {
        XCTAssertEqual(sourceChoices(enabled: ["a", "b", "c", "d"]), [
            saved,
            SourceChoice(order: ["a"], label: "a only"),
            SourceChoice(order: ["b"], label: "b only"),
            SourceChoice(order: ["c"], label: "c only"),
            SourceChoice(order: ["d"], label: "d only"),
        ])
    }

    func testInputOrderIsRespected() {
        let r = sourceChoices(enabled: ["web", "ug"])
        XCTAssertEqual(r.map(\.label), ["Saved order", "web → ug", "ug → web", "web only", "ug only"])
    }
}
