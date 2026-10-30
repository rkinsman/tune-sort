import Foundation
import Observation

/// State for the selected-song side panel. `row` follows the app's selection.
@MainActor @Observable
public final class SidePanelModel {
    @ObservationIgnored let api: HelperAPI
    @ObservationIgnored let app: AppModel

    /// The text typed in the "type a tuning" field.
    public var typed: String = ""
    /// The latest `describe` outcome for `typed`; nil when `typed` is blank or not yet answered.
    public var typedResult: Result<TuningInfo, ClientError>?

    public init(api: HelperAPI, app: AppModel) {
        self.api = api
        self.app = app
    }

    /// The selected song: the row in `app.rows` whose id is `app.selectedRowID`.
    public var row: SongRow? {
        guard let id = app.selectedRowID else { return nil }
        return app.rows.first { $0.id == id }
    }

    public func typedChanged() async { fatalError("unimplemented") }
    public func use(_ match: MatchInfo) async { fatalError("unimplemented") }
    public func save() async { fatalError("unimplemented") }
    public func clear() async { fatalError("unimplemented") }
}
