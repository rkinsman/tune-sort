import SwiftUI
import TuneSortCore

/// The selected song: review candidates, its cached tuning, or why it has none.
struct SidePanelView: View {
    let app: AppModel
    @Bindable var panel: SidePanelModel

    private var isRunning: Bool { app.runState != .idle }

    var body: some View {
        Group {
            if let row = panel.row {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(row.title).font(.title3.weight(.semibold))
                            Text(row.artist).foregroundStyle(.secondary)
                        }
                        content(row)
                    }
                    .padding()
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .disabled(isRunning)
            } else {
                ContentUnavailableView("No song selected", systemImage: "music.note")
            }
        }
        .onChange(of: app.selectedRowID) {
            panel.typed = ""
        }
        .onChange(of: panel.typed) {
            Task { await panel.typedChanged() }
        }
    }

    @ViewBuilder
    private func content(_ row: SongRow) -> some View {
        switch row.status {
        case .review(let candidates):
            Text("Needs review").font(.headline)
            if candidates.isEmpty {
                Text("No candidates to choose from. Type the tuning below.")
                    .foregroundStyle(.secondary)
            } else {
                Text("Matches found:").foregroundStyle(.secondary)
                ForEach(Array(candidates.enumerated()), id: \.offset) { _, match in
                    CandidateButton(match: match) { Task { await panel.use(match) } }
                }
            }
            TuningField(panel: panel, actionTitle: "Save")
        case let .cached(tuning, source, confirmed):
            Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 6) {
                GridRow {
                    Text("Tuning").foregroundStyle(.secondary)
                    Text(tuning.name).fontWeight(.medium)
                }
                GridRow {
                    Text("Notes").foregroundStyle(.secondary)
                    Text(tuning.notes)
                }
                GridRow {
                    Text("Source").foregroundStyle(.secondary)
                    Text(source)
                }
                GridRow {
                    Text("Confirmed").foregroundStyle(.secondary)
                    Text(confirmed ? "Yes" : "No")
                }
            }
            Divider()
            TuningField(panel: panel, actionTitle: "Change")
            Text("Changing the tuning updates the cache only. The song stays in its old tuning playlist; the next sort adds it to the new one.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Button("Clear", role: .destructive) { Task { await panel.clear() } }
                .help("Forget this song's tuning; the next sort looks it up again")
        case .failed(let sources):
            Text("Lookup failed").font(.headline)
            Text(sources.isEmpty
                 ? "The lookup failed. The next sort retries."
                 : "These sources failed: \(sources.joined(separator: ", ")). The next sort retries.")
                .fixedSize(horizontal: false, vertical: true)
        case .unknown:
            Text("Not looked up yet. Sorting this playlist looks it up.")
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        case .lookingUp:
            HStack {
                ProgressView().controlSize(.small)
                Text("Looking up…")
            }
        case .addError(let message):
            Text("Couldn't add to its playlist").font(.headline)
            Text(message).foregroundStyle(.secondary).textSelection(.enabled)
        }
    }
}

struct CandidateButton: View {
    let match: MatchInfo
    let action: () -> Void

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Button(action: action) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(match.tuning.name).fontWeight(.medium)
                    Text("\(match.matchedArtist) – \(match.matchedTitle)\(match.exact ? "" : " (close match)")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(match.source).font(.caption2).foregroundStyle(.tertiary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .help("Use \(match.tuning.name)")
            if let url = URL(string: match.url), url.scheme != nil {
                Link(destination: url) { Image(systemName: "arrow.up.right.square") }
                    .help("Open the source page")
            }
        }
    }
}

/// A tuning text field checked with `describe` as you type, plus its save button.
struct TuningField: View {
    @Bindable var panel: SidePanelModel
    let actionTitle: String

    private var canSave: Bool {
        guard !panel.typed.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        if case .failure? = panel.typedResult { return false }
        return true
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                TextField("Tuning, e.g. Drop D", text: $panel.typed)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { if canSave { Task { await panel.save() } } }
                Button(actionTitle) { Task { await panel.save() } }
                    .disabled(!canSave)
            }
            switch panel.typedResult {
            case .success(let info)?:
                Text("Goes to \(info.playlistName) (\(info.notes))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            case .failure(let error)?:
                Text(message(error))
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            case nil:
                EmptyView()
            }
        }
    }

    private func message(_ e: ClientError) -> String {
        if case let .helper(_, message) = e { return message }
        return String(describing: e)
    }
}
