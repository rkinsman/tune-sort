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

    /// Bumped on every `typedChanged`; a reply applies only if no newer change started.
    private var typedGeneration = 0

    public func typedChanged() async {
        typedGeneration += 1
        let gen = typedGeneration
        let text = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty {
            typedResult = nil
            return
        }
        let result: Result<TuningInfo, ClientError>
        do {
            result = .success(try await api.describe(app.instrument, text))
        } catch let e as ClientError {
            result = .failure(e)
        } catch {
            if !(error is CancellationError) { app.show(error) }
            return
        }
        guard gen == typedGeneration else { return }
        typedResult = result
    }

    public func use(_ match: MatchInfo) async { await store(match.tuning.name) }

    public func save() async {
        let text = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        await store(text)
    }

    public func clear() async {
        guard let row else { return }
        do {
            try await api.delete(app.instrument, artist: row.artist, title: row.title)
        } catch {
            app.show(error)
            return
        }
        await app.refreshRow(artist: row.artist, title: row.title)
    }

    private func store(_ tuning: String) async {
        guard let row else { return }
        do {
            _ = try await api.set(app.instrument, artist: row.artist, title: row.title, tuning: tuning)
        } catch let ClientError.helper(kind, message) where kind == "bad_tuning" {
            typedResult = .failure(.helper(kind: kind, message: message))
            return
        } catch {
            app.show(error)
            return
        }
        await app.refreshRow(artist: row.artist, title: row.title)
    }
}
